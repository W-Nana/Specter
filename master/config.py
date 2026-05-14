"""Specter Master 配置管理

從環境變量讀取配置，提供 dataclass 形式的配置對象。
調用鏈: bot.py → Config.load() → 全局使用
"""

import os
import logging
from dataclasses import dataclass
from dotenv import load_dotenv

logger = logging.getLogger(__name__)


@dataclass
class Config:
    """Master 端所有配置項，從環境變量載入"""

    # Discord 設定
    discord_token: str
    guild_id: int
    notify_channel_id: int

    # Agent HTTP API
    api_port: int

    # GOST 默認值
    default_relay_port: int
    default_poll_interval: int

    # 存儲
    db_path: str

    # 日誌
    log_level: str

    @classmethod
    def load(cls) -> "Config":
        """從 .env 文件和環境變量載入配置

        優先級: 環境變量 > .env 文件
        必填項缺失時直接 raise，不搞默認值糊弄
        """
        load_dotenv()

        # 必填項 — 沒有就死
        discord_token = os.environ.get("DISCORD_TOKEN")
        if not discord_token:
            raise ValueError("DISCORD_TOKEN 未設定，Bot 無法啟動")

        guild_id = os.environ.get("GUILD_ID")
        if not guild_id:
            raise ValueError("GUILD_ID 未設定")

        notify_channel_id = os.environ.get("NOTIFY_CHANNEL_ID")
        if not notify_channel_id:
            raise ValueError("NOTIFY_CHANNEL_ID 未設定")

        return cls(
            discord_token=discord_token,
            guild_id=int(guild_id),
            notify_channel_id=int(notify_channel_id),
            api_port=int(os.environ.get("API_PORT", "8080")),
            default_relay_port=int(os.environ.get("DEFAULT_RELAY_PORT", "8420")),
            default_poll_interval=int(os.environ.get("DEFAULT_POLL_INTERVAL", "10")),
            db_path=os.environ.get("DB_PATH", "specter.db"),
            log_level=os.environ.get("LOG_LEVEL", "INFO"),
        )

    def setup_logging(self):
        """配置全局日誌格式"""
        logging.basicConfig(
            level=getattr(logging, self.log_level.upper(), logging.INFO),
            format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
