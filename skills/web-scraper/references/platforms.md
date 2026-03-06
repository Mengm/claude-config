# 各平台爬取指南

按平台整理的爬取方案、反爬策略、推荐工具和实战经验。

---

## 国内平台

### 微信公众号（mp.weixin.qq.com）

**难度：中 | 推荐方案：httpx + HTML 解析**

**方法**：
- 移动端 Safari UA + httpx 直接抓 HTML
- 从 `og:title`、`msg_title`、`js_content` 提取元数据和正文
- 图片从 `data-src` 属性提取（`mmbiz.qpic.cn`，永久有效，无签名时效）

**反爬要点**：
- WebFetch / Jina Reader 均无法读取（302 验证码拦截）
- 直接用 httpx + 移动端 UA 可以绕过，不需要 Playwright
- 文章会过期/删除，URL 不保证永久有效
- 批量爬取公众号历史文章需要 MITM 代理拦截 `getmasssendmsg` 接口获取 `appmsg_token`（复杂，一般不需要）
- 数据中心 IP 容易被封，住宅代理更稳

**数据结构**：
```
标题 → og:title 或 var msg_title
作者 → var nickname
正文 → div#js_content 内的文本
图片 → data-src="https://mmbiz.qpic.cn/..."
```

**项目内已有**：`web-read` skill 完整支持

---

### 小红书（xiaohongshu.com / xhslink.com）

**难度：高 | 推荐方案：xhs 库 API + SSR HTML 兜底**

**方法一（推荐）：xhs 库 API 调用**
- 项目已安装 `xhs` 库（PyPI），封装了 edith API 签名
- `get_note_by_id()` 获取笔记详情
- `get_notes_statistics()` / `get_notes_summary()` 获取数据统计
- 必须先 `inspect.getsource()` 看库源码确认端点和参数（field-note #33）

**方法二：SSR HTML 解析（web-read 当前方案）**
- 移动端 UA 请求 → `__INITIAL_STATE__` JSON 包含完整数据
- JSON 中有 `:undefined`（非标准），需先 `.replace(":undefined", ":null")`
- `noteData.data.noteData` → 标题、正文、标签、图片
- `noteData.data.commentData` → 评论区（含楼中楼）

**反爬要点**：
- 云服务器 IP（阿里云/AWS）被重点封禁，请求直接 302 到 `/404/sec_*`
- Cookie 必须：`a1`、`web_session`、`webId`（从环境变量 `XHS_COOKIE_*` 读取）
- 图片 CDN 绕过：用 `ci.xiaohongshu.com/{fileId}?imageView2/2/w/1080/format/jpg`（永久），不用 `sns-webpic-qc.xhscdn.com`（带签名会过期）
- edith API cookie 频繁过期（`{"code": -100}`）
- `site:xiaohongshu.com` 搜索引擎搜索几乎无效（JS 渲染页面不被索引）
- 平台 AIGC 检测：句长标准差是核心特征（AI ~1.2 vs 人类 ~4.7）

**推荐库**：
- `xhs`（PyPI，项目已安装）— edith API 封装
- `JoeanAmier/XHS-Downloader`（GitHub）— 图文/视频下载
- `NanmiCoder/MediaCrawler`（GitHub）— 多平台爬虫（XHS/抖音/B站/微博/知乎），Playwright + 登录态保持，Pro 版支持多账号和 JS 签名解耦

---

### 知乎（zhihu.com / zhuanlan.zhihu.com）

**难度：高 | 推荐方案：API → Firecrawl 兜底**

**方法**：
- 单条回答：`/api/v4/answers/{id}?include=content,voteup_count` API 直调
- 问题页/专栏文章：需要 x-zse 签名，直接用 Firecrawl（`waitFor=5000`）
- z_c0 登录 cookie 显著提高 API 成功率

**反爬要点**：
- 云服务器 IP 极易被限流（403 错误码 40362）
- API 被限时自动 fallback 到 Firecrawl（需 `FIRECRAWL_API_KEY`）
- 不要短时间内反复请求同一 IP
- 问题页和专栏文章的 API 需要 x-zse-93/x-zse-96 签名（复杂），优先用 Firecrawl

**数据结构**（API 返回）：
```json
{
  "question": {"title": "..."},
  "author": {"name": "..."},
  "content": "<html>...",  // 需要 strip HTML tags
  "voteup_count": 1234,
  "comment_count": 56
}
```

**推荐库**：
- Firecrawl API（`FIRECRAWL_API_KEY`）— JS 渲染 + 反爬绕过
- 项目已有完整实现（`web-read` skill）

---

### B 站（bilibili.com / b23.tv）

**难度：低 | 推荐方案：B 站公开 API**

**方法**：
- 视频信息：`/x/web-interface/view?bvid=BVxxx`
- 标签：`/x/tag/archive/tags?bvid=BVxxx`
- 字幕：`/x/player/wbi/v2`（需 WBI 签名 + SESSDATA）
- 评论：`/x/v2/reply?type=1&oid={aid}&sort=1`（按热度排序）

**反爬要点**：
- 字幕 API 需要 `BILI_SESSDATA` 登录态，没有时仍可获取元数据+标签+评论
- WBI 签名：需要从 `/x/web-interface/nav` 获取 `img_key` + `sub_key`，用 mixin table 生成 `w_rid`
- 短链 `b23.tv` 需先 HEAD 请求解析真实 URL
- 评论 API 旧版（`/x/v2/reply`）不需要 WBI，但新版可能需要

**数据覆盖**：
```
元数据: 标题、UP主、BV号、时长、分P
数据: 播放/弹幕/评论/点赞/投币/收藏/分享
字幕: AI 中文字幕全文（需 SESSDATA）
评论: 热门评论 top15（含点赞数和回复数）
标签: 视频标签列表
```

**推荐库**：
- `bilibili-api-python`（PyPI，Nemo2011）— 全异步，覆盖视频/番剧/直播/弹幕/专栏
- 项目当前用 httpx 直调 API（`web-read` skill）

---

### 知识星球（zsxq.com）

**难度：低 | 推荐方案：ZSXQ v2 API**

**方法**：
- `/v2/topics/{topic_id}` 获取帖子详情
- `/v2/topics/{topic_id}/comments?count=20&sort=asc` 获取评论
- 仅需 cookie 鉴权（`zsxq_access_token`），无需复杂签名

**反爬要点**：
- `ZSXQ_ACCESS_TOKEN` 定期过期，需人工更新
- 短链 `t.zsxq.com` 返回 405 对 HEAD 请求，必须用 GET 解析
- Headers 需要 `X-Version: 2.89.0`

**URL 格式**：
```
wx.zsxq.com/topic/{topic_id}       — 标准
wx.zsxq.com/dweb/topic/{topic_id}  — 桌面版
articles.zsxq.com/id_{id}.html     — 文章
t.zsxq.com/xxx                     — 短链
```

---

### 抖音（douyin.com）

**难度：极高 | 推荐方案：MediaCrawler（Playwright）/ f2**

**方法一（推荐）：MediaCrawler — Playwright 浏览器自动化**
- 避开 X-Bogus/A-Bogus 签名逆向，直接用真实浏览器环境
- QR 码扫码登录，自动保持 session
- 支持关键词搜索、视频详情、评论（含楼中楼）、作者主页
- 输出：CSV、JSON、Excel、SQLite、MySQL

**方法二：Douyin_TikTok_Download_API — 异步 REST 服务**
- 内部实现 X-Bogus/A-Bogus 签名生成
- 暴露 REST 端点：`/api/hybrid/video_data`、`/api/download`
- 需要手动配置 cookie（`config.yaml`）
- GitHub: Evil0ctal/Douyin_TikTok_Download_API（16k+ stars）

**方法三：f2 — 编程式 API 访问**
- 最完整的签名处理（XBogus、ABogus、msToken、ttwid、verify_fp）
- CLI + Python 库双接口
- 需要跟进签名算法更新
- GitHub: Johnserf-Seed/f2（2.3k stars）

**反爬要点（国内最强之一）**：
- **X-Bogus / A-Bogus 签名**：每个 API 请求需要加密签名参数，算法定期更新，A-Bogus 更复杂
- **msToken**：服务端签发 token，126 字符，部分端点可伪造但真实 token 更稳定
- **ttwid / s_v_web_id / verify_fp**：浏览器指纹 cookie，即使未登录也必须携带
- **自定义字体混淆**：部分页面数字用自定义字体渲染，字形重映射，OCR 不可靠
- **IP 限流极其激进**：密集请求几分钟内触发验证码或封禁
- **接口频繁变更**：端点和签名算法不定期修改，爬虫需要持续维护

**Cookie/登录**：
- 无登录：极其有限，大部分端点返回空数据
- 有登录：QR 码扫码（MediaCrawler 方案）或手动从 DevTools 提取
- 关键 cookie：`sessionid`、`ttwid`、`odin_tt`、`passport_csrf_token`
- Session 会过期，需定期刷新

**可提取数据**：
```
视频: 标题、描述、标签、音乐、播放/点赞/评论/分享数、发布时间
下载: 无水印视频 URL
用户: 昵称、头像、简介、粉丝/关注数、认证状态
评论: 评论及嵌套回复
搜索: 关键词搜索结果
直播: 直播间数据和弹幕
```

**法律风险：极高**
- 抖音 ToS 明确禁止自动化采集
- 反不正当竞争法：已有判例赔偿 2000 万元（抖音 vs 刷宝，爬取 5 万条视频）
- PIPL：未经同意采集用户数据，最高罚款 5000 万元或年营收 5%

**推荐库**：
- `NanmiCoder/MediaCrawler`（44k+ stars）— Playwright 方案，绕过签名
- `Evil0ctal/Douyin_TikTok_Download_API`（16k+ stars）— 异步 REST API
- `Johnserf-Seed/f2`（2.3k stars）— 编程式签名 + CLI

---

### 微博（weibo.com / m.weibo.cn）

**难度：中 | 推荐方案：移动端 API（m.weibo.cn）**

**方法一（推荐）：移动端 Web API**
- `m.weibo.cn` 返回 JSON，反爬比桌面端轻得多
- 用户微博列表：`/api/container/getIndex?containerid=107603{uid}`
- 微博详情：`/detail/{mid}`
- 评论：`/api/comments/show?id={mid}&page=1`
- 无需复杂签名（和抖音的根本区别）

**方法二：dataabc/weibo-crawler**
- 专用微博爬虫，成熟稳定，文档详尽（4.3k stars）
- 按用户 ID 爬取（支持多用户）
- 图片、视频、Live Photo 下载
- 增量爬取支持（只爬新内容）
- 存储：CSV、JSON、MySQL、MongoDB、SQLite
- Cookie 可选（没有 cookie 也能爬公开数据，有 cookie 数据更全）

**反爬要点**：
- **无加密签名**：微博不使用 X-Bogus 类签名，这是它比抖音容易得多的核心原因
- Cookie 可选：移动端 API 公开数据不需要 cookie，搜索和评论需要
- IP 限流中等：住宅代理更稳，数据中心 IP 被封更快
- CAPTCHA：持续请求后触发滑动验证码，不是每次请求都有
- **搜索结果上限**：每个搜索词最多 50 页 × 20 条 = 1000 条结果（硬限制）
- Cookie 寿命比抖音长，不需要频繁刷新

**可提取数据**：
```
用户: ID、昵称、性别、生日、地点、教育、公司、粉丝/关注数、简介、认证状态、阳光信用
微博: 正文、图片/视频 URL、位置、发布时间、点赞/评论/转发数、话题标签、@提及
评论: 一级评论
热搜: 热搜榜/趋势话题
搜索: 关键词搜索（上限 1000 条）
```

**官方 API**（`open.weibo.com`）：
- 需要注册开发者 + 应用审核
- 限流 ~150 req/hour，数据范围有限
- 2018 年后大量端点废弃或收紧，实用价值低
- 不推荐作为主力方案

**推荐库**：
- `dataabc/weibo-crawler`（4.3k stars）— 用户维度爬取，最成熟
- `NanmiCoder/MediaCrawler`（44k+ stars）— 多平台统一方案
- `Johnserf-Seed/f2`（2.3k stars）— 也支持微博

---

## 国外平台

### YouTube（youtube.com / youtu.be）

**难度：低 | 推荐方案：yt-dlp + youtube-transcript-api**

**方法一：yt-dlp（批量元数据/评论推荐）**
- `yt-dlp --dump-json URL` 获取完整结构化数据（不下载视频）
- 支持播放列表、频道、搜索结果的批量处理
- 评论提取：`--write-comments`
- GitHub: yt-dlp/yt-dlp（90k+ stars，极活跃）

**方法二：oEmbed + transcript-api（web-read 当前方案）**
- 元数据：oEmbed API（无需 API key）`/oembed?url=...&format=json`
- 字幕/转录：`youtube-transcript-api` 库（项目已安装）
- 优先中文字幕 → 英文 → 其他语言
- 支持 AI 自动生成字幕和手动上传字幕

**反爬要点**：
- 公开视频字幕不需要登录
- 年龄限制视频需要登录态
- IP 级限流（~50-100 req/hour/IP），批量场景需代理轮换
- EU IP 可能触发 consent 页面
- yt-dlp 更新频繁（YouTube 常改接口），生产环境建议 pin 版本但定期更新
- YouTube Data API v3（官方）有免费配额（10k units/day），纯元数据场景可考虑

**URL 格式**（正则 `([\w-]{11})`）：
```
youtube.com/watch?v=xxxxx
youtu.be/xxxxx
youtube.com/shorts/xxxxx
youtube.com/embed/xxxxx
youtube.com/live/xxxxx
```

---

### X / Twitter

**难度：极高 | 推荐方案：twscrape（批量）/ Tweepy（官方 API）**

**方法一：twscrape（推荐，免费）**
- GraphQL 端点爬取，不依赖官方 API
- 需要添加 X 账号（cookie 或 登录流程）
- 支持搜索、推文详情、用户信息、粉丝列表、趋势
- 全异步，支持账号池轮换

```python
from twscrape import API
api = API()
await api.pool.add_account("user", "pass", "email", "email_pass")
await api.pool.login_all()
tweets = await api.search("query", limit=20)
```

**方法二：Tweepy（官方 API）**
- 项目已安装 `tweepy`
- 需要 Twitter Developer 账号和 API keys
- Free tier 限制严格（1500 tweets/month）
- Basic tier $100/month

**反爬要点**：
- X 反爬极其激进，snscrape（HTML 端点）经常失效（每隔几周就会坏一次）
- twscrape 用 GraphQL 相对稳定，但也需要定期更新
- 账号池轮换是批量爬取的关键（每个账号有请求限制）
- 不要暴力请求，会导致账号被封
- **法律风险**：X 的 ToS 规定未授权爬取 >100 万条/24h 可能面临 $15,000 违约金
- Twint 已废弃（abandoned），不要使用

**推荐库**：
- `twscrape`（GitHub: vladkens/twscrape）— 2025 活跃维护，GraphQL + 多账号池
- `tweepy`（项目已安装）— 官方 API 封装
- snscrape — 免费但脆弱，不推荐作为主力

---

### Dev.to

**难度：极低 | 推荐方案：官方 API（免费，无需认证）**

**方法**：
- 文章列表：`GET https://dev.to/api/articles?tag=python&top=7`（7 天热门）
- 文章详情：`GET https://dev.to/api/articles/{id}`
- 用户文章：`GET https://dev.to/api/articles?username=xxx`
- 搜索：`GET https://dev.to/api/articles?tag=xxx&page=1&per_page=30`

```python
import httpx

resp = httpx.get("https://dev.to/api/articles", params={
    "tag": "webdev",
    "top": 7,
    "per_page": 30,
})
articles = resp.json()
# 每篇文章有: title, url, description, tags,
# positive_reactions_count, comments_count, published_at
```

**反爬要点**：
- API 完全公开免费，不需要 API key
- Rate limit 宽松（~30 req/s）
- 返回 JSON 结构化数据，不需要 HTML 解析
- 文章正文在 `/articles/{id}` 里的 `body_html` 或 `body_markdown` 字段

---

### GitHub

**难度：低 | 推荐方案：gh CLI / REST API / PyGithub**

**方法一：gh CLI（项目内推荐）**
- `gh api repos/{owner}/{repo}` — 仓库信息
- `gh api search/repositories?q=topic:ai+stars:>1000` — 搜索
- `gh api repos/{owner}/{repo}/readme` — README 内容
- 已认证，不需要额外配置

**方法二：REST API / PyGithub**
```python
import httpx

# 无认证：60 req/hour，认证后：5000 req/hour
headers = {"Authorization": f"token {GITHUB_TOKEN}"}
resp = httpx.get("https://api.github.com/search/repositories",
    params={"q": "web scraping language:python", "sort": "stars"},
    headers=headers,
)
```

**Trending 页面（无官方 API）**：
- GitHub 没有 trending 的 REST API
- 需要 HTML 爬取 `https://github.com/trending?since=daily`
- 或用 `gh api search/repositories?q=created:>2026-02-15+stars:>100&sort=stars` 模拟

**反爬要点**：
- 无认证 60 req/hour，认证 5000 req/hour
- 搜索 API 限制 30 req/min
- README 内容需要 base64 解码

**推荐库**：
- `gh` CLI（项目已配置）
- `PyGithub`（PyPI）— REST API 的 Python 封装

---

## AI 驱动的爬虫工具（新趋势）

### Crawl4AI
- 专为 LLM 设计，自动将网页转成 clean markdown（58k+ stars）
- Playwright 后端，支持 JS 渲染、无限滚动、点击交互
- **Crash Recovery**：内置 `CrawlResumeState`，批量爬取中断后可从断点恢复
- **智能分块**：自动按 DOM 结构分块，适配 LLM context window
- **结构化提取**：支持 CSS/XPath/LLM-based extraction 三种模式
- **Session 管理**：保持登录态跨页面爬取（`session_id` 参数）
- 本地部署免费，也提供 Docker 一键部署
- GitHub: unclecode/crawl4ai

### Firecrawl
- 项目已使用（`FIRECRAWL_API_KEY`）
- API 服务，`waitFor` 参数支持 JS 渲染等待
- 用作知乎等复杂站点的可靠兜底

### ScrapeGraphAI
- 用 LLM + 图逻辑构建爬虫 pipeline
- 自然语言描述要提取什么 → 自动爬取
- 支持多种 LLM 后端（OpenAI/Groq/Ollama）
- GitHub: ScrapeGraphAI/Scrapegraph-ai

### Jina Reader
- 项目已使用（`web-read` 的通用 URL fallback）
- 免费，无需 API key
- `https://r.jina.ai/{url}` → markdown 输出
- 不适合反爬严格的站点

---

## 通用 Fallback 链

项目当前的 URL 处理优先级（可复用于批量场景）：

```
特定平台（微信/XHS/B站/YouTube/知乎/ZSXQ）
  → 各平台专用逻辑

其他 URL：
  → Jina Reader（免费，快）
  → Firecrawl（JS 渲染，反爬绕过，需 API key）
  → Playwright（本地浏览器，最重但最可靠）
```
