#!/bin/bash
set -e

echo "=========================================="
echo "Flow2API Token Updater v2.0"
echo "多 Profile 管理版"
echo "=========================================="
echo ""
echo "管理界面: http://localhost:8080"
echo "noVNC:    http://localhost:${NOVNC_PORT:-6080}/vnc.html"
echo "VNC 密码: ${VNC_PASSWORD:-flow2api}"
echo ""
echo "=========================================="

# 确保目录存在
mkdir -p /app/logs /app/profiles /app/data

# 启动 supervisor
exec /usr/bin/supervisord -c /etc/supervisor/conf.d/supervisord.conf
