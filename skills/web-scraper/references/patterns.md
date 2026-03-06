# 常见爬取模式

## 1. 分页爬取（页码/offset）

```python
import httpx, time, json

BASE_URL = "https://example.com/api/list"
DELAY = 1.5
results = []

with httpx.Client(timeout=30) as client:
    page = 1
    while True:
        resp = client.get(BASE_URL, params={"page": page, "size": 20})
        data = resp.json()
        items = data.get("items", [])
        if not items:
            break
        results.extend(items)
        print(f"Page {page}: {len(items)} items (total: {len(results)})")
        # 检查是否有下一页
        if not data.get("has_more", True):
            break
        page += 1
        time.sleep(DELAY)

print(f"Done: {len(results)} total items")
```

## 2. 列表页 → 详情页

```python
import httpx, time
from bs4 import BeautifulSoup

DELAY = 1.5
HEADERS = {"User-Agent": "Mozilla/5.0 ..."}

def fetch_list_page(client, page):
    resp = client.get(f"https://example.com/list?page={page}", headers=HEADERS)
    soup = BeautifulSoup(resp.text, "lxml")
    links = [a["href"] for a in soup.select("a.item-link")]
    return links

def fetch_detail(client, url):
    resp = client.get(url, headers=HEADERS)
    soup = BeautifulSoup(resp.text, "lxml")
    return {
        "title": soup.select_one("h1").get_text(strip=True),
        "content": soup.select_one(".content").get_text(strip=True),
    }

results = []
with httpx.Client(follow_redirects=True, timeout=30) as client:
    for page in range(1, 11):  # 10 pages
        links = fetch_list_page(client, page)
        if not links:
            break
        for link in links:
            detail = fetch_detail(client, link)
            results.append(detail)
            print(f"  Fetched: {detail['title'][:40]}")
            time.sleep(DELAY)
        print(f"Page {page} done ({len(links)} items)")
```

## 3. API 逆向（从 DevTools Network 获取接口）

很多"看起来需要 JS 渲染"的页面其实有隐藏 API：

```python
# 典型步骤：
# 1. 打开 DevTools → Network → XHR/Fetch
# 2. 操作页面（翻页、搜索），观察请求
# 3. 复制请求 URL 和 Headers

import httpx

# 常见 API 模式
resp = httpx.get("https://example.com/api/v1/search", params={
    "keyword": "python",
    "page": 1,
    "limit": 20,
}, headers={
    "User-Agent": "...",
    "Referer": "https://example.com/search",  # 有些 API 校验 Referer
    "X-Requested-With": "XMLHttpRequest",     # 有些校验这个
})
data = resp.json()
```

## 4. 无限滚动（Playwright）

```python
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    page.goto(url, wait_until="networkidle")

    all_items = set()
    max_scrolls = 50  # 安全上限

    for i in range(max_scrolls):
        # 提取当前可见的数据
        items = page.query_selector_all(".item")
        new_count = 0
        for item in items:
            text = item.text_content()
            if text not in all_items:
                all_items.add(text)
                new_count += 1

        if new_count == 0:
            print(f"No new items after scroll {i+1}, stopping")
            break

        print(f"Scroll {i+1}: {new_count} new items (total: {len(all_items)})")
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        page.wait_for_timeout(2000)

    browser.close()
```

## 5. 登录态爬取

### 方法 A：用户提供 Cookie

```python
import httpx

cookies = {"session_id": "user_provided_value"}
with httpx.Client(cookies=cookies, timeout=30) as client:
    resp = client.get(protected_url)
```

### 方法 B：Playwright 自动登录

```python
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()

    # 登录
    page.goto("https://example.com/login")
    page.fill("#username", "user")
    page.fill("#password", "pass")
    page.click("#submit")
    page.wait_for_url("**/dashboard**")

    # 登录后爬取
    page.goto(target_url)
    # ...

    browser.close()
```

## 6. 数据输出模板

### JSON 输出

```python
import json, os

output_path = os.path.join(
    os.environ.get("TASKPOOL_USER_DESK", os.path.expanduser("~/desk")),
    f"task-{os.environ.get('TASKPOOL_TASK_ID', 'dev')}-scrape-result.json"
)
with open(output_path, "w", encoding="utf-8") as f:
    json.dump(results, f, ensure_ascii=False, indent=2)
print(f"Saved {len(results)} items to {output_path}")
```

### CSV 输出

```python
import csv, os

output_path = os.path.join(
    os.environ.get("TASKPOOL_USER_DESK", os.path.expanduser("~/desk")),
    f"task-{os.environ.get('TASKPOOL_TASK_ID', 'dev')}-scrape-result.csv"
)
with open(output_path, "w", encoding="utf-8-sig", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=results[0].keys())
    writer.writeheader()
    writer.writerows(results)
print(f"Saved {len(results)} rows to {output_path}")
```

## 7. UA 轮换

```python
import random

_USER_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.2 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:134.0) Gecko/20100101 Firefox/134.0",
]

def random_ua():
    return random.choice(_USER_AGENTS)
```

## 8. 重试与限速

```python
import time, httpx

def fetch_with_retry(client, url, max_retries=3, base_delay=2):
    for attempt in range(max_retries):
        try:
            resp = client.get(url)
            if resp.status_code == 429:
                wait = base_delay * (2 ** attempt)
                print(f"Rate limited, waiting {wait}s...")
                time.sleep(wait)
                continue
            resp.raise_for_status()
            return resp
        except httpx.HTTPStatusError as e:
            if e.response.status_code >= 500 and attempt < max_retries - 1:
                time.sleep(base_delay * (2 ** attempt))
                continue
            raise
    raise Exception(f"Failed after {max_retries} retries: {url}")
```

---

## 9. 断点续爬（Checkpoint/Resume）

批量爬取最常见的故障就是中途崩溃（网络超时、IP 被封、进程被杀）。核心思路：每爬完一条就记录进度，重启后跳过已完成的。

```python
import json, os, time

CHECKPOINT_FILE = os.path.join(
    os.environ.get("TASKPOOL_USER_DESK", os.path.expanduser("~/desk")),
    f"task-{os.environ.get('TASKPOOL_TASK_ID', 'dev')}-checkpoint.json"
)

def load_checkpoint():
    """加载已完成的 ID 集合"""
    if os.path.exists(CHECKPOINT_FILE):
        with open(CHECKPOINT_FILE, "r") as f:
            data = json.load(f)
            return set(data.get("done_ids", [])), data.get("results", [])
    return set(), []

def save_checkpoint(done_ids, results):
    """每条完成后立即写入"""
    with open(CHECKPOINT_FILE, "w") as f:
        json.dump({"done_ids": list(done_ids), "results": results}, f, ensure_ascii=False)

# 使用示例
done_ids, results = load_checkpoint()
print(f"Resuming: {len(done_ids)} already done")

for item_id in all_ids:
    if item_id in done_ids:
        continue  # 跳过已完成
    try:
        data = fetch_detail(item_id)
        results.append(data)
        done_ids.add(item_id)
        save_checkpoint(done_ids, results)  # 每条写一次
        print(f"Done: {item_id} ({len(done_ids)}/{len(all_ids)})")
        time.sleep(DELAY)
    except Exception as e:
        print(f"Failed: {item_id} — {e}")
        save_checkpoint(done_ids, results)  # 失败也保存进度
        # 可选: break 或 continue

print(f"Complete: {len(results)} items")
```

**关键设计**：
- checkpoint 文件用 JSON（不是 CSV），方便存储复杂结构
- `done_ids` 用 set，查找 O(1)
- 每条完成后立即 `save_checkpoint()`，不要攒批次
- 失败时也保存——下次重跑会跳过已成功的，只重试失败的
- 文件名含 task ID，多任务不冲突
