"""Agent HTTP API 服務器

Agent 主動連接此 API 進行註冊、心跳上報、配置拉取。
與 Discord Bot 共享同一個 asyncio 事件循環和 Database 實例。

調用鏈: bot.py 啟動時 → start_server(bot) → aiohttp 開始監聽
        Agent POST /api/v1/register → handle_register()
        Agent POST /api/v1/heartbeat → handle_heartbeat()
"""

import logging
from aiohttp import web

from master import gost_builder

logger = logging.getLogger(__name__)


async def handle_register(request: web.Request) -> web.Response:
    """處理 Agent 註冊請求

    調用鏈: Agent install.sh → POST /api/v1/register
            → database.register_agent()
            → 通知 Discord 頻道

    請求 Body:
        {"token": "one-time-reg-token"}

    回應:
        成功: {"ok": true, "agent_id": "...", "agent_token": "...", "poll_interval": N}
        失敗: {"ok": false, "error": "..."}
    """
    try:
        data = await request.json()
    except Exception:
        return web.json_response({"ok": False, "error": "無效的 JSON"}, status=400)

    token = data.get("token")
    if not token:
        return web.json_response({"ok": False, "error": "缺少 token"}, status=400)

    # 從請求中獲取 Agent 的公網 IP
    host = _get_client_ip(request)

    db = request.app["db"]
    result = await db.register_agent(token, host)

    if not result:
        return web.json_response({"ok": False, "error": "無效或已使用的 token"}, status=401)

    logger.info("Agent '%s' 已註冊，IP: %s", result["name"], host)

    # 向 Discord 發送通知
    bot = request.app["bot"]
    await _notify_discord(
        bot,
        request.app["notify_channel_id"],
        f"✅ Agent **{result['name']}** (`{host}`) 已上線",
    )

    return web.json_response({
        "ok": True,
        "agent_id": result["id"],
        "agent_token": result["agent_token"],
        "poll_interval": result["poll_interval"],
    })


async def handle_heartbeat(request: web.Request) -> web.Response:
    """處理 Agent 心跳

    調用鏈: Agent daemon 每 N 秒
            → POST /api/v1/heartbeat
            → 驗證 token
            → 更新統計
            → 比對配置 hash → 需要更新時返回新配置

    請求 Body:
        {
            "agent_id": "uuid",
            "agent_token": "permanent-token",
            "config_hash": "md5-of-current-config",
            "stats": [
                {"service": "name", "totalConns": N, "currentConns": N,
                 "inputBytes": N, "outputBytes": N, "totalErrs": N},
                ...
            ]
        }

    回應:
        {"ok": true, "config": "yaml-string" | null, "poll_interval": N}
    """
    try:
        data = await request.json()
    except Exception:
        return web.json_response({"ok": False, "error": "無效的 JSON"}, status=400)

    agent_id = data.get("agent_id")
    agent_token = data.get("agent_token")
    client_hash = data.get("config_hash", "")

    if not agent_id or not agent_token:
        return web.json_response({"ok": False, "error": "缺少認證信息"}, status=400)

    db = request.app["db"]

    # 驗證身份 + 更新心跳
    agent = await db.heartbeat(agent_id, agent_token, client_hash)
    if not agent:
        return web.json_response({"ok": False, "error": "認證失敗"}, status=401)

    # 更新流量統計
    stats_list = data.get("stats", [])
    for stat in stats_list:
        svc_name = stat.get("service")
        if svc_name:
            await db.upsert_stats(agent_id, svc_name, stat)

    # 生成此 Agent 的 GOST 配置
    rules = await db.get_rules_for_agent(agent_id)
    agents_map = await db.get_agents_map()
    config_yaml = gost_builder.build_config(agent_id, rules, agents_map)
    new_hash = gost_builder.config_hash(config_yaml)

    # 比對 hash：只有配置變更時才下發
    config_response = None
    if new_hash != client_hash:
        config_response = config_yaml
        logger.info(
            "Agent '%s' 配置更新: %s → %s",
            agent["name"], client_hash[:8], new_hash[:8],
        )

    return web.json_response({
        "ok": True,
        "config": config_response,
        "config_hash": new_hash,
        "poll_interval": agent["poll_interval"],
    })


async def start_server(bot, db, config):
    """啟動 Agent HTTP API 服務器

    調用鏈: bot.py on_ready() → start_server()
    與 Bot 共享同一個 asyncio 事件循環
    """
    app = web.Application()

    # 注入共享依賴
    app["db"] = db
    app["bot"] = bot
    app["notify_channel_id"] = config.notify_channel_id

    # 路由
    app.router.add_post("/api/v1/register", handle_register)
    app.router.add_post("/api/v1/heartbeat", handle_heartbeat)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", config.api_port)
    await site.start()

    logger.info("Agent HTTP API 啟動在 :%d", config.api_port)
    return runner


def _get_client_ip(request: web.Request) -> str:
    """從請求中提取客戶端 IP

    優先讀取反向代理的 X-Forwarded-For，否則用 peername
    """
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()

    peername = request.transport.get_extra_info("peername")
    if peername:
        return peername[0]

    return "unknown"


async def _notify_discord(bot, channel_id: int, message: str):
    """向 Discord 頻道發送通知"""
    try:
        channel = bot.get_channel(channel_id)
        if channel:
            await channel.send(message)
        else:
            logger.warning("通知頻道 %d 不存在", channel_id)
    except Exception as e:
        logger.error("Discord 通知發送失敗: %s", e)
