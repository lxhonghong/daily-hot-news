#!/bin/bash
# 一键启动 RSSHub Docker 容器
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

# 加载 .env 文件中的环境变量
if [ -f "$PROJECT_DIR/.env" ]; then
    set -a
    source "$PROJECT_DIR/.env"
    set +a
fi

echo "🚀 启动 RSSHub Docker 容器..."
docker compose -f "$PROJECT_DIR/docker-compose.rsshub.yml" up -d

echo "⏳ 等待 RSSHub 就绪..."
MAX_WAIT=60
WAITED=0
while [ $WAITED -lt $MAX_WAIT ]; do
    if curl -s -o /dev/null -w "%{http_code}" http://localhost:1200/ | grep -q "200"; then
        echo "✅ RSSHub 已就绪 (http://localhost:1200)"
        echo ""
        echo "验证关键路由..."
        ROUTES=(
            "/36kr/hot-list/24"
            "/qbitai/category/资讯"
            "/hackernews/best"
            "/zhihu/hot"
            "/thepaper/featured"
            "/reuters/world"
            "/bbc/chinese"
        )
        for route in "${ROUTES[@]}"; do
            STATUS=$(curl -s -o /dev/null -w "%{http_code}" "http://localhost:1200${route}" --max-time 10)
            if [ "$STATUS" = "200" ]; then
                echo "  ✅ $route"
            else
                echo "  ❌ $route (HTTP $STATUS)"
            fi
        done
        exit 0
    fi
    sleep 2
    WAITED=$((WAITED + 2))
done

echo "❌ RSSHub 启动超时（${MAX_WAIT}秒），请检查 Docker 日志："
echo "   docker compose -f $PROJECT_DIR/docker-compose.rsshub.yml logs"
exit 1
