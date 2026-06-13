# 每日热点速递 📰

自动采集 AI/科技、国际形势、国内形势三大方向的每日热点新闻，由 GLM-5.1 生成摘要和影响分析，部署在 Cloudflare Pages 上。

## 数据源

| 方向 | 来源 |
|------|------|
| AI/科技 | 36氪热榜、量子位、Hacker News、TechCrunch、arXiv cs.AI/cs.CL |
| 国际形势 | BBC World、BBC 中文网、CurrentsAPI |
| 国内形势 | 知乎热榜、澎湃新闻、观察者网、人民网、CurrentsAPI |

## 快速开始

### 1. 环境准备

```bash
# 创建虚拟环境
python3 -m venv .venv
source .venv/bin/activate
pip install -e .

# 复制环境变量模板
cp .env.example .env
# 编辑 .env 填入 API Keys 和知乎 Cookie
```

### 2. 启动 RSSHub

```bash
# 确保 Docker 运行
bash scripts/setup_rsshub.sh
```

### 3. 手动运行一次

```bash
source .venv/bin/activate
python -m src.main
```

### 4. 安装定时任务

```bash
cp launchd/com.lx.daily-hot-news.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.lx.daily-hot-news.plist
```

## 部署

1. 创建 GitHub 仓库
2. 在仓库 Settings → Secrets 中添加 `CLOUDFLARE_API_TOKEN` 和 `CLOUDFLARE_ACCOUNT_ID`
3. Push 后 GitHub Actions 自动部署到 Cloudflare Pages

## 项目结构

```
src/
├── main.py              # 主入口
├── config.py            # 配置
├── collectors/          # 采集层
│   ├── rss_collector.py # RSS 采集
│   └── currents.py      # CurrentsAPI
├── processor/           # 处理层
│   ├── llm.py           # LLM 调用
│   ├── deduper.py       # 去重
│   └── summarizer.py    # 摘要生成
└── renderer/            # 渲染层
    ├── html_builder.py  # HTML 生成
    └── templates/       # Jinja2 模板
```
