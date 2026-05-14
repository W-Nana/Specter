"""反向隧道命令

/tunnel add <nat_agent> <pub_agent> <pub_port> <local_port> [protocol] [relay_port]
/tunnel remove <rule_id>
/tunnel list [agent]

場景: Agent(B, NAT 後) 連接 Agent(A, 公網) 建立反向隧道
      使得 Agent(A):pub_port → 隧道 → Agent(B):local_port

調用鏈: Discord 用戶 → slash command → Database
        → 兩個 Agent 下次心跳時分別拉取各自的配置
"""

import logging
import discord
from discord import app_commands
from discord.ext import commands

from master.cogs import agent_autocomplete

logger = logging.getLogger(__name__)


class TunnelCog(commands.Cog):
    """反向隧道命令組"""

    def __init__(self, bot):
        self.bot = bot
        self.db = bot.db
        self.config = bot.cfg

    @app_commands.command(name="tunnel_add", description="創建反向隧道")
    @app_commands.describe(
        nat_agent="NAT 後方的 Agent（發起連接方）",
        pub_agent="公網 Agent（提供 relay 入口 + 對外監聽）",
        pub_port="公網 Agent 上的監聽端口",
        local_port="NAT Agent 上的本地目標端口",
        protocol="協議 (tcp/udp，默認 tcp)",
        relay_port="Relay 端口（默認使用全局配置）",
    )
    @app_commands.autocomplete(nat_agent=agent_autocomplete, pub_agent=agent_autocomplete)
    @app_commands.checks.has_permissions(administrator=True)
    async def tunnel_add(
        self,
        interaction: discord.Interaction,
        nat_agent: str,
        pub_agent: str,
        pub_port: int,
        local_port: int,
        protocol: str = "tcp",
        relay_port: int = None,
    ):
        """創建反向隧道: pub_agent:pub_port → 隧道 → nat_agent:local_port"""
        if protocol not in ("tcp", "udp"):
            await interaction.response.send_message(
                "❌ protocol 僅支持 tcp 或 udp", ephemeral=True
            )
            return

        if relay_port is None:
            relay_port = self.config.default_relay_port

        # 驗證兩個 Agent 都存在
        nat = await self.db.get_agent_by_name(nat_agent)
        if not nat:
            await interaction.response.send_message(
                f"❌ Agent `{nat_agent}` 不存在", ephemeral=True
            )
            return

        pub = await self.db.get_agent_by_name(pub_agent)
        if not pub:
            await interaction.response.send_message(
                f"❌ Agent `{pub_agent}` 不存在", ephemeral=True
            )
            return

        if nat["id"] == pub["id"]:
            await interaction.response.send_message(
                "❌ NAT Agent 和公網 Agent 不能是同一台", ephemeral=True
            )
            return

        # 創建規則
        # src_agent = 公網方（提供 relay + 對外監聯端口）
        # dst_agent = NAT 方（發起 rtcp 連接 + 本地轉發）
        rule = await self.db.create_rule(
            rule_type="tunnel",
            src_agent_id=pub["id"],
            dst_agent_id=nat["id"],
            listen_port=pub_port,
            target_port=local_port,
            protocol=protocol,
            relay_port=relay_port,
        )

        embed = discord.Embed(
            title="✅ 反向隧道已創建",
            description=(
                f"**{pub_agent}**:`{pub_port}` ← 🔗隧道 ← "
                f"**{nat_agent}**:`{local_port}` ({protocol})"
            ),
            color=0x9B59B6,
        )
        embed.add_field(name="Relay 端口", value=str(relay_port), inline=True)
        embed.set_footer(text=f"Rule ID: {rule['id']} | 兩個 Agent 下次心跳時生效")

        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="tunnel_remove", description="刪除反向隧道")
    @app_commands.describe(rule_id="規則 ID")
    @app_commands.checks.has_permissions(administrator=True)
    async def tunnel_remove(self, interaction: discord.Interaction, rule_id: int):
        """刪除反向隧道規則"""
        rule = await self.db.get_rule(rule_id)
        if not rule or rule["rule_type"] != "tunnel":
            await interaction.response.send_message(
                f"❌ 隧道規則 #{rule_id} 不存在", ephemeral=True
            )
            return

        await self.db.remove_rule(rule_id)
        await interaction.response.send_message(f"✅ 隧道 #{rule_id} 已刪除，Agent 下次心跳時生效")

    @app_commands.command(name="tunnel_list", description="列出反向隧道")
    @app_commands.describe(agent="篩選指定 Agent（可選）")
    @app_commands.autocomplete(agent=agent_autocomplete)
    @app_commands.checks.has_permissions(administrator=True)
    async def tunnel_list(self, interaction: discord.Interaction, agent: str = None):
        """列出反向隧道規則"""
        agent_id = None
        if agent:
            a = await self.db.get_agent_by_name(agent)
            if not a:
                await interaction.response.send_message(
                    f"❌ Agent `{agent}` 不存在", ephemeral=True
                )
                return
            agent_id = a["id"]

        rules = await self.db.list_rules(agent_id=agent_id, rule_type="tunnel")
        if not rules:
            await interaction.response.send_message("📭 無反向隧道", ephemeral=True)
            return

        agents_map = await self.db.get_agents_map()
        lines = []
        for r in rules:
            pub_name = agents_map.get(r["src_agent_id"], {}).get("name", "?")
            nat_name = agents_map.get(r["dst_agent_id"], {}).get("name", "?")
            lines.append(
                f"`#{r['id']}` {pub_name}:`{r['listen_port']}` ← 🔗 ← "
                f"{nat_name}:`{r['target_port']}` ({r['protocol']}) "
                f"relay:{r['relay_port']}"
            )

        embed = discord.Embed(
            title=f"🔗 反向隧道 ({len(rules)})",
            description="\n".join(lines),
            color=0x9B59B6,
        )

        await interaction.response.send_message(embed=embed)


async def setup(bot):
    await bot.add_cog(TunnelCog(bot))
