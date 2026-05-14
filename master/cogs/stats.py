"""流量統計命令

/stats <agent>  - 查看指定 Agent 的流量統計
/stats_summary  - 全局匯總

調用鏈: Discord 用戶 → slash command → Database.get_stats()
"""

import logging
import discord
from discord import app_commands
from discord.ext import commands

from master.cogs import agent_autocomplete

logger = logging.getLogger(__name__)


def _format_bytes(n: int) -> str:
    """人類可讀的流量大小"""
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(n) < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} PB"


class StatsCog(commands.Cog):
    """流量統計命令組"""

    def __init__(self, bot):
        self.bot = bot
        self.db = bot.db

    @app_commands.command(name="stats", description="查看 Agent 流量統計")
    @app_commands.describe(agent="Agent 名稱")
    @app_commands.autocomplete(agent=agent_autocomplete)
    @app_commands.checks.has_permissions(administrator=True)
    async def stats(self, interaction: discord.Interaction, agent: str):
        """查看指定 Agent 的各 service 流量統計"""
        a = await self.db.get_agent_by_name(agent)
        if not a:
            await interaction.response.send_message(
                f"❌ Agent `{agent}` 不存在", ephemeral=True
            )
            return

        stats_list = await self.db.get_stats(agent_id=a["id"])
        if not stats_list:
            await interaction.response.send_message(
                f"📭 Agent `{agent}` 暫無統計數據", ephemeral=True
            )
            return

        embed = discord.Embed(
            title=f"📊 Agent `{agent}` 流量統計",
            color=0xE67E22,
        )

        for s in stats_list:
            value = (
                f"連接: {s['total_conns']} 總 / {s['current_conns']} 當前\n"
                f"上傳: {_format_bytes(s['input_bytes'])}\n"
                f"下載: {_format_bytes(s['output_bytes'])}\n"
                f"錯誤: {s['total_errs']}"
            )
            embed.add_field(
                name=f"🔹 {s['service_name']}",
                value=value,
                inline=True,
            )

        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="stats_summary", description="全局流量匯總")
    @app_commands.checks.has_permissions(administrator=True)
    async def stats_summary(self, interaction: discord.Interaction):
        """所有 Agent 的匯總統計"""
        all_stats = await self.db.get_stats()
        if not all_stats:
            await interaction.response.send_message("📭 暫無統計數據", ephemeral=True)
            return

        agents_map = await self.db.get_agents_map()

        # 按 Agent 分組匯總
        summary = {}
        for s in all_stats:
            aid = s["agent_id"]
            if aid not in summary:
                name = agents_map.get(aid, {}).get("name", aid[:8])
                summary[aid] = {
                    "name": name,
                    "services": 0,
                    "total_conns": 0,
                    "input_bytes": 0,
                    "output_bytes": 0,
                    "total_errs": 0,
                }
            summary[aid]["services"] += 1
            summary[aid]["total_conns"] += s["total_conns"]
            summary[aid]["input_bytes"] += s["input_bytes"]
            summary[aid]["output_bytes"] += s["output_bytes"]
            summary[aid]["total_errs"] += s["total_errs"]

        embed = discord.Embed(
            title=f"📊 全局流量匯總 ({len(summary)} Agents)",
            color=0xE67E22,
        )

        # 全局總計
        total_in = sum(v["input_bytes"] for v in summary.values())
        total_out = sum(v["output_bytes"] for v in summary.values())
        total_conns = sum(v["total_conns"] for v in summary.values())
        embed.description = (
            f"**總上傳:** {_format_bytes(total_in)} | "
            f"**總下載:** {_format_bytes(total_out)} | "
            f"**總連接:** {total_conns}"
        )

        for data in summary.values():
            value = (
                f"服務數: {data['services']}\n"
                f"上傳: {_format_bytes(data['input_bytes'])} | "
                f"下載: {_format_bytes(data['output_bytes'])}\n"
                f"連接: {data['total_conns']} | 錯誤: {data['total_errs']}"
            )
            embed.add_field(name=f"📡 {data['name']}", value=value, inline=True)

        await interaction.response.send_message(embed=embed)


async def setup(bot):
    await bot.add_cog(StatsCog(bot))
