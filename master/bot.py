"""Specter Bot 入口

啟動流程:
1. 載入配置 (.env)
2. 初始化 SQLite 數據庫
3. 載入 Discord 命令模組 (cogs)
4. 啟動 Agent HTTP API 服務器 (aiohttp，同一事件循環)
5. 啟動 Discord Bot

調用鏈:
    python -m master.bot
    → Config.load()
    → Database.init()
    → Bot.setup_hook() → 載入 cogs + 啟動 HTTP server
    → Bot.start()
"""

import asyncio
import logging
import discord
from discord.ext import commands

from master.config import Config
from master.database import Database
from master import server

logger = logging.getLogger(__name__)

# 要載入的 cogs 列表
COGS = [
    "master.cogs.agent",
    "master.cogs.forward",
    "master.cogs.tunnel",
    "master.cogs.stats",
]


class SpecterBot(commands.Bot):
    """Specter Discord Bot

    持有全局共享的 Database 和 Config 實例，
    供所有 cogs 和 HTTP server 使用。
    """

    def __init__(self, cfg: Config, db: Database):
        intents = discord.Intents.default()
        intents.message_content = True

        super().__init__(
            command_prefix="!",  # slash commands 為主，prefix 做備用
            intents=intents,
        )

        self.cfg = cfg
        self.db = db
        self._api_runner = None

    async def setup_hook(self):
        """Bot 連接 Discord 前的初始化

        1. 載入所有 cogs
        2. 同步 slash commands 到 guild
        3. 啟動 Agent HTTP API
        """
        # 載入命令模組
        for cog in COGS:
            try:
                await self.load_extension(cog)
                logger.info("載入 cog: %s", cog)
            except Exception as e:
                logger.error("載入 cog %s 失敗: %s", cog, e)

        # 同步 slash commands 到指定 guild（即時生效，不用等全局同步）
        guild = discord.Object(id=self.cfg.guild_id)
        self.tree.copy_global_to(guild=guild)
        await self.tree.sync(guild=guild)
        logger.info("Slash commands 已同步到 guild %d", self.cfg.guild_id)

        # 啟動 Agent HTTP API 服務器
        self._api_runner = await server.start_server(self, self.db, self.cfg)

    async def on_ready(self):
        """Bot 就緒回調"""
        logger.info("Bot 已上線: %s (ID: %d)", self.user.name, self.user.id)
        logger.info("Guild: %d | API: :%d", self.cfg.guild_id, self.cfg.api_port)

        # 設定 Bot 狀態
        await self.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.watching,
                name="GOST tunnels",
            )
        )

    async def close(self):
        """清理資源"""
        if self._api_runner:
            await self._api_runner.cleanup()
            logger.info("HTTP API 已關閉")

        await self.db.close()
        logger.info("數據庫已關閉")

        await super().close()


async def main():
    """主入口"""
    # 載入配置
    cfg = Config.load()
    cfg.setup_logging()

    logger.info("Specter Master 啟動中...")

    # 初始化數據庫
    db = Database(cfg.db_path)
    await db.init()

    # 創建並啟動 Bot
    bot = SpecterBot(cfg, db)

    try:
        await bot.start(cfg.discord_token)
    except KeyboardInterrupt:
        logger.info("收到中斷信號，關閉中...")
    finally:
        await bot.close()


if __name__ == "__main__":
    asyncio.run(main())
