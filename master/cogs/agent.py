"""Agent 管理命令

/agent create <name> - 創建 Agent + 生成安裝命令
/agent list          - 列出所有 Agent
/agent remove <name> - 移除 Agent
/agent rename <old> <new> - 重命名
/agent set-interval <name> <seconds> - 設定心跳間隔

調用鏈: Discord 用戶 → slash command → Database CRUD
"""

import time
import logging
import discord
from discord import app_commands
from discord.ext import commands

logger = logging.getLogger(__name__)


class AgentCog(commands.Cog):
    """Agent 管理命令組"""

    def __init__(self, bot):
        self.bot = bot
        # db 和 config 由 bot 實例持有
        self.db = bot.db
        self.config = bot.cfg

    @app_commands.command(name="agent_create", description="創建新 Agent 並生成安裝命令")
    @app_commands.describe(name="Agent 名稱（如 us-west-1）")
    @app_commands.checks.has_permissions(administrator=True)
    async def agent_create(self, interaction: discord.Interaction, name: str):
        """創建 Agent，生成一次性 token，返回安裝命令"""
        # 檢查名稱是否已存在
        existing = await self.db.get_agent_by_name(name)
        if existing:
            await interaction.response.send_message(
                f"❌ Agent `{name}` 已存在", ephemeral=True
            )
            return

        agent = await self.db.create_agent(name, self.config.default_poll_interval)

        # 生成安裝命令
        install_cmd = (
            f"curl -sSL https://raw.githubusercontent.com/W-Nana/Specter/main/install.sh "
            f"| bash -s -- --master http://<MASTER_IP>:{self.config.api_port} "
            f"--token {agent['reg_token']}"
        )

        embed = discord.Embed(
            title=f"✅ Agent `{name}` 已創建",
            color=0x2ECC71,
        )
        embed.add_field(
            name="📋 安裝命令",
            value=f"```bash\n{install_cmd}\n```",
            inline=False,
        )
        embed.add_field(
            name="⚠️ 注意",
            value="請將 `<MASTER_IP>` 替換為 Master 的公網 IP。此 token 僅可使用一次。",
            inline=False,
        )
        embed.set_footer(text=f"Agent ID: {agent['id']}")

        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="agent_list", description="列出所有 Agent")
    @app_commands.checks.has_permissions(administrator=True)
    async def agent_list(self, interaction: discord.Interaction):
        """列出所有 Agent + 在線狀態"""
        agents = await self.db.list_agents()

        if not agents:
            await interaction.response.send_message("📭 尚無任何 Agent", ephemeral=True)
            return

        now = int(time.time())
        lines = []
        for a in agents:
            # 判斷在線狀態：心跳超時 = poll_interval * 3
            timeout = a["poll_interval"] * 3
            if a["status"] == "pending":
                status = "⏳ 待註冊"
            elif a["last_heartbeat"] and (now - a["last_heartbeat"]) < timeout:
                status = "🟢 在線"
            else:
                status = "🔴 離線"

            host = a["host"] or "N/A"
            lines.append(f"{status} **{a['name']}** | `{host}` | 間隔 {a['poll_interval']}s")

        embed = discord.Embed(
            title=f"📡 Agent 列表 ({len(agents)})",
            description="\n".join(lines),
            color=0x3498DB,
        )

        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="agent_remove", description="移除 Agent（級聯刪除規則）")
    @app_commands.describe(name="Agent 名稱")
    @app_commands.checks.has_permissions(administrator=True)
    async def agent_remove(self, interaction: discord.Interaction, name: str):
        """移除 Agent 及其所有規則"""
        removed = await self.db.remove_agent(name)
        if removed:
            await interaction.response.send_message(f"✅ Agent `{name}` 已移除")
        else:
            await interaction.response.send_message(
                f"❌ Agent `{name}` 不存在", ephemeral=True
            )

    @app_commands.command(name="agent_rename", description="重命名 Agent")
    @app_commands.describe(old_name="當前名稱", new_name="新名稱")
    @app_commands.checks.has_permissions(administrator=True)
    async def agent_rename(
        self, interaction: discord.Interaction, old_name: str, new_name: str
    ):
        """重命名 Agent"""
        success = await self.db.rename_agent(old_name, new_name)
        if success:
            await interaction.response.send_message(
                f"✅ Agent `{old_name}` → `{new_name}`"
            )
        else:
            await interaction.response.send_message(
                f"❌ 重命名失敗：`{old_name}` 不存在或 `{new_name}` 已被使用",
                ephemeral=True,
            )

    @app_commands.command(name="agent_interval", description="設定 Agent 心跳間隔")
    @app_commands.describe(name="Agent 名稱", seconds="間隔秒數")
    @app_commands.checks.has_permissions(administrator=True)
    async def agent_interval(
        self, interaction: discord.Interaction, name: str, seconds: int
    ):
        """設定心跳間隔"""
        if seconds < 3 or seconds > 300:
            await interaction.response.send_message(
                "❌ 間隔範圍 3-300 秒", ephemeral=True
            )
            return

        success = await self.db.set_agent_interval(name, seconds)
        if success:
            await interaction.response.send_message(
                f"✅ Agent `{name}` 心跳間隔設為 {seconds}s"
            )
        else:
            await interaction.response.send_message(
                f"❌ Agent `{name}` 不存在", ephemeral=True
            )


async def setup(bot):
    """Cog 載入入口，由 bot.py 調用"""
    await bot.add_cog(AgentCog(bot))
