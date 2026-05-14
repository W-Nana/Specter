// Package main - Specter Agent
//
// 內嵌 GOST 模組的 Agent daemon，負責:
// 1. 向 Master 註冊（--register 模式）
// 2. 定期心跳：上報統計 + 拉取配置
// 3. 配置變更時重載 GOST 引擎
//
// 調用鏈:
//   main() → parseFlags()
//   --register 模式: client.Register() → 寫入配置文件 → 退出
//   daemon 模式: 主循環 → client.Heartbeat() → engine.Reload()
package main

import (
	"flag"
	"fmt"
	"log"
	"os"
	"os/signal"
	"syscall"
	"time"
)

// Version 由編譯時 ldflags 注入
var Version = "dev"

func main() {
	// === 命令行參數 ===
	var (
		registerMode bool
		masterURL    string
		token        string
		configPath   string
		showVersion  bool
	)

	flag.BoolVar(&registerMode, "register", false, "註冊模式：向 Master 註冊後退出")
	flag.StringVar(&masterURL, "master", "", "Master API 地址 (如 http://1.2.3.4:8080)")
	flag.StringVar(&token, "token", "", "一次性註冊 token")
	flag.StringVar(&configPath, "config", "/etc/specter/agent.conf", "Agent 配置文件路徑")
	flag.BoolVar(&showVersion, "version", false, "顯示版本")
	flag.Parse()

	if showVersion {
		fmt.Printf("specter-agent %s\n", Version)
		os.Exit(0)
	}

	// === 註冊模式 ===
	if registerMode {
		if masterURL == "" || token == "" {
			log.Fatal("註冊模式需要 --master 和 --token 參數")
		}
		runRegister(masterURL, token, configPath)
		return
	}

	// === Daemon 模式 ===
	cfg, err := LoadConfig(configPath)
	if err != nil {
		log.Fatalf("載入配置失敗: %v", err)
	}

	log.Printf("Specter Agent %s 啟動", Version)
	log.Printf("Master: %s | Agent: %s | 間隔: %ds",
		cfg.MasterURL, cfg.AgentID, cfg.PollInterval)

	// 初始化 GOST 引擎
	engine := NewEngine()

	// 初始化 Master 客戶端
	client := NewClient(cfg.MasterURL, cfg.AgentID, cfg.AgentToken)

	// 優雅關閉
	sigCh := make(chan os.Signal, 1)
	signal.Notify(sigCh, syscall.SIGINT, syscall.SIGTERM)

	// 啟動心跳循環
	ticker := time.NewTicker(time.Duration(cfg.PollInterval) * time.Second)
	defer ticker.Stop()

	// 啟動時立即執行一次心跳
	doHeartbeat(client, engine)

	for {
		select {
		case <-ticker.C:
			doHeartbeat(client, engine)

		case sig := <-sigCh:
			log.Printf("收到信號 %v，關閉中...", sig)
			engine.Stop()
			return
		}
	}
}

// runRegister 執行註冊流程
//
// 調用鏈: main() --register → Register() → SaveConfig()
func runRegister(masterURL, token, configPath string) {
	client := NewClient(masterURL, "", "")

	resp, err := client.Register(token)
	if err != nil {
		log.Fatalf("註冊失敗: %v", err)
	}

	// 保存配置
	cfg := &AgentConfig{
		MasterURL:    masterURL,
		AgentID:      resp.AgentID,
		AgentToken:   resp.AgentToken,
		PollInterval: resp.PollInterval,
	}

	if err := SaveConfig(configPath, cfg); err != nil {
		log.Fatalf("保存配置失敗: %v", err)
	}

	log.Printf("✅ 註冊成功！Agent ID: %s", resp.AgentID)
	log.Printf("配置已保存到: %s", configPath)
}

// doHeartbeat 執行一次心跳：上報統計 + 拉取配置
//
// 調用鏈: 主循環 → doHeartbeat() → client.Heartbeat() → engine.Reload()
func doHeartbeat(client *Client, engine *Engine) {
	// 收集當前 GOST 服務的統計信息
	stats := engine.Stats()

	// 發送心跳
	resp, err := client.Heartbeat(engine.ConfigHash(), stats)
	if err != nil {
		log.Printf("心跳失敗: %v", err)
		return
	}

	// 如果 Master 返回了新配置，重載 GOST 引擎
	if resp.Config != "" {
		log.Printf("收到新配置 (hash: %s)，重載中...", resp.ConfigHash[:8])
		if err := engine.Reload(resp.Config, resp.ConfigHash); err != nil {
			log.Printf("重載失敗: %v", err)
		} else {
			log.Printf("✅ GOST 配置已更新")
		}
	}

	// 更新心跳間隔（如果 Master 修改了）
	if resp.PollInterval > 0 {
		// TODO: 動態調整 ticker 間隔
		_ = resp.PollInterval
	}
}
