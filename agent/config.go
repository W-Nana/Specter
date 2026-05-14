// Package main - Agent 配置讀寫
//
// Agent 的本地配置文件格式（/etc/specter/agent.conf）：
//   master_url=http://1.2.3.4:8080
//   agent_id=uuid
//   agent_token=permanent-token
//   poll_interval=10
//
// 調用鏈:
//   main() → LoadConfig() 讀取
//   runRegister() → SaveConfig() 寫入
package main

import (
	"bufio"
	"fmt"
	"os"
	"path/filepath"
	"strconv"
	"strings"
)

// AgentConfig Agent 本地配置
type AgentConfig struct {
	MasterURL    string // Master API 地址
	AgentID      string // Agent UUID
	AgentToken   string // 永久認證 token
	PollInterval int    // 心跳間隔（秒）
}

// LoadConfig 從文件載入配置
//
// 格式: key=value，每行一個，忽略空行和 # 開頭的註釋
func LoadConfig(path string) (*AgentConfig, error) {
	f, err := os.Open(path)
	if err != nil {
		return nil, fmt.Errorf("無法打開配置文件 %s: %w", path, err)
	}
	defer f.Close()

	cfg := &AgentConfig{
		PollInterval: 10, // 默認值
	}

	scanner := bufio.NewScanner(f)
	for scanner.Scan() {
		line := strings.TrimSpace(scanner.Text())
		// 跳過空行和註釋
		if line == "" || strings.HasPrefix(line, "#") {
			continue
		}

		parts := strings.SplitN(line, "=", 2)
		if len(parts) != 2 {
			continue
		}

		key := strings.TrimSpace(parts[0])
		val := strings.TrimSpace(parts[1])

		switch key {
		case "master_url":
			cfg.MasterURL = val
		case "agent_id":
			cfg.AgentID = val
		case "agent_token":
			cfg.AgentToken = val
		case "poll_interval":
			if n, err := strconv.Atoi(val); err == nil && n > 0 {
				cfg.PollInterval = n
			}
		}
	}

	// 驗證必填項
	if cfg.MasterURL == "" {
		return nil, fmt.Errorf("配置缺少 master_url")
	}
	if cfg.AgentID == "" {
		return nil, fmt.Errorf("配置缺少 agent_id")
	}
	if cfg.AgentToken == "" {
		return nil, fmt.Errorf("配置缺少 agent_token")
	}

	return cfg, nil
}

// SaveConfig 保存配置到文件
//
// 自動創建父目錄
func SaveConfig(path string, cfg *AgentConfig) error {
	// 創建父目錄
	dir := filepath.Dir(path)
	if err := os.MkdirAll(dir, 0755); err != nil {
		return fmt.Errorf("無法創建目錄 %s: %w", dir, err)
	}

	content := fmt.Sprintf(
		"# Specter Agent 配置（自動生成，請勿手動修改）\n"+
			"master_url=%s\n"+
			"agent_id=%s\n"+
			"agent_token=%s\n"+
			"poll_interval=%d\n",
		cfg.MasterURL, cfg.AgentID, cfg.AgentToken, cfg.PollInterval,
	)

	if err := os.WriteFile(path, []byte(content), 0600); err != nil {
		return fmt.Errorf("無法寫入配置文件 %s: %w", path, err)
	}

	return nil
}
