# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 常用命令

```bash
# 激活虚拟环境
source .venv/bin/activate

# 运行完整日报生成流程（采集→去重→LLM摘要→渲染→推送）
python -m src.main

# 单独测试采集（不调用 LLM，快速验证数据源可用性）
python scripts/test_collect.py

# 本地预览生成的页面
open output/index.html

# 启动 RSSHub Docker（国内数据源依赖）
docker compose -f docker-compose.rsshub.yml up -d

# 验证 RSSHub 路由可用性
bash scripts/setup_rsshub.sh
```

## 架构概览

流水线：**采集 → 去重 → LLM 摘要+影响分析 → HTML 渲染 → Git 推送 → Cloudflare 自动部署**

### 采集层 (`src/collectors/`)

三个采集器并行运行，各自返回 `dict[Category, list[RawItem]]`：

- **rss_collector.py**：httpx 并发采集所有 RSS/Atom feeds。国内源直连 RSSHub Docker (localhost:1200)，国际源走宿主机代理 (`settings.http_proxy`)。`FeedSource.needs_proxy` 控制走哪个 httpx client。
- **currents.py**：CurrentsAPI REST 搜索，每个方向一次查询，全走代理。
- **github_trending.py**：CDN JSON 直取 (isboyjc/github-trending-api) + GitHub Search API。Trending CDN 返回的 JSON 顶层是 `{"items": [...]}` 而非裸数组，解析时需兼容两种格式。

### 处理层 (`src/processor/`)

- **llm.py**：Anthropic SDK 封装，`base_url=https://www.huolilink.com`，模型 GLM-5.1。指数退避重试，默认 max_tokens=8192。GLM-5.1 偶尔不稳定(502)，需较大超时(120s)。
- **deduper.py**：先 `_clean_html()` 清理摘要中的 HTML 标签，再 URL 精确去重 + Levenshtein 标题相似度去重(阈值 0.75)。
- **summarizer.py**：5 个方向各有独立 prompt 模板，LLM 输出严格 JSON 数组。超过 `llm_batch_size`(15) 条时分批发送，每批独立降级。解析失败时降级为原始摘要（`impact="暂无影响分析"`）。

### 渲染层 (`src/renderer/`)

Jinja2 模板生成纯 HTML+CSS 静态页面。模板中字典的 `items` key 会和 Python 内置 `dict.items()` 冲突，所以数据中的新闻列表 key 用 `entries` 而非 `items`。

### 数据流

```
collect_all_feeds() + collect_currents() + collect_github_trending()
  → combined: dict[Category, list[RawItem]]
  → deduplicate_all(combined)
  → process_all(deduped) → dict[Category, ProcessedCategory]
  → render_daily_page(today, processed) → output/index.html + archive/
  → git_push(today) → Cloudflare 自动部署
```

## 5 个新闻方向

| Category 枚举 | 标签 | 主要数据源 |
|---|---|---|
| AI_TECH | AI / 科技 | 36氪、量子位、HN、TechCrunch、arXiv、CurrentsAPI |
| INTERNATIONAL | 国际形势 | BBC World、BBC中文、CurrentsAPI |
| DOMESTIC | 国内形势 | 知乎、澎湃、观察者网、人民网、CurrentsAPI |
| DEV_TOOLS | 编程工具 | GitHub Blog、JetBrains Blog、VS Code Releases、HN Show |
| AI_GITHUB | AI 开源飙升榜 | GitHub Trending CDN、GitHub Search API |

## 关键配置 (.env)

- `ANTHROPIC_API_KEY` + `ANTHROPIC_BASE_URL`：LLM 调用必需
- `CURRENTS_API_KEY`：不配则跳过 CurrentsAPI 采集
- `ZHIHU_COOKIES`：知乎全文摘要需要，不配只取标题
- `GITHUB_TOKEN`：可选，提升 GitHub API 速率限制（不配每分钟 10 次也够用）
- `http_proxy` / `https_proxy`：国际源访问代理，默认 `http://127.0.0.1:54771`

## 定时与部署

- macOS launchd 每日 10:00 触发，plist 文件在 `launchd/` 目录
- Cloudflare Pages 通过 Git 集成自动部署（push 后自动构建）
- 不再使用 GitHub Actions 部署（已删除 `.github/workflows/deploy.yml`）
