#!/bin/bash
# Specter Agent 一鍵安裝腳本
#
# 用法（由 /agent create 命令生成）:
#   curl -sSL https://raw.githubusercontent.com/W-Nana/Specter/main/install.sh \
#     | bash -s -- --master http://MASTER_IP:PORT --token TOKEN
#
# 流程:
#   1. 解析參數
#   2. 檢測系統架構
#   3. 下載 specter-agent 二進制
#   4. 向 Master 註冊
#   5. 部署 systemd 服務
#   6. 啟動

set -e

# ============================================================
# 顏色輸出
# ============================================================
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

info()  { echo -e "${GREEN}[INFO]${NC} $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*"; exit 1; }

# ============================================================
# 參數解析
# ============================================================
MASTER_URL=""
REG_TOKEN=""
INSTALL_DIR="/usr/local/bin"
CONFIG_DIR="/etc/specter"
GITHUB_REPO="W-Nana/Specter"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --master)
            MASTER_URL="$2"
            shift 2
            ;;
        --token)
            REG_TOKEN="$2"
            shift 2
            ;;
        *)
            error "未知參數: $1"
            ;;
    esac
done

if [ -z "$MASTER_URL" ] || [ -z "$REG_TOKEN" ]; then
    error "用法: install.sh --master http://IP:PORT --token TOKEN"
fi

# ============================================================
# 檢測架構
# ============================================================
detect_arch() {
    local arch
    arch=$(uname -m)
    case "$arch" in
        x86_64|amd64)
            echo "linux-amd64"
            ;;
        aarch64|arm64)
            echo "linux-arm64"
            ;;
        armv7l|armhf)
            echo "linux-armv7"
            ;;
        *)
            error "不支持的架構: $arch"
            ;;
    esac
}

ARCH=$(detect_arch)
info "檢測到架構: $ARCH"

# ============================================================
# 下載二進制
# ============================================================
info "下載 specter-agent..."

# 嘗試從 GitHub Release 下載
DOWNLOAD_URL="https://github.com/${GITHUB_REPO}/releases/latest/download/specter-agent-${ARCH}"

if command -v curl &>/dev/null; then
    curl -sSL -o /tmp/specter-agent "$DOWNLOAD_URL" || error "下載失敗: $DOWNLOAD_URL"
elif command -v wget &>/dev/null; then
    wget -qO /tmp/specter-agent "$DOWNLOAD_URL" || error "下載失敗: $DOWNLOAD_URL"
else
    error "需要 curl 或 wget"
fi

chmod +x /tmp/specter-agent
mv /tmp/specter-agent "${INSTALL_DIR}/specter-agent"
info "已安裝到 ${INSTALL_DIR}/specter-agent"

# ============================================================
# 向 Master 註冊
# ============================================================
info "向 Master 註冊..."
mkdir -p "$CONFIG_DIR"

"${INSTALL_DIR}/specter-agent" --register \
    --master "$MASTER_URL" \
    --token "$REG_TOKEN" \
    --config "${CONFIG_DIR}/agent.conf"

if [ $? -ne 0 ]; then
    error "註冊失敗"
fi

info "註冊成功"

# ============================================================
# 部署 systemd 服務
# ============================================================
info "部署 systemd 服務..."

cat > /etc/systemd/system/specter-agent.service << 'EOF'
[Unit]
Description=Specter Agent (GOST Tunnel Manager)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
ExecStart=/usr/local/bin/specter-agent --config /etc/specter/agent.conf
Restart=always
RestartSec=5
LimitNOFILE=65536
NoNewPrivileges=true

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable specter-agent
systemctl start specter-agent

# ============================================================
# 完成
# ============================================================
echo ""
info "========================================="
info "  Specter Agent 安裝完成！"
info "========================================="
info "  二進制: ${INSTALL_DIR}/specter-agent"
info "  配置:   ${CONFIG_DIR}/agent.conf"
info "  服務:   specter-agent.service"
info ""
info "  查看狀態: systemctl status specter-agent"
info "  查看日誌: journalctl -u specter-agent -f"
info "========================================="
