---
name: web-scraper
description: 网页爬虫与批量数据采集。当用户涉及以下场景时触发：(1) 批量抓取网页数据（"爬一下"、"抓取"、"采集"、"爬虫"、"scrape"、"crawl"） (2) 给了列表页 URL 要求提取所有条目 (3) 分页爬取（"把所有页都爬下来"） (4) 列表页→详情页的结构化采集 (5) 需要登录态/cookie 的批量爬取 (6) 定期数据采集/监控需求。注意：单个 URL 的内容读取使用 web-read skill，本 skill 用于批量/结构化/多页场景。
---

# 网页爬虫与批量数据采集

批量/结构化网页数据采集。与 web-read（单页阅读）的区别：本 skill 处理多页、分页、列表→详情等需要编写爬虫逻辑的场景。

## 工作流程

1. **分析目标** — 访问目标 URL，判断页面类型和反爬等级
2. **选择工具链** — 根据分析结果选择合适方案（见 References）
3. **编写爬虫** — 在 `$TASKPOOL_USER_DESK/` 下生成爬虫脚本，文件名含 `$TASKPOOL_TASK_ID`
4. **执行采集** — 运行脚本，输出结构化数据
5. **交付数据** — JSON/CSV 文件，或写入飞书多维表格

## 工具链选择（快速决策）

```
目标页面
  ├─ 静态 HTML（能看到数据在源码里）→ httpx + parsel/bs4
  ├─ JS 渲染（数据靠 JS 加载）
  │    ├─ 有 API 接口（Network 能抓到 JSON）→ httpx 直调 API
  │    └─ 无明显 API → Playwright
  ├─ 有 Cloudflare/反爬盾 → curl_cffi（TLS 指纹模拟）
  └─ 需要登录 → Playwright + cookie 注入 / httpx + session
```

## 核心原则

- **先找 API，后解析 HTML**：大多数现代网站有前后端分离的 JSON API，比解析 HTML 稳定得多。打开 DevTools Network 标签页找 XHR/Fetch 请求
- **调第三方 API 先查库源码**：不要猜端点和参数。项目已有 `xhs` 库等，用 `inspect.getsource()` 看库怎么调的，确认端点、header、签名方式后再写代码（field-note #33）
- **先小批验证再全量**：先爬 3-5 页确认数据格式和反爬等级，再决定全量策略。一次性写完整框架不验证 = 5 个未验证假设同时上线（field-note #32）
- **前 10 条必须检查字段完整性**：列表 API 往往缺正文/回复等关键字段。跑 10 条后打印所有字段名+样本值，对照需求确认必需字段全部有非空值（field-note #36 反模式 2）
- **前 3 页必须检查去重率**：分页参数不生效时每页返回相同数据，9840 条可能只有 20 条唯一记录。对比第 1 页和第 3 页数据，唯一记录占比 < 95% 就停下排查（field-note #36 反模式 1）
- **"success: true + 空数据"是最危险的响应**：代码不报错但数据为空，很可能是端点/参数/cookie 不对，不是"没有数据"
- **尊重目标站点**：默认 1-2 秒请求间隔，不要 DDoS。设置合理的 User-Agent。批量场景比单次更容易触发反爬
- **数据落盘到 desk**：所有输出文件写到 `$TASKPOOL_USER_DESK/`，文件名含 task ID

## 输出格式

根据用户需求选择：
- **JSON** — 默认，最灵活
- **CSV** — 用户要求表格/Excel 兼容
- **飞书多维表格** — 用户要求写入飞书，组合调用 `feishu-bitable` skill

输出文件使用 `[OUTPUT_FILE: /path/to/file]` 标记。

## 反爬对抗清单

- UA 轮换：维护 5-10 个真实浏览器 UA
- 请求限速：默认 1.5s 间隔，批量场景适当加大到 2-3s。**不要对反爬站点密集重试**——会加速触发临时封禁
- Cookie/登录态：用户提供 cookie 或通过 Playwright 登录获取。cookie 会过期，需检测有效性
- 代理：`CN_PROXY_URL` 环境变量（同 web-read），按域名精确路由，`trust_env=False` 防 httpx 读系统代理
- TLS 指纹：curl_cffi impersonate 模式
- 重试策略：429/503 时指数退避，最多 3 次
- **云服务器 IP 容易被标记**：阿里云/AWS 等云厂商 IP 段被反爬系统重点关注（field-note #35，小红书/知乎实测确认）

## References

- `references/tool-selection.md` — 工具链详细对比（httpx/Playwright/curl_cffi/bs4/parsel）、请求模板和示例代码。选工具或写第一个请求时 Read
- `references/patterns.md` — 9 种爬取模式（分页、列表→详情、无限滚动、API 逆向、断点续爬、重试限速等）的完整代码模板。编写爬虫时 Read
- `references/platforms.md` — 11 平台爬取指南（微信/小红书/知乎/B站/知识星球/抖音/微博/YouTube/X/Dev.to/GitHub）+ AI 爬虫工具。目标平台确定后 Read
- `references/field-lessons.md` — 实战踩坑经验（云 IP 被封、cookie 过期、空数据陷阱、代理架构）。遇到反爬或结果异常时 Read
