#!/bin/bash
# nanobot Gateway 看门狗脚本 - 监控并自动重启 nanobot Gateway
# 注意：nanobot Gateway 不是 HTTP 服务，不监听端口，只检查进程是否存在

NANOBOT_DIR="$HOME/.nanobot"
VENV_DIR="$NANOBOT_DIR/venv"
LOG_FILE="$NANOBOT_DIR/logs/gateway.log"
PORT=18799
MAX_LOG_AGE=180  # 5 分钟无新日志视为假死

# 确保 PATH 包含系统目录
export PATH="/usr/bin:/usr/sbin:/bin:/usr/local/bin:$PATH"

# 检查 nanobot Gateway 进程
check_gateway() {
    # 1. 检查进程是否存在
    GATEWAY_PID=$(pgrep -f "nanobot gateway.*--port $PORT" | head -1)
    if [ -z "$GATEWAY_PID" ]; then
        echo "[$(date)] ❌ nanobot Gateway 进程不存在"
        return 1
    fi
    
    # 2. 检查进程是否存活
    if ! ps -p "$GATEWAY_PID" > /dev/null 2>&1; then
        echo "[$(date)] ❌ nanobot Gateway 进程已退出 (PID: $GATEWAY_PID)"
        return 1
    fi
    
    # 3. 检查日志是否更新（避免假死）
    if [ -f "$LOG_FILE" ]; then
        LOG_AGE=$(($(date +%s) - $(stat -f %m "$LOG_FILE" 2>/dev/null || echo 0)))
        if [ $LOG_AGE -gt $MAX_LOG_AGE ]; then
            echo "[$(date)] ❌ nanobot Gateway 日志 $LOG_AGE 秒未更新（假死）"
            return 1
        fi
    fi
    
    echo "[$(date)] ✅ nanobot Gateway 正常 (PID: $GATEWAY_PID)"
    return 0
}

# 重启 nanobot Gateway
restart_gateway() {
    echo "[$(date)] 🔄 重启 nanobot Gateway..."
    
    # 停止旧进程
    pkill -9 -f "nanobot gateway" 2>/dev/null
    sleep 2
    
    # 清理端口（使用 lsof 完整路径）
    /usr/sbin/lsof -ti :$PORT | xargs kill -9 2>/dev/null || true
    sleep 2
    
    # 确保日志目录存在
    mkdir -p "$NANOBOT_DIR/logs"
    
    # 启动新网关（使用虚拟环境）
    cd "$NANOBOT_DIR"
    source "$VENV_DIR/bin/activate"
    nohup nanobot gateway --port $PORT > "$LOG_FILE" 2>&1 &
    deactivate
    
    sleep 5
    
    # 验证启动
    GATEWAY_PID=$(pgrep -f "nanobot gateway" | head -1)
    if [ -n "$GATEWAY_PID" ]; then
        echo "[$(date)] ✅ nanobot Gateway 重启成功 (PID: $GATEWAY_PID)"
        return 0
    else
        echo "[$(date)] ❌ nanobot Gateway 重启失败"
        return 1
    fi
}

# 主循环
main() {
    echo "[$(date)] 🐶 nanobot Gateway 看门狗启动"
    
    while true; do
        if ! check_gateway; then
            restart_gateway
        fi
        sleep 60  # 每分钟检查一次
    done
}

main
