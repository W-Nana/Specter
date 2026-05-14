# Specter Agent 交叉編譯 Makefile

BINARY = specter-agent
VERSION ?= $(shell git describe --tags --always 2>/dev/null || echo "dev")
LDFLAGS = -s -w -X main.Version=$(VERSION)

.PHONY: all clean linux-amd64 linux-arm64 linux-armv7

all: linux-amd64 linux-arm64 linux-armv7

linux-amd64:
	@echo "🔨 編譯 linux/amd64..."
	GOOS=linux GOARCH=amd64 CGO_ENABLED=0 go build -ldflags "$(LDFLAGS)" -o dist/$(BINARY)-linux-amd64 .

linux-arm64:
	@echo "🔨 編譯 linux/arm64..."
	GOOS=linux GOARCH=arm64 CGO_ENABLED=0 go build -ldflags "$(LDFLAGS)" -o dist/$(BINARY)-linux-arm64 .

linux-armv7:
	@echo "🔨 編譯 linux/armv7..."
	GOOS=linux GOARCH=arm GOARM=7 CGO_ENABLED=0 go build -ldflags "$(LDFLAGS)" -o dist/$(BINARY)-linux-armv7 .

clean:
	rm -rf dist/
