#!/bin/bash
# Specter Agent 安裝/更新/卸載腳本
#
# 安裝（由 /agent create 命令生成）:
#   curl -sSL .../install.sh | bash -s -- --master http://IP:PORT --token TOKEN
#
# 更新:
#   curl -sSL .../install.sh | bash -s -- --update
#
# 卸載:
#   curl -sSL .../install.sh | bash -s -- --uninstall

set -e

# ============================================================
# 顏色輸出
# ============================================================
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

info()  { echo -e "${GREEN}[INFO]${NC} $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*"; exit 1; }

# ============================================================
# 常量
# ============================================================
INSTALL_DIR="/usr/local/bin"
CONFIG_DIR="/etc/specter"
SERVICE_NAME="specter-agent"
BINARY_NAME="specter-agent"
GITHUB_REPO="W-Nana/Specter"

# ============================================================
# 參數解析
# ============================================================
MODE="install"
MASTER_URL=""
REG_TOKEN=""

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
        --update)
            MODE="update"
            shift
            ;;
        --uninstall)
            MODE="uninstall"
            shift
            ;;
        *)
            error "未知參數: $1\n用法:\n  安裝: --master URL --token TOKEN\n  更新: --update\n  卸載: --uninstall"
            ;;
    esac
done

# ============================================================
# 架構檢測
# ============================================================
detect_arch() {
    local arch
    arch=$(uname -m)
    case "$arch" in
        x86_64|amd64)   echo "linux-amd64" ;;
        aarch64|arm64)   echo "linux-arm64" ;;
        armv7l|armhf)    echo "linux-armv7" ;;
        *)               error "不支持的架構: $arch" ;;
    esac
}

# ============================================================
# 下載二進制
# ============================================================
download_binary() {
    local arch="$1"
    local download_url="https://github.com/${GITHUB_REPO}/releases/latest/download/${BINARY_NAME}-${arch}"

    info "下載 ${BINARY_NAME} (${arch})..."

    if command -v curl &>/dev/null; then
        curl -sSL -o /tmp/${BINARY_NAME} "$download_url" || error "下載失敗: $download_url"
    elif command -v wget &>/dev/null; then
        wget -qO /tmp/${BINARY_NAME} "$download_url" || error "下載失敗: $download_url"
    else
        error "需要 curl 或 wget"
    fi

    chmod +x /tmp/${BINARY_NAME}
}

# ============================================================
# 安裝模式
# ============================================================
do_install() {
    if [ -z "$MASTER_URL" ] || [ -z "$REG_TOKEN" ]; then
        error "安裝模式需要 --master 和 --token 參數"
    fi

    local arch
    arch=$(detect_arch)
    info "檢測到架構: $arch"

    # 下載二進制
    download_binary "$arch"
    mv /tmp/${BINARY_NAME} "${INSTALL_DIR}/${BINARY_NAME}"
    info "已安裝到 ${INSTALL_DIR}/${BINARY_NAME}"

    # 向 Master 註冊
    info "向 Master 註冊..."
    mkdir -p "$CONFIG_DIR"

    "${INSTALL_DIR}/${BINARY_NAME}" --register \
        --master "$MASTER_URL" \
        --token "$REG_TOKEN" \
        --config "${CONFIG_DIR}/agent.conf"

    if [ $? -ne 0 ]; then
        error "註冊失敗"
    fi
    info "註冊成功"

    # 部署 systemd 服務
    info "部署 systemd 服務..."
    cat > /etc/systemd/system/${SERVICE_NAME}.service << 'EOF'
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
    systemctl enable ${SERVICE_NAME}
    systemctl start ${SERVICE_NAME}

    echo ""
    info "========================================="
    info "  Specter Agent 安裝完成！"
    info "========================================="
    info "  二進制: ${INSTALL_DIR}/${BINARY_NAME}"
    info "  配置:   ${CONFIG_DIR}/agent.conf"
    info "  服務:   ${SERVICE_NAME}.service"
    info ""
    info "  查看狀態: systemctl status ${SERVICE_NAME}"
    info "  查看日誌: journalctl -u ${SERVICE_NAME} -f"
    info "========================================="
}

# ============================================================
# 更新模式
# ============================================================
do_update() {
    if [ ! -f "${INSTALL_DIR}/${BINARY_NAME}" ]; then
        error "未找到已安裝的 ${BINARY_NAME}，請先執行安裝"
    fi

    # 記錄舊版本
    local old_version
    old_version=$("${INSTALL_DIR}/${BINARY_NAME}" --version 2>&1 || echo "unknown")
    info "當前版本: ${old_version}"

    local arch
    arch=$(detect_arch)

    # 下載新版本
    download_binary "$arch"

    # 記錄新版本
    local new_version
    new_version=$(/tmp/${BINARY_NAME} --version 2>&1 || echo "unknown")
    info "新版本: ${new_version}"

    if [ "$old_version" = "$new_version" ]; then
        info "已是最新版本，無需更新"
        rm -f /tmp/${BINARY_NAME}
        return
    fi

    # 停止服務 → 替換二進制 → 啟動服務
    info "停止服務..."
    systemctl stop ${SERVICE_NAME} 2>/dev/null || true

    mv /tmp/${BINARY_NAME} "${INSTALL_DIR}/${BINARY_NAME}"

    info "啟動服務..."
    systemctl start ${SERVICE_NAME}

    info "========================================="
    info "  更新完成: ${old_version} → ${new_version}"
    info "========================================="
}

# ============================================================
# 卸載模式
# ============================================================
do_uninstall() {
    info "卸載 Specter Agent..."

    # 停止並禁用服務
    if systemctl is-active --quiet ${SERVICE_NAME} 2>/dev/null; then
        info "停止服務..."
        systemctl stop ${SERVICE_NAME}
    fi
    if systemctl is-enabled --quiet ${SERVICE_NAME} 2>/dev/null; then
        systemctl disable ${SERVICE_NAME}
    fi

    # 刪除 systemd unit
    rm -f /etc/systemd/system/${SERVICE_NAME}.service
    systemctl daemon-reload

    # 刪除二進制
    rm -f "${INSTALL_DIR}/${BINARY_NAME}"

    # 刪除配置（詢問用戶）
    if [ -d "$CONFIG_DIR" ]; then
        read -p "是否刪除配置目錄 ${CONFIG_DIR}? [y/N] " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            rm -rf "$CONFIG_DIR"
            info "配置已刪除"
        else
            info "配置已保留在 ${CONFIG_DIR}"
        fi
    fi

    info "========================================="
    info "  Specter Agent 已卸載"
    info "========================================="
}

# ============================================================
# 執行
# ============================================================
case "$MODE" in
    install)   do_install ;;
    update)    do_update ;;
    uninstall) do_uninstall ;;
esac
