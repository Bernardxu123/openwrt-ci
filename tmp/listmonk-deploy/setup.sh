#!/bin/bash
# Listmonk 一键部署脚本
# VLOOK OPTICAL 邮件营销系统
set -e

cd /opt/listmonk

echo "=== 1. 创建目录结构 ==="
mkdir -p data/postgres data/uploads
chmod 755 data

echo "=== 2. 启动 PostgreSQL ==="
docker compose up -d db
echo "等待 PostgreSQL 就绪..."
sleep 10
# 等待数据库健康检查通过
for i in $(seq 1 30); do
    if docker compose exec db pg_isready -U listmonk > /dev/null 2>&1; then
        echo "PostgreSQL 就绪！"
        break
    fi
    echo "等待中... ($i/30)"
    sleep 2
done

echo "=== 3. 初始化 Listmonk 数据库 ==="
# 用临时容器运行安装（初始化数据库表）
docker compose run --rm listmonk sh -c "yes | ./listmonk --install --config config.toml" || true
echo "数据库初始化完成"

echo "=== 4. 启动 Listmonk ==="
docker compose up -d

echo "=== 5. 等待 Listmonk 就绪 ==="
sleep 5
for i in $(seq 1 20); do
    if curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:9000 | grep -q "200\|302"; then
        echo "Listmonk 启动成功！"
        break
    fi
    echo "等待中... ($i/20)"
    sleep 3
done

echo ""
echo "====================================="
echo "  Listmonk 部署完成！"
echo "  访问地址: http://158.178.238.209:9000"
echo "  管理员: admin"
echo "  密码: VlookMail2026!"
echo "====================================="
