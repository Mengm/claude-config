# 数据源详细配置

## 0. Twitter/X AI 大佬动态

用 Jina Reader 抓取关键 AI 领袖的 X/Twitter 主页，提取最近 24-48 小时的原创推文。

**目标账号：**
- `@sama` — Sam Altman, OpenAI CEO
- `@ylecun` — Yann LeCun, Meta 首席 AI 科学家
- `@AndrewYNg` — Andrew Ng, DeepLearning.AI 创始人
- `@elonmusk` — Elon Musk, xAI / Tesla
- `@demishassabis` — Demis Hassabis, Google DeepMind CEO
- `@DarioAmodei` — Dario Amodei, Anthropic CEO
- `@DrJimFan` — Jim Fan, NVIDIA AI 研究总监
- `@JeffDean` — Jeff Dean, Google 首席科学家
- `@satyanadella` — Satya Nadella, Microsoft CEO
- `@hardmaru` — David Ha, Sakana AI CEO
- `@karpathy` — Andrej Karpathy, Eureka Labs 创始人

**抓取方式：**
```bash
curl -s "https://r.jina.ai/https://x.com/{HANDLE}" -H "Accept: text/markdown"
```

**筛选标准：**
- 只保留与 AI/ML/LLM/AGI 相关的实质性内容（产品发布预告、技术观点、行业判断、对重大事件的回应）
- 忽略：纯转推、日常生活、政治评论（除非直接涉及 AI 政策）、营销套话
- 如果某条推文引用或评论了日报其他条目中的事件，建立交叉引用
- 保留推文中的图片链接

**降级策略：** 如果超过半数账号抓取失败，降级为 WebSearch：
```
WebSearch: "site:x.com" (sama OR ylecun OR karpathy OR AndrewYNg) AI announcement （限最近 1 天）
```

## 1. Hacker News

**Algolia API — 按热度搜 AI 相关高分帖：**
```bash
curl -s "https://hn.algolia.com/api/v1/search_by_date?tags=story&query=AI+OR+LLM+OR+GPT+OR+Claude+OR+Gemini&hitsPerPage=30&numericFilters=points%3E50"
```
无鉴权。关键字段：`title`, `url`, `points`, `num_comments`, `objectID`（讨论链接 `https://news.ycombinator.com/item?id={objectID}`）, `created_at`

可调参数：`query`（OR 组合）、`tags`（story/show_hn/ask_hn）、`numericFilters`（points>50）、`hitsPerPage`

**HN 首页补充：**
```bash
curl -s "https://r.jina.ai/https://news.ycombinator.com/front" -H "Accept: text/markdown"
```

## 2. HuggingFace Daily Papers

```bash
curl -s "https://r.jina.ai/https://huggingface.co/papers" -H "Accept: text/markdown"
```
每日社区投票热门论文，关注 upvote 数高的。

## 3. Product Hunt

Cloudflare 防护，使用 WebSearch：
```
WebSearch: "site:producthunt.com" AI OR LLM OR GPT （限最近 1 天）
```

## 4. GitHub Trending

```bash
curl -s "https://r.jina.ai/https://github.com/trending?since=daily" -H "Accept: text/markdown"
```
筛选 AI/ML 相关项目，关注 star 增长异常快的。

## 5. 少数派

```bash
curl -s "https://r.jina.ai/https://sspai.com/tag/AI" -H "Accept: text/markdown"
```
AI 工具评测和深度体验，补充中文用户视角。

## 6. Lex Fridman Podcast

**RSS Feed：**
```bash
curl -s "https://lexfridman.com/feed/podcast/" | head -c 3000
```
只关注最近 7 天内的 AI 相关新集。有则用 Jina Reader 抓取提炼核心观点。

## 7. Dwarkesh Podcast

**RSS Feed：**
```bash
curl -s "https://www.dwarkesh.com/feed.xml" | head -c 3000
```
超深度 AI 访谈，1-2 周一期。只关注最近 7 天内的 AI 相关新集。

## 8. Agent Memory 研究追踪

持续关注 agent memory / context management 方向的核心团队和项目。

**GitHub Releases/Commits 监控：**
```bash
# RLM 官方实现 — Alex Zhang (MIT)
curl -s "https://r.jina.ai/https://github.com/alexzhang13/rlm/releases" -H "Accept: text/markdown"

# Letta (MemGPT) — 最新 release
curl -s "https://r.jina.ai/https://github.com/letta-ai/letta/releases" -H "Accept: text/markdown"

# A-MEM — Zettelkasten 式记忆
curl -s "https://r.jina.ai/https://github.com/WujiangXu/A-mem" -H "Accept: text/markdown"
```

**博客/团队动态：**
```bash
# Prime Intellect 博客 — RLM 工程化落地
curl -s "https://r.jina.ai/https://www.primeintellect.ai/blog" -H "Accept: text/markdown"

# Letta 博客 — Context Engineering / Memory Blocks / Skill Learning
curl -s "https://r.jina.ai/https://www.letta.com/blog" -H "Accept: text/markdown"

# Alex Zhang 博客
curl -s "https://r.jina.ai/https://alexzhang13.github.io/" -H "Accept: text/markdown"
```

**筛选标准：**
- RLM 新版本、新论文、训练结果
- Letta 新功能发布、benchmark 更新、Context Repositories 进展
- Prime Intellect 的 RLMEnv/prime-rl 训练进展
- Agent memory 相关重要论文（arXiv "LLM memory management" / "context engineering"）

**联动**：发现新内容时，检查 `kb/agent-memory-research.md` 是否已收录，未收录则追加。

## 9. WebSearch 补充

对固定源遗漏的领域用 WebSearch 补充：新模型发布、重大政策/监管、行业并购/融资。

## 10. 92 个顶级博客 RSS 源

2025 年 Hacker News 最受欢迎博客 RSS 源（Karpathy 推荐），涵盖 AI/ML/编程艺术/数学/科学/硬科技领域。

**详细列表**：读取 `references/top-blog-rss.md`

**抓取策略**：
- 使用 `feedparser` 解析 RSS feeds
- 每天扫描一次，抓取最近 24 小时的更新
- 优先关注 AI/ML/LLM/AGI 相关的深度技术文章
- 如 RSS 解析失败，使用 Jina Reader 从博客 URL 获取最新文章

**筛选标准**：
- AI/ML/LLM/AGI 相关的深度技术文章
- 产品发布/更新公告
- 行业分析和趋势判断
- 重要技术观点和方法论

**降级策略**：如果超过 70% 的 feeds 抓取失败，跳过此数据源，依赖其他源。

**技术实现**（示例）：
```python
import feedparser

def fetch_rss_feed(url):
    feed = feedparser.parse(url)
    return [(e.get('title'), e.get('link'), e.get('published'), e.get('summary', ''))
            for e in feed.entries if e.get('published')]
```

或使用 Jina Reader 统一处理：
```python
import httpx

def fetch_with_jina(url):
    response = httpx.get(f"https://r.jina.ai/{url}", headers={"Accept": "text/markdown"})
    return response.text
```

**优先级分类**：
- 一级优先（AI/ML 核心源）：simonwillison.net, garymarcus.substack.com, gwern.net, geoffreylitt.com, minimaxir.com, geohot.github.io
- 二级优先（硬核技术/编程）：matklad.github.io, eli.thegreenplace.net, borretti.me, bernsteinbear.com, lcamtuf.substack.com, mitchellh.com
- 三级优先（深度思考/人文）：pluralistic.net, paulgraham.com, steveblank.com, experimental-history.com, tedium.co
