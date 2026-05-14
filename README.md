# Specter

Discord Bot 驅動的 GOST 隧道管理系統。通過 Discord 命令集中管理多台 Agent 上的 GOST 轉發規則。

## 架構

```
Master (Python)                     Agent (Go 單一二進制)
┌──────────────────────┐           ┌─────────────────────────┐
│ Discord Bot          │           │ 內嵌 GOST 引擎          │
│ HTTP API             │◄──────────│ 定期心跳 + 配置拉取      │
│ SQLite DB            │           │ 流量統計上報             │
└──────────────────────┘           └─────────────────────────┘
```

- **Agent 主動拉取**：Agent 不開放任何端口，定期向 Master 心跳並拉取配置
- **Go 單一二進制**：Agent 內嵌 GOST 模組，零依賴部署
- **兩種轉發模型**：正向轉發 (A→B) 和反向隧道 (B 連接 A)

## 快速開始

### 1. 部署 Master

```bash
cd master
cp ../.env.example .env
# 編輯 .env，填入 Discord Bot Token 等配置
pip install -r ../requirements.txt
python -m master.bot
```

### 2. 添加 Agent

在 Discord 中執行：
```
/agent_create us-west-1
```

Bot 會返回一鍵安裝命令。

### 3. 安裝 Agent

在目標 VPS 上執行安裝命令：
```bash
curl -sSL https://raw.githubusercontent.com/W-Nana/Specter/main/install.sh \
  | bash -s -- --master http://MASTER_IP:8080 --token <TOKEN>
```

### 4. 創建轉發規則

```
# 正向轉發：AgentA:8080 → 1.2.3.4:80
/forward_add AgentA 8080 1.2.3.4:80

# 反向隧道：AgentA:2222 ← 隧道 ← AgentB:22
/tunnel_add AgentB AgentA 2222 22

# 查看流量統計
/stats AgentA
```

## Discord 命令

| 命令 | 說明 |
|------|------|
| `/agent_create <name>` | 創建 Agent + 生成安裝命令 |
| `/agent_list` | 列出所有 Agent |
| `/agent_remove <name>` | 移除 Agent |
| `/agent_rename <old> <new>` | 重命名 |
| `/agent_interval <name> <secs>` | 設定心跳間隔 |
| `/forward_add <agent> <port> <target>` | 正向轉發 (target=IP:port) |
| `/forward_remove <id>` | 刪除轉發 |
| `/forward_list [agent]` | 列出轉發 |
| `/tunnel_add <nat> <pub> <pub_port> <local_port>` | 反向隧道 |
| `/tunnel_remove <id>` | 刪除隧道 |
| `/tunnel_list [agent]` | 列出隧道 |
| `/stats <agent>` | 流量統計 |
| `/stats_summary` | 全局匯總 |

## 編譯 Agent

```bash
cd agent
make all  # 編譯 amd64/arm64/armv7
```

## 項目結構

```
Specter/
├── master/              # Python: Discord Bot + HTTP API
│   ├── bot.py           # 入口
│   ├── config.py        # 配置
│   ├── database.py      # SQLite
│   ├── server.py        # Agent HTTP API
│   ├── gost_builder.py  # GOST 配置生成
│   └── cogs/            # Discord 命令
├── agent/               # Go: 內嵌 GOST 的 Agent
│   ├── main.go          # 入口
│   ├── client.go        # Master 客戶端
│   ├── engine.go        # GOST 引擎
│   └── config.go        # 配置讀寫
├── install.sh           # 一鍵安裝
└── systemd/             # systemd unit
```

## License

MIT
