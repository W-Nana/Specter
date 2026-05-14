"""正向轉發命令

/forward add <from_agent> <listen_port> <to_agent> <to_port> [protocol]
/forward remove <rule_id>
/forward list [agent]

場景: Agent(A) 監聽 listen_port → 轉發到 Agent(B):to_port
調用鏈: Discord 用戶 → slash command → Database → Agent 下次心跳時拉取新配置
"""

import logging
import discord
from discord import app_commands
from discord.ext import commands

logger = logging.getLogger(__name__)


class ForwardCog(commands.Cog):
    """正向轉發命令組"""

    def __init__(self, bot):
        self.bot = bot
        self.db = bot.db

    @app_commands.command(name="forward_add", description="創建正向轉發規則")
    @app_commands.describe(
        from_agent="監聽方 Agent 名稱",
        listen_port="監聽端口",
        to_agent="目標 Agent 名稱（或輸入 IP:port 格式）",
        to_port="目標端口",
        protocol="協議 (tcp/udp，默認 tcp)",
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def forward_add(
        self,
        interaction: discord.Interaction,
        from_agent: str,
        listen_port: int,
        to_agent: str,
        to_port: int,
        protocol: str = "tcp",
    ):
        """創建正向轉發: from_agent:listen_port → to_agent:to_port"""
        if protocol not in ("tcp", "udp"):
            await interaction.response.send_message(
                "❌ protocol 僅支持 tcp 或 udp", ephemeral=True
            )
            return

        # 解析來源 Agent
        src = await self.db.get_agent_by_name(from_agent)
        if not src:
            await interaction.response.send_message(
                f"❌ Agent `{from_agent}` 不存在", ephemeral=True
            )
            return

        # 解析目標：可以是 Agent 名稱或直接 IP:port
        dst_agent_id = None
        dst_addr = None
        dst = await self.db.get_agent_by_name(to_agent)
        if dst:
            dst_agent_id = dst["id"]
        else:
            # 視為 IP 地址（to_port 已單獨提供）
            dst_addr = f"{to_agent}:{to_port}"

        rule = await self.db.create_rule(
            rule_type="forward",
            src_agent_id=src["id"],
            listen_port=listen_port,
            target_port=to_port,
            dst_agent_id=dst_agent_id,
            dst_addr=dst_addr,
            protocol=protocol,
        )

        dst_display = to_agent if dst else dst_addr
        embed = discord.Embed(
            title="✅ 正向轉發規則已創建",
            description=(
                f"**{from_agent}**:`{listen_port}` → "
                f"**{dst_display}**:`{to_port}` ({protocol})"
            ),
            color=0x2ECC71,
        )
        embed.set_footer(text=f"Rule ID: {rule['id']} | Agent 下次心跳時生效")

        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="forward_remove", description="刪除正向轉發規則")
    @app_commands.describe(rule_id="規則 ID")
    @app_commands.checks.has_permissions(administrator=True)
    async def forward_remove(self, interaction: discord.Interaction, rule_id: int):
        """刪除正向轉發規則"""
        rule = await self.db.get_rule(rule_id)
        if not rule or rule["rule_type"] != "forward":
            await interaction.response.send_message(
                f"❌ 正向轉發規則 #{rule_id} 不存在", ephemeral=True
            )
            return

        await self.db.remove_rule(rule_id)
        await interaction.response.send_message(f"✅ 規則 #{rule_id} 已刪除，Agent 下次心跳時生效")

    @app_commands.command(name="forward_list", description="列出正向轉發規則")
    @app_commands.describe(agent="篩選指定 Agent（可選）")
    @app_commands.checks.has_permissions(administrator=True)
    async def forward_list(
        self, interaction: discord.Interaction, agent: str = None
    ):
        """列出正向轉發規則"""
        agent_id = None
        if agent:
            a = await self.db.get_agent_by_name(agent)
            if not a:
                await interaction.response.send_message(
                    f"❌ Agent `{agent}` 不存在", ephemeral=True
                )
                return
            agent_id = a["id"]

        rules = await self.db.list_rules(agent_id=agent_id, rule_type="forward")
        if not rules:
            await interaction.response.send_message("📭 無正向轉發規則", ephemeral=True)
            return

        agents_map = await self.db.get_agents_map()
        lines = []
        for r in rules:
            src_name = agents_map.get(r["src_agent_id"], {}).get("name", "?")
            if r["dst_agent_id"]:
                dst_name = agents_map.get(r["dst_agent_id"], {}).get("name", "?")
                dst_display = f"{dst_name}:{r['target_port']}"
            else:
                dst_display = r["dst_addr"] or "?"

            lines.append(
                f"`#{r['id']}` {src_name}:`{r['listen_port']}` → "
                f"{dst_display} ({r['protocol']})"
            )

        embed = discord.Embed(
            title=f"📤 正向轉發規則 ({len(rules)})",
            description="\n".join(lines),
            color=0x3498DB,
        )

        await interaction.response.send_message(embed=embed)


async def setup(bot):
    await bot.add_cog(ForwardCog(bot))
