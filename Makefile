# Specter 頂層 Makefile

.PHONY: agent master clean

# 編譯 Agent（所有架構）
agent:
	@echo "=== 編譯 Agent ==="
	cd agent && $(MAKE) all

# 安裝 Master 依賴
master:
	@echo "=== 安裝 Master 依賴 ==="
	pip install -r requirements.txt

# 啟動 Master（開發模式）
run-master:
	python -m master.bot

clean:
	cd agent && $(MAKE) clean
