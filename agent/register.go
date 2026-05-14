// Package main - GOST 組件註冊
//
// GOST 的 handler/listener/connector/dialer 類型通過 Go init() 函數自動註冊。
// 必須 blank import 需要的包，否則 loader.Load() 會報 "unknown listener/handler"。
//
// 只 import Specter 實際用到的組件，不拉整個 GOST：
//   - tcp/udp listener + forward/local handler: 正向轉發
//   - rtcp/rudp listener + forward/remote handler: 反向隧道客戶端
//   - relay handler + connector: 反向隧道的 relay 入口
//   - tcp/direct dialer + connector: chain 中的連接組件
package main

import (
	// === Listeners ===
	_ "github.com/go-gost/x/listener/tcp"  // 正向轉發：TCP 監聽
	_ "github.com/go-gost/x/listener/udp"  // 正向轉發：UDP 監聽
	_ "github.com/go-gost/x/listener/rtcp" // 反向隧道：RTCP 監聽
	_ "github.com/go-gost/x/listener/rudp" // 反向隧道：RUDP 監聽

	// === Handlers ===
	_ "github.com/go-gost/x/handler/forward/local"  // 註冊 "tcp", "udp", "forward" handler
	_ "github.com/go-gost/x/handler/forward/remote" // 註冊 "rtcp", "rudp" handler
	_ "github.com/go-gost/x/handler/relay"          // relay handler（公網方入口）

	// === Connectors ===
	_ "github.com/go-gost/x/connector/direct"  // 直連 connector
	_ "github.com/go-gost/x/connector/forward" // forward connector
	_ "github.com/go-gost/x/connector/relay"   // relay connector（NAT 方連 relay 入口）

	// === Dialers ===
	_ "github.com/go-gost/x/dialer/direct" // 直連 dialer
	_ "github.com/go-gost/x/dialer/tcp"    // TCP dialer（chain 中用）
	_ "github.com/go-gost/x/dialer/udp"    // UDP dialer
)
