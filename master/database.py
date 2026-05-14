"""Specter SQLite 數據層

三張核心表 + CRUD 操作。用 aiosqlite 做 async。
調用鏈: cogs/* 和 server.py → Database.*()
"""

import uuid
import time
import secrets
import logging
import aiosqlite
from typing import Optional

logger = logging.getLogger(__name__)

# ============================================================
# Schema：三張表，零特殊情況
# ============================================================

SCHEMA = """
CREATE TABLE IF NOT EXISTS agents (
    id TEXT PRIMARY KEY,
    name TEXT UNIQUE NOT NULL,
    host TEXT DEFAULT '',
    agent_token TEXT NOT NULL,
    reg_token TEXT NOT NULL,
    config_hash TEXT DEFAULT '',
    status TEXT DEFAULT 'pending',
    last_heartbeat INTEGER DEFAULT 0,
    poll_interval INTEGER DEFAULT 10,
    created_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS rules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    rule_type TEXT NOT NULL,
    src_agent_id TEXT NOT NULL,
    dst_agent_id TEXT,
    dst_addr TEXT,
    listen_port INTEGER NOT NULL,
    target_port INTEGER NOT NULL,
    protocol TEXT DEFAULT 'tcp',
    relay_port INTEGER DEFAULT 8420,
    created_at INTEGER NOT NULL,
    FOREIGN KEY (src_agent_id) REFERENCES agents(id) ON DELETE CASCADE,
    FOREIGN KEY (dst_agent_id) REFERENCES agents(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS traffic_stats (
    agent_id TEXT NOT NULL,
    service_name TEXT NOT NULL,
    total_conns INTEGER DEFAULT 0,
    current_conns INTEGER DEFAULT 0,
    input_bytes INTEGER DEFAULT 0,
    output_bytes INTEGER DEFAULT 0,
    total_errs INTEGER DEFAULT 0,
    updated_at INTEGER NOT NULL,
    PRIMARY KEY (agent_id, service_name),
    FOREIGN KEY (agent_id) REFERENCES agents(id) ON DELETE CASCADE
);
"""


class Database:
    """Specter SQLite 數據庫

    所有方法都是 async。連接在 init() 中創建，close() 中關閉。
    """

    def __init__(self, db_path: str):
        self._db_path = db_path
        self._db: Optional[aiosqlite.Connection] = None

    async def init(self):
        """初始化連接 + 建表"""
        self._db = await aiosqlite.connect(self._db_path)
        # 開啟外鍵約束和 WAL 模式
        await self._db.execute("PRAGMA journal_mode=WAL")
        await self._db.execute("PRAGMA foreign_keys=ON")
        await self._db.executescript(SCHEMA)
        await self._db.commit()
        logger.info("數據庫初始化完成: %s", self._db_path)

    async def close(self):
        """關閉連接"""
        if self._db:
            await self._db.close()

    # ============================================================
    # Agent CRUD
    # ============================================================

    async def create_agent(self, name: str, poll_interval: int = 10) -> dict:
        """創建 Agent（pending 狀態），生成註冊 token

        調用鏈: cogs/agent.py /agent create → create_agent()
        返回: {id, name, reg_token, agent_token, ...}
        """
        agent_id = str(uuid.uuid4())
        # 註冊 token: 短且人類可讀，用於安裝命令
        reg_token = secrets.token_urlsafe(16)
        # 永久 token: 長且安全，用於心跳認證
        agent_token = secrets.token_urlsafe(32)
        now = int(time.time())

        await self._db.execute(
            """INSERT INTO agents (id, name, agent_token, reg_token, poll_interval, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (agent_id, name, agent_token, reg_token, poll_interval, now),
        )
        await self._db.commit()

        return {
            "id": agent_id,
            "name": name,
            "reg_token": reg_token,
            "agent_token": agent_token,
            "poll_interval": poll_interval,
            "status": "pending",
            "created_at": now,
        }

    async def register_agent(self, reg_token: str, host: str) -> Optional[dict]:
        """Agent 用註冊 token 完成註冊

        調用鏈: server.py handle_register() → register_agent()
        返回: {id, name, agent_token, poll_interval} 或 None（token 無效）
        """
        cursor = await self._db.execute(
            "SELECT id, name, agent_token, poll_interval FROM agents WHERE reg_token = ? AND status = 'pending'",
            (reg_token,),
        )
        row = await cursor.fetchone()
        if not row:
            return None

        agent_id, name, agent_token, poll_interval = row
        now = int(time.time())

        await self._db.execute(
            "UPDATE agents SET host = ?, status = 'online', last_heartbeat = ? WHERE id = ?",
            (host, now, agent_id),
        )
        await self._db.commit()

        return {
            "id": agent_id,
            "name": name,
            "agent_token": agent_token,
            "poll_interval": poll_interval,
        }

    async def get_agent_by_name(self, name: str) -> Optional[dict]:
        """按名稱查詢 Agent"""
        cursor = await self._db.execute(
            "SELECT id, name, host, status, last_heartbeat, poll_interval, created_at FROM agents WHERE name = ?",
            (name,),
        )
        row = await cursor.fetchone()
        if not row:
            return None
        return dict(
            zip(
                ["id", "name", "host", "status", "last_heartbeat", "poll_interval", "created_at"],
                row,
            )
        )

    async def get_agent_by_id(self, agent_id: str) -> Optional[dict]:
        """按 ID 查詢 Agent"""
        cursor = await self._db.execute(
            "SELECT id, name, host, status, last_heartbeat, poll_interval, created_at FROM agents WHERE id = ?",
            (agent_id,),
        )
        row = await cursor.fetchone()
        if not row:
            return None
        return dict(
            zip(
                ["id", "name", "host", "status", "last_heartbeat", "poll_interval", "created_at"],
                row,
            )
        )

    async def list_agents(self) -> list[dict]:
        """列出所有 Agent"""
        cursor = await self._db.execute(
            "SELECT id, name, host, status, last_heartbeat, poll_interval, created_at FROM agents ORDER BY created_at"
        )
        rows = await cursor.fetchall()
        cols = ["id", "name", "host", "status", "last_heartbeat", "poll_interval", "created_at"]
        return [dict(zip(cols, row)) for row in rows]

    async def remove_agent(self, name: str) -> bool:
        """刪除 Agent（級聯刪除 rules + stats）

        調用鏈: cogs/agent.py /agent remove → remove_agent()
        """
        cursor = await self._db.execute("DELETE FROM agents WHERE name = ?", (name,))
        await self._db.commit()
        return cursor.rowcount > 0

    async def rename_agent(self, old_name: str, new_name: str) -> bool:
        """重命名 Agent"""
        try:
            cursor = await self._db.execute(
                "UPDATE agents SET name = ? WHERE name = ?", (new_name, old_name)
            )
            await self._db.commit()
            return cursor.rowcount > 0
        except aiosqlite.IntegrityError:
            return False

    async def set_agent_interval(self, name: str, interval: int) -> bool:
        """設定 Agent 心跳間隔"""
        cursor = await self._db.execute(
            "UPDATE agents SET poll_interval = ? WHERE name = ?", (interval, name)
        )
        await self._db.commit()
        return cursor.rowcount > 0

    async def set_agent_host(self, name: str, host: str) -> bool:
        """手動設定 Agent 地址

        調用鏈: cogs/agent.py /agent_sethost → set_agent_host()
        用於覆蓋註冊時自動記錄的 IP（如需指定 IPv4 而非 IPv6）
        """
        cursor = await self._db.execute(
            "UPDATE agents SET host = ? WHERE name = ?", (host, name)
        )
        await self._db.commit()
        return cursor.rowcount > 0

    # ============================================================
    # 心跳處理
    # ============================================================

    async def heartbeat(self, agent_id: str, agent_token: str, config_hash: str) -> Optional[dict]:
        """處理心跳：驗證 token，更新狀態，返回 agent 信息

        調用鏈: server.py handle_heartbeat() → heartbeat()
        返回: agent dict 或 None（認證失敗）
        """
        cursor = await self._db.execute(
            "SELECT id, name, config_hash, poll_interval FROM agents WHERE id = ? AND agent_token = ?",
            (agent_id, agent_token),
        )
        row = await cursor.fetchone()
        if not row:
            return None

        now = int(time.time())
        await self._db.execute(
            "UPDATE agents SET last_heartbeat = ?, status = 'online', config_hash = ? WHERE id = ?",
            (now, config_hash, agent_id),
        )
        await self._db.commit()

        return {
            "id": row[0],
            "name": row[1],
            "config_hash": row[2],  # Master 端記錄的 hash，用於比對
            "poll_interval": row[3],
        }

    # ============================================================
    # Rules CRUD
    # ============================================================

    async def create_rule(
        self,
        rule_type: str,
        src_agent_id: str,
        listen_port: int,
        target_port: int,
        dst_agent_id: str = None,
        dst_addr: str = None,
        protocol: str = "tcp",
        relay_port: int = 8420,
    ) -> dict:
        """創建轉發規則

        調用鏈: cogs/forward.py 或 cogs/tunnel.py → create_rule()
        """
        now = int(time.time())
        cursor = await self._db.execute(
            """INSERT INTO rules
               (rule_type, src_agent_id, dst_agent_id, dst_addr,
                listen_port, target_port, protocol, relay_port, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (rule_type, src_agent_id, dst_agent_id, dst_addr,
             listen_port, target_port, protocol, relay_port, now),
        )
        await self._db.commit()

        return {
            "id": cursor.lastrowid,
            "rule_type": rule_type,
            "src_agent_id": src_agent_id,
            "dst_agent_id": dst_agent_id,
            "dst_addr": dst_addr,
            "listen_port": listen_port,
            "target_port": target_port,
            "protocol": protocol,
            "relay_port": relay_port,
            "created_at": now,
        }

    async def remove_rule(self, rule_id: int) -> bool:
        """刪除轉發規則"""
        cursor = await self._db.execute("DELETE FROM rules WHERE id = ?", (rule_id,))
        await self._db.commit()
        return cursor.rowcount > 0

    async def get_rule(self, rule_id: int) -> Optional[dict]:
        """查詢單條規則"""
        cursor = await self._db.execute(
            """SELECT id, rule_type, src_agent_id, dst_agent_id, dst_addr,
                      listen_port, target_port, protocol, relay_port, created_at
               FROM rules WHERE id = ?""",
            (rule_id,),
        )
        row = await cursor.fetchone()
        if not row:
            return None
        cols = [
            "id", "rule_type", "src_agent_id", "dst_agent_id", "dst_addr",
            "listen_port", "target_port", "protocol", "relay_port", "created_at",
        ]
        return dict(zip(cols, row))

    async def list_rules(self, agent_id: str = None, rule_type: str = None) -> list[dict]:
        """列出規則，可按 agent 或類型篩選"""
        query = """SELECT id, rule_type, src_agent_id, dst_agent_id, dst_addr,
                          listen_port, target_port, protocol, relay_port, created_at
                   FROM rules WHERE 1=1"""
        params = []

        if agent_id:
            query += " AND (src_agent_id = ? OR dst_agent_id = ?)"
            params.extend([agent_id, agent_id])
        if rule_type:
            query += " AND rule_type = ?"
            params.append(rule_type)

        query += " ORDER BY created_at"
        cursor = await self._db.execute(query, params)
        rows = await cursor.fetchall()
        cols = [
            "id", "rule_type", "src_agent_id", "dst_agent_id", "dst_addr",
            "listen_port", "target_port", "protocol", "relay_port", "created_at",
        ]
        return [dict(zip(cols, row)) for row in rows]

    async def get_rules_for_agent(self, agent_id: str) -> list[dict]:
        """獲取某個 Agent 相關的所有規則（作為 src 或 dst）

        調用鏈: server.py handle_heartbeat() → get_rules_for_agent()
                → gost_builder.build_config() 生成 GOST 配置
        """
        return await self.list_rules(agent_id=agent_id)

    # ============================================================
    # 流量統計
    # ============================================================

    async def upsert_stats(self, agent_id: str, service_name: str, stats: dict):
        """更新或插入流量統計（UPSERT）

        調用鏈: server.py handle_heartbeat() → upsert_stats()
        """
        now = int(time.time())
        await self._db.execute(
            """INSERT INTO traffic_stats
                   (agent_id, service_name, total_conns, current_conns,
                    input_bytes, output_bytes, total_errs, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(agent_id, service_name) DO UPDATE SET
                   total_conns = excluded.total_conns,
                   current_conns = excluded.current_conns,
                   input_bytes = excluded.input_bytes,
                   output_bytes = excluded.output_bytes,
                   total_errs = excluded.total_errs,
                   updated_at = excluded.updated_at""",
            (
                agent_id,
                service_name,
                stats.get("totalConns", 0),
                stats.get("currentConns", 0),
                stats.get("inputBytes", 0),
                stats.get("outputBytes", 0),
                stats.get("totalErrs", 0),
                now,
            ),
        )
        await self._db.commit()

    async def get_stats(self, agent_id: str = None) -> list[dict]:
        """查詢流量統計

        調用鏈: cogs/stats.py → get_stats()
        """
        if agent_id:
            cursor = await self._db.execute(
                """SELECT agent_id, service_name, total_conns, current_conns,
                          input_bytes, output_bytes, total_errs, updated_at
                   FROM traffic_stats WHERE agent_id = ? ORDER BY service_name""",
                (agent_id,),
            )
        else:
            cursor = await self._db.execute(
                """SELECT agent_id, service_name, total_conns, current_conns,
                          input_bytes, output_bytes, total_errs, updated_at
                   FROM traffic_stats ORDER BY agent_id, service_name"""
            )

        rows = await cursor.fetchall()
        cols = [
            "agent_id", "service_name", "total_conns", "current_conns",
            "input_bytes", "output_bytes", "total_errs", "updated_at",
        ]
        return [dict(zip(cols, row)) for row in rows]

    # ============================================================
    # Agent 名稱 → IP 解析（供 gost_builder 使用）
    # ============================================================

    async def get_agents_map(self) -> dict[str, dict]:
        """返回 {agent_id: {name, host, ...}} 映射表

        調用鏈: gost_builder.build_config() → get_agents_map()
        """
        agents = await self.list_agents()
        return {a["id"]: a for a in agents}
