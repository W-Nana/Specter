"""GOST YAML 配置生成器

從數據庫中的 rules 生成某個 Agent 的完整 GOST 配置。
這是整個系統的核心翻譯層：業務規則 → GOST 配置。

調用鏈: server.py handle_heartbeat()
        → build_config(agent_id, rules, agents_map)
        → 返回 YAML 字符串
"""

import hashlib
import logging
import yaml

logger = logging.getLogger(__name__)


def build_config(agent_id: str, rules: list[dict], agents_map: dict[str, dict]) -> str:
    """從規則列表生成某個 Agent 的完整 GOST YAML

    參數:
        agent_id: 目標 Agent 的 ID
        rules: 所有涉及此 Agent 的規則列表
        agents_map: {agent_id: {name, host, ...}} 全局映射

    返回:
        GOST 配置的 YAML 字符串

    配置生成邏輯:
        1. 遍歷每條 rule
        2. forward 規則 → 如果此 agent 是 src → 生成 tcp/udp service
        3. tunnel 規則 → 分兩種角色:
           - 此 agent 是 src（公網方）→ 生成 relay service
           - 此 agent 是 dst（NAT 方）→ 生成 rtcp service + chain
    """
    services = []
    chains = []

    # 收集此 Agent 需要開放的 relay 端口（去重）
    relay_ports = set()

    for rule in rules:
        rule_type = rule["rule_type"]

        if rule_type == "forward" and rule["src_agent_id"] == agent_id:
            # === 正向轉發：此 Agent 監聽，轉發到目標 ===
            svc = _build_forward_service(rule, agents_map)
            if svc:
                services.append(svc)

        elif rule_type == "tunnel":
            if rule["src_agent_id"] == agent_id:
                # === 反向隧道：此 Agent 是公網方，需要 relay 入口 ===
                relay_ports.add(rule.get("relay_port", 8420))

            elif rule["dst_agent_id"] == agent_id:
                # === 反向隧道：此 Agent 是 NAT 方，發起 rtcp 連接 ===
                svc, chain = _build_tunnel_client(rule, agents_map)
                if svc and chain:
                    services.append(svc)
                    chains.append(chain)

    # 為每個 relay 端口生成一個 relay service
    for port in sorted(relay_ports):
        services.append(_build_relay_service(port))

    # 組裝完整配置
    config = {}
    if services:
        config["services"] = services
    if chains:
        config["chains"] = chains

    return yaml.dump(config, default_flow_style=False, allow_unicode=True)


def config_hash(yaml_str: str) -> str:
    """計算配置的 MD5 hash，用於比對是否需要更新"""
    return hashlib.md5(yaml_str.encode()).hexdigest()


# ============================================================
# 內部構建函數
# ============================================================


def _host_port(host: str, port: int) -> str:
    """格式化 host:port，IPv6 地址自動加方括號

    IPv4: 1.2.3.4:8420
    IPv6: [2406:da14::44f8]:8420
    """
    if ":" in host:
        return f"[{host}]:{port}"
    return f"{host}:{port}"



def _build_forward_service(rule: dict, agents_map: dict) -> dict | None:
    """生成正向轉發的 GOST service 配置

    場景: Agent 監聯 :listen_port → 轉發到任意 target (IP:port)
    forward 規則的目標地址直接使用 dst_addr 字段
    """
    target_addr = rule.get("dst_addr")
    if not target_addr:
        logger.warning("規則 #%d: 缺少目標地址 dst_addr，跳過", rule["id"])
        return None

    protocol = rule.get("protocol", "tcp")
    service_name = f"fwd-{protocol}-{rule['listen_port']}-r{rule['id']}"

    return {
        "name": service_name,
        "addr": f":{rule['listen_port']}",
        "handler": {"type": protocol},
        "listener": {"type": protocol},
        "forwarder": {
            "nodes": [
                {
                    "name": "target-0",
                    "addr": target_addr,
                }
            ]
        },
        "metadata": {"enableStats": True},
    }


def _build_relay_service(port: int) -> dict:
    """生成 relay 入口 service（供反向隧道的 NAT 方連接）

    場景: 公網 Agent 上開一個 relay 端口，
          NAT 後的 Agent 連接此端口建立反向隧道
    """
    return {
        "name": f"relay-{port}",
        "addr": f":{port}",
        "handler": {
            "type": "relay",
            "metadata": {"bind": True},
        },
        "listener": {"type": "tcp"},
        "metadata": {"enableStats": True},
    }


def _build_tunnel_client(rule: dict, agents_map: dict) -> tuple[dict | None, dict | None]:
    """生成反向隧道客戶端的 service + chain

    場景: Agent(B, NAT 後) 連接 Agent(A, 公網) 的 relay，
          使 Agent(A):listen_port → 隧道 → Agent(B):target_port

    返回: (service_dict, chain_dict) 或 (None, None)
    """
    # 公網 Agent 的地址
    src_agent = agents_map.get(rule["src_agent_id"])
    if not src_agent or not src_agent.get("host"):
        logger.warning("規則 #%d: 公網 Agent 地址未知，跳過", rule["id"])
        return None, None

    relay_port = rule.get("relay_port", 8420)
    protocol = rule.get("protocol", "tcp")
    chain_name = f"chain-r{rule['id']}"
    service_name = f"rtcp-{rule['listen_port']}-r{rule['id']}"

    # rtcp service: 告訴公網 Agent 在 listen_port 監聽
    # 收到的流量通過隧道轉發到本地的 target_port
    service = {
        "name": service_name,
        "addr": f":{rule['listen_port']}",
        "handler": {
            "type": f"r{protocol}",
            "chain": chain_name,
        },
        "listener": {
            "type": f"r{protocol}",
            "chain": chain_name,
        },
        "forwarder": {
            "nodes": [
                {
                    "name": "target-0",
                    "addr": f"127.0.0.1:{rule['target_port']}",
                }
            ]
        },
        "metadata": {"enableStats": True},
    }

    # chain: 連接到公網 Agent 的 relay 端口
    chain = {
        "name": chain_name,
        "hops": [
            {
                "name": "hop-0",
                "nodes": [
                    {
                        "name": "node-0",
                        "addr": _host_port(src_agent['host'], relay_port),
                        "connector": {"type": "relay"},
                        "dialer": {"type": "tcp"},
                    }
                ],
            }
        ],
    }

    return service, chain
