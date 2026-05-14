// Package main - GOST 引擎管理
//
// 內嵌 GOST 的核心：解析 YAML 配置 → 創建/銷毀 GOST services。
// 直接使用 go-gost/x 的 config、loader、registry 模組。
//
// 調用鏈:
//   main() → NewEngine()
//   doHeartbeat() → engine.Reload(yaml, hash) 重載配置
//   doHeartbeat() → engine.Stats() 採集統計
//   main() SIGTERM → engine.Stop() 關閉所有服務
package main

import (
	"crypto/md5"
	"fmt"
	"log"
	"sync"

	"github.com/go-gost/core/logger"
	"github.com/go-gost/core/service"
	"github.com/go-gost/x/config"
	"github.com/go-gost/x/config/loader"
	xlogger "github.com/go-gost/x/logger"
	"github.com/go-gost/x/registry"
	"gopkg.in/yaml.v3"
)

// Engine 管理內嵌 GOST 的服務生命週期
type Engine struct {
	mu         sync.Mutex
	configHash string           // 當前配置的 MD5
	services   []service.Service // 當前運行的 GOST services
}

// NewEngine 創建 GOST 引擎
func NewEngine() *Engine {
	// 初始化 GOST 日誌
	log := xlogger.NewLogger()
	logger.SetDefault(log)

	return &Engine{}
}

// ConfigHash 返回當前配置的 hash
func (e *Engine) ConfigHash() string {
	e.mu.Lock()
	defer e.mu.Unlock()
	return e.configHash
}

// Reload 重載 GOST 配置
//
// 流程:
//   1. 解析 YAML → config.Config
//   2. 停止所有現有服務
//   3. 清空全局 registry
//   4. 用 loader.Load() 註冊新的服務/鏈/等組件
//   5. 啟動所有新服務
//
// 調用鏈: doHeartbeat() → Reload()
func (e *Engine) Reload(yamlConfig string, hash string) error {
	e.mu.Lock()
	defer e.mu.Unlock()

	// 解析 YAML 為 GOST 配置結構
	cfg := &config.Config{}
	if err := yaml.Unmarshal([]byte(yamlConfig), cfg); err != nil {
		return fmt.Errorf("解析 GOST 配置失敗: %w", err)
	}

	// 停止所有現有服務
	e.stopServicesLocked()

	// 設定全局配置
	config.Set(cfg)

	// 用 loader 將配置註冊到全局 registry
	// loader.Load() 會：
	//   - 清空並重新註冊所有 chains、services、等組件
	//   - 解析配置生成運行時對象
	if err := loader.Load(cfg); err != nil {
		return fmt.Errorf("載入 GOST 配置失敗: %w", err)
	}

	// 啟動所有已註冊的服務
	var newServices []service.Service
	for _, svc := range registry.ServiceRegistry().GetAll() {
		svc := svc
		go func() {
			if err := svc.Serve(); err != nil {
				log.Printf("服務異常退出: %v", err)
			}
		}()
		newServices = append(newServices, svc)
	}

	e.services = newServices
	e.configHash = hash

	log.Printf("GOST 引擎重載完成: %d 個服務", len(newServices))
	return nil
}

// Stop 停止所有 GOST 服務
//
// 調用鏈: main() SIGTERM → Stop()
func (e *Engine) Stop() {
	e.mu.Lock()
	defer e.mu.Unlock()
	e.stopServicesLocked()
	log.Printf("GOST 引擎已停止")
}

// stopServicesLocked 停止所有服務（需持有鎖）
func (e *Engine) stopServicesLocked() {
	// 關閉 registry 中的所有服務
	for name, svc := range registry.ServiceRegistry().GetAll() {
		svc.Close()
		registry.ServiceRegistry().Unregister(name)
	}
	e.services = nil
}

// Stats 採集所有 GOST 服務的統計信息
//
// 調用鏈: doHeartbeat() → Stats()
//
// 從 registry 中遍歷所有服務，
// 通過 GOST 的 config.Get() 讀取當前配置中的 status.stats
func (e *Engine) Stats() []ServiceStats {
	e.mu.Lock()
	defer e.mu.Unlock()

	var result []ServiceStats

	// 從全局配置中讀取服務狀態
	cfg := config.Global()
	if cfg == nil {
		return result
	}

	for _, svcCfg := range cfg.Services {
		if svcCfg.Status == nil || svcCfg.Status.Stats == nil {
			continue
		}
		s := svcCfg.Status.Stats
		result = append(result, ServiceStats{
			Service:      svcCfg.Name,
			TotalConns:   int64(s.TotalConns),
			CurrentConns: int64(s.CurrentConns),
			InputBytes:   int64(s.InputBytes),
			OutputBytes:  int64(s.OutputBytes),
			TotalErrs:    int64(s.TotalErrs),
		})
	}

	return result
}

// computeHash 計算字符串的 MD5 hash
func computeHash(s string) string {
	return fmt.Sprintf("%x", md5.Sum([]byte(s)))
}
