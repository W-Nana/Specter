# Specter Discord 命令模組
"""共享的 autocomplete 函數，供所有 cog 使用

調用鏈: Discord 用戶開始輸入 agent 名稱
        → Discord 發送 autocomplete 請求
        → agent_autocomplete() 查詢 DB
        → 返回匹配的 Agent 名稱列表
"""

import discord
from discord import app_commands


async def agent_autocomplete(
    interaction: discord.Interaction, current: str
) -> list[app_commands.Choice[str]]:
    """Agent 名稱自動補全

    從數據庫查詢所有 Agent，按用戶輸入過濾。
    Discord 限制最多返回 25 個選項。
    """
    db = interaction.client.db
    agents = await db.list_agents()

    choices = []
    for a in agents:
        # 按輸入前綴過濾（不區分大小寫）
        if current.lower() in a["name"].lower():
            # 顯示名稱 + 狀態提示
            label = a["name"]
            if a["status"] == "pending":
                label += " ⏳"
            choices.append(app_commands.Choice(name=label, value=a["name"]))

    # Discord 限制 25 個
    return choices[:25]
