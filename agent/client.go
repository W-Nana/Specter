// Package main - Master HTTP 客戶端
//
// 封裝與 Master API 的所有 HTTP 通信。
// 純 net/http + encoding/json，零外部依賴。
//
// 調用鏈:
//   main() → NewClient()
//   註冊: client.Register(token) → POST /api/v1/register
//   心跳: client.Heartbeat(hash, stats) → POST /api/v1/heartbeat
package main

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"time"
)

// Client Master API 客戶端
type Client struct {
	masterURL  string
	agentID    string
	agentToken string
	httpClient *http.Client
}

// NewClient 創建客戶端
func NewClient(masterURL, agentID, agentToken string) *Client {
	return &Client{
		masterURL:  masterURL,
		agentID:    agentID,
		agentToken: agentToken,
		httpClient: &http.Client{
			Timeout: 15 * time.Second,
		},
	}
}

// ============================================================
// 請求/回應結構體
// ============================================================

// RegisterRequest 註冊請求
type RegisterRequest struct {
	Token string `json:"token"`
}

// RegisterResponse 註冊回應
type RegisterResponse struct {
	OK           bool   `json:"ok"`
	Error        string `json:"error,omitempty"`
	AgentID      string `json:"agent_id"`
	AgentToken   string `json:"agent_token"`
	PollInterval int    `json:"poll_interval"`
}

// HeartbeatRequest 心跳請求
type HeartbeatRequest struct {
	AgentID    string         `json:"agent_id"`
	AgentToken string         `json:"agent_token"`
	ConfigHash string         `json:"config_hash"`
	Stats      []ServiceStats `json:"stats"`
}

// HeartbeatResponse 心跳回應
type HeartbeatResponse struct {
	OK           bool   `json:"ok"`
	Error        string `json:"error,omitempty"`
	Config       string `json:"config"`       // GOST YAML 配置（為空表示無需更新）
	ConfigHash   string `json:"config_hash"`  // 新配置的 hash
	PollInterval int    `json:"poll_interval"`
}

// ServiceStats 單個 GOST service 的統計信息
type ServiceStats struct {
	Service      string `json:"service"`
	TotalConns   int64  `json:"totalConns"`
	CurrentConns int64  `json:"currentConns"`
	InputBytes   int64  `json:"inputBytes"`
	OutputBytes  int64  `json:"outputBytes"`
	TotalErrs    int64  `json:"totalErrs"`
}

// ============================================================
// API 調用
// ============================================================

// Register 向 Master 註冊
//
// 調用鏈: main() --register → Register() → POST /api/v1/register
func (c *Client) Register(token string) (*RegisterResponse, error) {
	req := RegisterRequest{Token: token}

	var resp RegisterResponse
	if err := c.post("/api/v1/register", req, &resp); err != nil {
		return nil, err
	}

	if !resp.OK {
		return nil, fmt.Errorf("註冊被拒絕: %s", resp.Error)
	}

	return &resp, nil
}

// Heartbeat 發送心跳
//
// 調用鏈: doHeartbeat() → Heartbeat() → POST /api/v1/heartbeat
func (c *Client) Heartbeat(configHash string, stats []ServiceStats) (*HeartbeatResponse, error) {
	req := HeartbeatRequest{
		AgentID:    c.agentID,
		AgentToken: c.agentToken,
		ConfigHash: configHash,
		Stats:      stats,
	}

	var resp HeartbeatResponse
	if err := c.post("/api/v1/heartbeat", req, &resp); err != nil {
		return nil, err
	}

	if !resp.OK {
		return nil, fmt.Errorf("心跳被拒絕: %s", resp.Error)
	}

	return &resp, nil
}

// ============================================================
// 內部 HTTP 工具
// ============================================================

// post 發送 JSON POST 請求
func (c *Client) post(path string, body interface{}, result interface{}) error {
	data, err := json.Marshal(body)
	if err != nil {
		return fmt.Errorf("序列化請求失敗: %w", err)
	}

	url := c.masterURL + path
	req, err := http.NewRequest("POST", url, bytes.NewReader(data))
	if err != nil {
		return fmt.Errorf("創建請求失敗: %w", err)
	}
	req.Header.Set("Content-Type", "application/json")

	resp, err := c.httpClient.Do(req)
	if err != nil {
		return fmt.Errorf("請求 %s 失敗: %w", url, err)
	}
	defer resp.Body.Close()

	respBody, err := io.ReadAll(resp.Body)
	if err != nil {
		return fmt.Errorf("讀取回應失敗: %w", err)
	}

	if resp.StatusCode >= 400 {
		return fmt.Errorf("HTTP %d: %s", resp.StatusCode, string(respBody))
	}

	if err := json.Unmarshal(respBody, result); err != nil {
		return fmt.Errorf("解析回應失敗: %w", err)
	}

	return nil
}
