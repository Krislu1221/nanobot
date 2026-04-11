#!/bin/bash
# nanobot Gateway 看门狗脚本 - 监控并自动重启

NANOBOT_DIR="$HOME/nanobot"
LOG_FILE="$HOME/nanobot/logs/gateway.log"
PORT=18799
MAX_LOG_AGE=300  # 5 分钟无新日志视为假死

# 检查 nanobot Gateway 进程
check_gateway() {
    # 1. 检查进程是否存在
    GATEWAY_PID=$(pgrep -f "nanobot gateway" | head -1)
    if [ -z "$GATEWAY_PID" ]; then
        echo "[$(date)] ❌ nanobot Gateway 进程不存在"
        return 1
    fi
    
    # 2. 检查日志是否更新（避免假死）
    if [ -f "$LOG_FILE" ]; then
        LOG_AGE=$(($(date +%s) - $(stat -f %m "$LOG_FILE" 2>/dev/null || echo 0)))
        if [ $LOG_AGE -gt $MAX_LOG_AGE ]; then
            echo "[$(date)] ❌ nanobot 日志 $LOG_AGE 秒未更新（假死）"
            return 1
        fi
    fi
    
    # 3. 检查进程是否存活
    if ! kill -0 "$GATEWAY_PID" 2>/dev/null; then
        echo "[$(date)] ❌ nanobot Gateway 进程已死亡 (PID: $GATEWAY_PID)"
        return 1
    fi
    
    echo "[$(date)] ✅ nanobot Gateway 正常 (PID: $GATEWAY_PID)"
    return 0
}

# 重启 nanobot Gateway
restart_gateway() {
    echo "[$(date)] 🔄 重启 nanobot Gateway..."
    
    # 停止旧进程
    pkill -9 -f "nanobot gateway" 2>/dev/null
    sleep 3
    
    # 创建日志目录
    mkdir -p "$NANOBOT_DIR/logs"
    
    # 启动新网关
    cd "$NANOBOT_DIR"
    source venv/bin/activate
    nohup nanobot gateway --port $PORT > "$LOG_FILE" 2>&1 &
    
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

# 发送飞书通知（可选）
notify_restart() {
    local reason="$1"
    # 如果有飞书 webhook，可以在这里发送通知
    # curl -X POST -H "Content-Type: application/json" -d "{\"text\":\"🐶 nanobot 重启：$reason\"}" "$WEBHOOK_URL"
    echo "[$(date)] 📢 通知：nanobot 因 $reason 重启"
}

# 主循环
main() {
    echo "[$(date)] 🐶 nanobot Gateway 看门狗启动 (launchd 管理)"
    
    while true; do
        if ! check_gateway; then
            local reason="健康检查失败"
            notify_restart "$reason"
            restart_gateway
        fi
        sleep 30  # 每30秒检查一次
    done
}

main
