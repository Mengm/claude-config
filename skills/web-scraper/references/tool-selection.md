# 工具链详细对比

## httpx（首选，覆盖 80% 场景）

**适用**: 静态 HTML、REST API、JSON 数据接口
**优势**: 快、轻、支持异步、HTTP/2
**限制**: 不执行 JS

```python
import httpx

# 同步
with httpx.Client(follow_redirects=True, timeout=30) as client:
    resp = client.get(url, headers={"User-Agent": UA})

# 异步（大规模并发）
import asyncio
async def fetch_all(urls):
    async with httpx.AsyncClient(follow_redirects=True, timeout=30) as client:
        tasks = [client.get(url) for url in urls]
        return await asyncio.gather(*tasks, return_exceptions=True)
```

**何时用异步**: 目标 URL > 50 个且互相独立时。少量 URL 用同步即可。

## Playwright（JS 渲染 + 交互）

**适用**: SPA/CSR 页面、需要点击/滚动/登录的场景
**优势**: 真实浏览器环境，几乎没有页面打不开
**限制**: 慢（每页 2-5 秒）、资源消耗大

```python
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    context = browser.new_context(
        user_agent="...",
        viewport={"width": 1920, "height": 1080},
    )
    page = context.new_page()

    # 拦截不需要的资源加速加载
    page.route("**/*.{png,jpg,jpeg,gif,svg,woff,woff2}", lambda route: route.abort())

    page.goto(url, wait_until="networkidle")

    # 等待特定元素出现
    page.wait_for_selector(".data-list", timeout=10000)

    # 提取数据
    items = page.query_selector_all(".item")
    data = [item.text_content() for item in items]

    browser.close()
```

### 无限滚动页面

```python
prev_height = 0
while True:
    page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
    page.wait_for_timeout(2000)
    new_height = page.evaluate("document.body.scrollHeight")
    if new_height == prev_height:
        break
    prev_height = new_height
```

### Cookie 注入（登录态）

```python
context = browser.new_context()
context.add_cookies([
    {"name": "session_id", "value": "xxx", "domain": ".example.com", "path": "/"},
])
```

## curl_cffi（反爬绕过）

**适用**: Cloudflare、DataDome 等 WAF 防护的站点
**优势**: 模拟真实浏览器 TLS 指纹（JA3/JA4）
**限制**: 需要额外安装 `curl_cffi`

```python
from curl_cffi import requests as curl_requests

# impersonate 支持: chrome110-131, safari15_3-18_0, edge101-131
resp = curl_requests.get(url, impersonate="chrome131", timeout=30)

# 带 session 保持 cookie
session = curl_requests.Session(impersonate="chrome131")
session.get(login_url, data={"user": "...", "pass": "..."})
resp = session.get(protected_url)
```

## BeautifulSoup4 + lxml（HTML 解析）

```python
from bs4 import BeautifulSoup

soup = BeautifulSoup(html, "lxml")
# CSS 选择器
items = soup.select("div.list > a.item")
for item in items:
    title = item.select_one("h3").get_text(strip=True)
    link = item["href"]
```

## parsel（轻量选择器，支持 CSS + XPath）

```python
from parsel import Selector

sel = Selector(text=html)
# CSS
titles = sel.css("h3.title::text").getall()
# XPath
links = sel.xpath("//a[@class='item']/@href").getall()
```

## 选型决策总结

- **静态页面** → httpx + bs4
- **JSON API** → httpx
- **JS 渲染页面** → Playwright
- **有 Cloudflare** → curl_cffi（备选 Playwright）
- **需要登录** → Playwright（备选 httpx + session）
- **大规模并发** → httpx async
- **无限滚动** → Playwright
