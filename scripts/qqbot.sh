#!/usr/bin/env bash
# QQ 机器人后台管理脚本
# 用法: ./scripts/qqbot.sh start|stop|restart|status

set -e
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG_FILE="/tmp/qqbot.log"
PID_PATTERN="[q]qbot.main"

case "${1:-}" in
  start)
    if pgrep -f "$PID_PATTERN" > /dev/null; then
      echo "机器人已在运行: $(pgrep -f "$PID_PATTERN" | tr '\n' ' ')"
      exit 0
    fi
    cd "$PROJECT_ROOT"
    nohup uv run python -m qqbot.main > "$LOG_FILE" 2>&1 &
    echo "已启动 (PID: $!)，日志: $LOG_FILE"
    sleep 5
    tail -3 "$LOG_FILE"
    ;;
  stop)
    pkill -f "$PID_PATTERN" || echo "没有运行中的进程"
    ;;
  restart)
    "$0" stop
    sleep 2
    "$0" start
    ;;
  status)
    if pgrep -f "$PID_PATTERN" > /dev/null; then
      echo "运行中: $(pgrep -f "$PID_PATTERN" | tr '\n' ' ')"
      tail -3 "$LOG_FILE"
    else
      echo "未运行"
    fi
    ;;
  *)
    echo "用法: $0 {start|stop|restart|status}"
    exit 1
    ;;
esac
