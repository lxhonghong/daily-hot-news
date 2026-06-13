# 每日热点新闻自动聚合系统

## 项目规范

- 语言：中文输出 + 英文专有名词
- 三个方向：AI/科技、国际形势、国内形势
- LLM：GLM-5.1（Anthropic SDK 兼容格式，base_url = https://www.huolilink.com）
- 部署：Cloudflare Pages
- 定时：macOS launchd，每日 10:00

## 开发约定

- 不可变数据模式，不修改已有对象
- 每个模块职责单一，文件 < 400 行
- RSSHub 本地 Docker 常驻运行（localhost:1200）
- 知乎热榜需配置 ZHIHU_COOKIES
- 容错：单个源失败不影响整体，LLM 不可用时降级为原始摘要
