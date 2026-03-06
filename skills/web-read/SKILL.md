---
name: web-read
description: 读取外部网页内容。当消息中包含非飞书内部文档的链接（微信公众号文章、小红书笔记、B站视频、YouTube视频、知乎回答/文章、知识星球帖子、普通网页等），且需要获取页面内容时触发。典型场景：(1) 用户发了微信文章链接要求阅读/总结 (2) 用户发了小红书链接（xhslink.com 或 xiaohongshu.com）(3) 用户发了B站视频链接（bilibili.com 或 b23.tv）(4) 用户发了YouTube视频链接 (5) 用户发了知乎链接（zhihu.com 回答/问题/专栏）(6) 用户发了知识星球链接（zsxq.com 或 t.zsxq.com）(7) 用户发了网页 URL 需要提取内容 (8) WebFetch 工具失败后的 fallback。注意：任何 *.feishu.cn 域名的 /docx/*、/wiki/*、/base/* 链接（包括 larkcommunity.feishu.cn 等跨租户公开 wiki）都不走此 skill，应使用 feishu-wiki / feishu-doc / feishu-bitable。飞书开发者文档（open.feishu.cn/document/*）是公开网页，可以走此 skill。
---

# 读取外部网页内容

统一的外部 URL 内容提取工具。按 URL 类型自动选择最佳抓取方式。

## 使用方法

```bash
uv run python .claude/skills/web-read/scripts/web_read.py <url>
```

可选参数：
- `--max-chars N` — 截断输出到 N 字符（节省 context，0=不限）

## 支持的 URL 类型

### 微信公众号文章（mp.weixin.qq.com）

WebFetch 和 Jina Reader 均无法读取微信文章（302 验证码拦截）。此 skill 用 httpx + 移动端 Safari UA 直接抓取 HTML，提取：
- 标题、作者、简介、封面图
- 正文纯文本（~2KB，非 2.8MB 全 HTML）
- 文章内所有图片链接

### 小红书笔记（xiaohongshu.com / xhslink.com）

支持短链接（xhslink.com）和直接链接（xiaohongshu.com/discovery/item/... 或 /explore/...）。用移动端 UA 获取 SSR 页面，解析 `__INITIAL_STATE__` JSON，提取：
- 标题、作者、正文描述、话题标签
- 图片永久链接（通过 ci.xiaohongshu.com CDN，无签名时效限制）
- 互动数据（赞/评/藏/转）
- 评论区（含楼中楼回复、IP 归属地、点赞数）

### B站视频（bilibili.com / b23.tv）

通过 B站 API 提取视频结构化数据，**不下载/播放视频**，token 消耗极低。支持：
- 标题、UP主、BV号、时长、分P信息
- 标签
- 完整数据（播放/弹幕/评论/点赞/投币/收藏/分享）
- AI 字幕全文（需要 `BILI_SESSDATA`，将视频内容转为纯文本）
- 热门评论（前15条，含点赞数和回复数）

支持 URL 格式：
- `bilibili.com/video/BVxxxxxxx`
- `bilibili.com/video/avxxxxxx`
- `b23.tv/xxxxxxx`（短链接，自动解析）

### YouTube 视频（youtube.com / youtu.be）

通过 youtube-transcript-api 提取字幕文本 + oEmbed 获取元数据，**不下载视频**。提取：
- 标题、频道名、缩略图
- 字幕全文（优先中文，其次英文，再其他语言）
- 支持 AI 自动生成字幕和手动上传字幕

支持 URL 格式：
- `youtube.com/watch?v=xxxxx`
- `youtu.be/xxxxx`
- `youtube.com/shorts/xxxxx`
- `youtube.com/embed/xxxxx`
- `youtube.com/live/xxxxx`

### 知乎（zhihu.com / zhuanlan.zhihu.com）

支持回答页、问题页、专栏文章。策略：API 快速获取（单条回答），Firecrawl 兜底（API 被限流时、问题页、专栏文章）。提取：
- 回答全文、作者、赞同数、评论数、发布日期
- 问题标题、关注者数、浏览量
- 专栏文章全文

支持 URL 格式：
- `zhihu.com/question/{id}/answer/{id}`（单条回答）
- `zhihu.com/question/{id}`（问题页）
- `zhuanlan.zhihu.com/p/{id}`（专栏文章）

### 知识星球（zsxq.com）

通过 ZSXQ v2 API 提取帖子结构化数据（cookie 鉴权，无需签名）。提取：
- 帖子正文、作者、时间
- 问答帖（问题+回答双方信息）
- 图片链接
- 互动数据（赞/评/阅读/是否精华）
- 评论区（含回复关系、IP 归属地）

支持 URL 格式：
- `wx.zsxq.com/topic/{topic_id}`（标准链接）
- `wx.zsxq.com/dweb/topic/{topic_id}`（桌面版链接）
- `articles.zsxq.com/id_{id}.html`（文章链接）
- `t.zsxq.com/xxx`（短链接，自动解析）

### 其他网页

通过 Jina Reader 转换为 markdown，失败则 Firecrawl 兜底。

## 使用策略

1. **遇到 `mp.weixin.qq.com` 链接** → 直接用此 skill，不要先尝试 WebFetch
2. **遇到小红书链接**（`xhslink.com` 或 `xiaohongshu.com`）→ 直接用此 skill，不要先尝试 WebFetch
3. **遇到B站链接**（`bilibili.com` 或 `b23.tv`）→ 直接用此 skill，不要先尝试 WebFetch
4. **遇到YouTube链接**（`youtube.com` 或 `youtu.be`）→ 直接用此 skill，不要先尝试 WebFetch
5. **遇到知乎链接**（`zhihu.com` 或 `zhuanlan.zhihu.com`）→ 直接用此 skill，不要先尝试 WebFetch
6. **遇到知识星球链接**（`zsxq.com` 或 `t.zsxq.com`）→ 直接用此 skill，不要先尝试 WebFetch
7. **遇到其他链接** → 优先用 WebFetch 工具；如果失败，再用此 skill 作为 fallback
8. **飞书文档**（任何 `*.feishu.cn` 域名的 `/docx/*`、`/wiki/*`、`/base/*`，含跨租户公开 wiki 如 `larkcommunity.feishu.cn`）→ 不走此 skill，用 feishu-wiki / feishu-doc / feishu-bitable
9. **飞书开发者文档**（`open.feishu.cn/document/*`）→ 公开网页，可以走此 skill 或 WebFetch

## 排障注意

- **抓取失败时先验证 URL 有效性**：微信文章会过期/删除，小红书短链会失效。用浏览器或 log 里曾成功的 URL 确认，再判断是代码问题还是链接问题
- **小红书反爬敏感**：云服务器 IP（阿里云、AWS 等）容易被 XHS 安全系统标记。脚本已实现 proxy→直连 fallback + cookie，但频繁请求仍会触发临时封禁。失败时不要反复重试，等几小时再试
- **B站字幕需要 SESSDATA**：字幕 API 需要登录态（`BILI_SESSDATA` 环境变量）。没有 SESSDATA 时仍可获取元数据+标签+评论，只是没有字幕
- **YouTube 字幕不需要登录**：公开视频的字幕可以直接获取。年龄限制视频除外
- **知乎反爬极其激进**：云服务器 IP 容易被知乎限流（403 错误码 40362）。回答 API 被限时自动 fallback 到 Firecrawl（需 `FIRECRAWL_API_KEY`）。不要短时间内反复请求同一 IP
- **Firecrawl 是知乎的可靠兜底**：需要 `waitFor=5000` 让页面 JS 渲染完成。问题页和专栏文章直接走 Firecrawl
- **知识星球需要 access_token**：ZSXQ v2 API 仅需 cookie 鉴权（`ZSXQ_ACCESS_TOKEN`），无需签名。token 可能定期过期，需人工更新
- **环境变量依赖**：
  - `CN_PROXY_URL` — 国内站点代理
  - `FIRECRAWL_API_KEY` — Firecrawl API（知乎兜底、通用 URL fallback）
  - `XHS_COOKIE_A1`/`XHS_COOKIE_WEB_SESSION`/`XHS_COOKIE_WEB_ID` — 小红书 cookie
  - `BILI_SESSDATA`/`BILI_JCT`/`BILI_TICKET` — B站 cookie（字幕需要 SESSDATA）
  - `ZHIHU_COOKIE_ZSE_CK`/`ZHIHU_COOKIE_XSRF`/`ZHIHU_COOKIE_ZAP` — 知乎 cookie（预留，当前 API 不需要）
  - `ZSXQ_ACCESS_TOKEN` — 知识星球 cookie token（v2 API 鉴权）

## 示例

```bash
# 微信文章
uv run python .claude/skills/web-read/scripts/web_read.py "https://mp.weixin.qq.com/s/xxxxx"

# 小红书笔记（短链接或直接链接均可）
uv run python .claude/skills/web-read/scripts/web_read.py "http://xhslink.com/o/xxxxx"
uv run python .claude/skills/web-read/scripts/web_read.py "https://www.xiaohongshu.com/discovery/item/xxxxx"

# B站视频
uv run python .claude/skills/web-read/scripts/web_read.py "https://www.bilibili.com/video/BV1GJ411x7h7"
uv run python .claude/skills/web-read/scripts/web_read.py "https://b23.tv/pigt3PQ"

# YouTube 视频
uv run python .claude/skills/web-read/scripts/web_read.py "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
uv run python .claude/skills/web-read/scripts/web_read.py "https://youtu.be/dQw4w9WgXcQ"

# 知乎回答
uv run python .claude/skills/web-read/scripts/web_read.py "https://www.zhihu.com/question/19551114/answer/12204407"

# 知乎专栏文章
uv run python .claude/skills/web-read/scripts/web_read.py "https://zhuanlan.zhihu.com/p/1986773341550450004"

# 知识星球帖子
uv run python .claude/skills/web-read/scripts/web_read.py "https://wx.zsxq.com/topic/82811218888554182"

# 普通网页（WebFetch 失败后的 fallback）
uv run python .claude/skills/web-read/scripts/web_read.py "https://example.com/article" --max-chars 5000
```

## References

- `references/anti-crawl.md` — 反爬经验、代理架构、CDN 签名绕过。排障或新增平台支持时 Read
