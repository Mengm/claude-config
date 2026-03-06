#!/usr/bin/env python3
"""Fetch and extract readable content from URLs.

Supports:
- WeChat articles (mp.weixin.qq.com) — direct HTML parsing
- Xiaohongshu / RedNote (xiaohongshu.com, xhslink.com) — SSR state parsing
- Bilibili videos (bilibili.com, b23.tv) — API-based metadata + subtitles + comments
- YouTube videos (youtube.com, youtu.be) — transcript + metadata
- General URLs — Jina Reader fallback

Usage:
    python3 web_read.py <url>
    python3 web_read.py --url <url> [--max-chars N]
"""

import argparse
import html
import json
import os
import re
import sys
from urllib.parse import urlparse
from datetime import datetime

from functools import reduce
from hashlib import md5
from urllib.parse import urlencode
import time

import httpx

_TIMEOUT = 30
_COOKIE_WARN_DAYS = 7  # warn when cookie expires within this many days
_MAX_BODY_CHARS = 5000  # truncate long body/transcript text
_MAX_COMMENTS = 20  # cap comments per platform
_MAX_JINA_CHARS = 8000  # truncate Jina/Firecrawl fallback output


def _truncate(text: str, max_chars: int, label: str = "content") -> str:
    """Truncate text with a total-length hint."""
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + f"\n\n... ({len(text)} chars total {label}, showing first {max_chars})"

# Domains that should use the CN proxy (domestic platforms)
_CN_DOMAINS = {
    "mp.weixin.qq.com",
    "weixin.qq.com",
    "xiaohongshu.com",
    "xhslink.com",
    "zhihu.com",
    "zhuanlan.zhihu.com",
    "bilibili.com",
    "b23.tv",
    "douyin.com",
    "toutiao.com",
    "baidu.com",
    "36kr.com",
    "ithome.com",
    "huxiu.com",
    "juejin.cn",
    "csdn.net",
    "jianshu.com",
    "weibo.com",
    "douban.com",
    "163.com",
    "qq.com",
    "sohu.com",
    "sina.com.cn",
    "thepaper.cn",
    "pedaily.cn",
}


def _needs_cn_proxy(url: str) -> bool:
    """Check if a URL's domain matches the CN proxy list."""
    try:
        host = urlparse(url).hostname or ""
    except Exception:
        return False
    for d in _CN_DOMAINS:
        if host == d or host.endswith("." + d):
            return True
    return False


def _get_cn_proxy() -> str | None:
    """Get CN proxy URL from environment."""
    return os.environ.get("CN_PROXY_URL") or None


def _check_cookie_expiry(platform: str) -> str | None:
    """Check if a platform's cookie is near expiry or expired.

    Returns a warning/error string to print to stderr, or None if OK.
    Env var format: {PLATFORM}_COOKIE_EXPIRES=YYYY-MM-DD
    """
    env_key = f"{platform.upper()}_COOKIE_EXPIRES"
    expires_str = os.environ.get(env_key)
    if not expires_str:
        return None
    try:
        expires = datetime.strptime(expires_str, "%Y-%m-%d")
    except ValueError:
        return None
    days_left = (expires - datetime.now()).days
    if days_left < 0:
        return f"WARNING: {platform} cookie expired {-days_left} days ago — update needed | env={env_key}"
    if days_left <= _COOKIE_WARN_DAYS:
        return f"WARNING: {platform} cookie expires in {days_left} day(s) — update soon | env={env_key}"
    return None


def _get_xhs_cookies() -> str:
    """Build XHS cookie string from environment variables."""
    parts = []
    a1 = os.environ.get("XHS_COOKIE_A1")
    if a1:
        parts.append(f"a1={a1}")
    ws = os.environ.get("XHS_COOKIE_WEB_SESSION")
    if ws:
        parts.append(f"web_session={ws}")
    wid = os.environ.get("XHS_COOKIE_WEB_ID")
    if wid:
        parts.append(f"webId={wid}")
    return "; ".join(parts)


def _make_client(**kwargs) -> httpx.Client:
    """Create an httpx client, adding CN proxy if the URL needs it."""
    url = kwargs.pop("_check_url", None)
    proxy = None
    if url and _needs_cn_proxy(url):
        proxy = _get_cn_proxy()
    return httpx.Client(proxy=proxy, trust_env=False, **kwargs)

_MOBILE_SAFARI_UA = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) "
    "Version/17.4 Mobile/15E148 Safari/604.1"
)

_WECHAT_RE = re.compile(r"https?://mp\.weixin\.qq\.com/s[/?\S]*")
_XHS_RE = re.compile(
    r"https?://(www\.)?xiaohongshu\.com/(discovery/item|explore)/\S*"
    r"|https?://xhslink\.com/\S*"
)
_XHS_IMG_CDN = "https://ci.xiaohongshu.com"

_BILIBILI_RE = re.compile(
    r"https?://(?:www\.|m\.)?bilibili\.com/video/(?:BV[\w]+|av\d+)"
    r"|https?://b23\.tv/\S+"
)
_BILIBILI_BV_RE = re.compile(r"(BV[\w]{10})")
_BILIBILI_AV_RE = re.compile(r"av(\d+)")

_YOUTUBE_RE = re.compile(
    r"(?:https?://)?(?:www\.|m\.|music\.)?(?:"
    r"youtu\.be/|"
    r"youtube\.com/(?:watch\?(?:.*&)?v=|embed/|v/|shorts/|live/)"
    r")([\w-]{11})"
)

# Zhihu URL patterns
_ZHIHU_ANSWER_RE = re.compile(
    r"https?://(?:www\.)?zhihu\.com/question/(\d+)/answer/(\d+)"
)
_ZHIHU_QUESTION_RE = re.compile(
    r"https?://(?:www\.)?zhihu\.com/question/(\d+)"
)
_ZHIHU_ARTICLE_RE = re.compile(
    r"https?://zhuanlan\.zhihu\.com/p/(\d+)"
)
_ZHIHU_RE = re.compile(
    r"https?://(?:www\.)?zhihu\.com/question/\d+"
    r"|https?://zhuanlan\.zhihu\.com/p/\d+"
)

# ZSXQ (知识星球) URL patterns
_ZSXQ_RE = re.compile(
    r"https?://(?:wx\.)?zsxq\.com/(?:dweb/)?topic/(\d+)"
    r"|https?://articles\.zsxq\.com/id_\w+\.html"
    r"|https?://t\.zsxq\.com/\S+"
)

# Bilibili WBI signing table
_WBI_MIXIN_KEY_ENC_TAB = [
    46, 47, 18, 2, 53, 8, 23, 32, 15, 50, 10, 31, 58, 3, 45, 35, 27, 43, 5, 49,
    33, 9, 42, 19, 29, 28, 14, 39, 12, 38, 41, 13, 37, 48, 7, 16, 24, 55, 40,
    61, 26, 17, 0, 1, 60, 51, 30, 4, 22, 25, 54, 21, 56, 59, 6, 63, 57, 62, 11,
    36, 20, 34, 44, 52,
]

_DESKTOP_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)


def _is_wechat_url(url: str) -> bool:
    return bool(_WECHAT_RE.match(url))


def _is_xhs_url(url: str) -> bool:
    return bool(_XHS_RE.match(url))


def _is_bilibili_url(url: str) -> bool:
    return bool(_BILIBILI_RE.match(url))


def _extract_youtube_id(url: str) -> str | None:
    m = _YOUTUBE_RE.search(url)
    return m.group(1) if m else None


def _is_youtube_url(url: str) -> bool:
    return _extract_youtube_id(url) is not None


def _is_zhihu_url(url: str) -> bool:
    return bool(_ZHIHU_RE.match(url))


def _is_zsxq_url(url: str) -> bool:
    return bool(_ZSXQ_RE.match(url))


def _resolve_short_url(url: str) -> str:
    """Resolve short URLs (e.g. xhslink.com, t.zsxq.com) to their final destination without proxy."""
    try:
        host = urlparse(url).hostname or ""
    except Exception:
        return url
    if host in ("xhslink.com", "b23.tv", "t.zsxq.com"):
        with httpx.Client(trust_env=False) as client:
            # t.zsxq.com returns 405 for HEAD, use GET instead
            method = "GET" if host == "t.zsxq.com" else "HEAD"
            resp = client.request(
                method, url, follow_redirects=True, timeout=10,
                headers={"User-Agent": _MOBILE_SAFARI_UA},
            )
            return str(resp.url)
    return url


def _fetch_xhs(url: str) -> dict | None:
    """Fetch a Xiaohongshu note and extract content from __INITIAL_STATE__.

    Tries CN proxy first, falls back to direct connection.
    Sends XHS cookies from env if available to reduce anti-bot blocks.
    """
    expiry_warn = _check_cookie_expiry("xhs")
    if expiry_warn:
        print(expiry_warn, file=sys.stderr)

    url = _resolve_short_url(url)
    headers = {
        "User-Agent": _MOBILE_SAFARI_UA,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Referer": "https://www.xiaohongshu.com/",
    }
    cookies = _get_xhs_cookies()
    if cookies:
        headers["Cookie"] = cookies

    raw = None
    # Try proxy first, then direct — one may bypass IP blocks the other hits
    for proxy in [_get_cn_proxy(), None]:
        with httpx.Client(proxy=proxy, trust_env=False) as client:
            resp = client.get(url, headers=headers, timeout=_TIMEOUT, follow_redirects=True)
        if resp.status_code != 200:
            continue
        # Check if redirected to security 404 page
        if "/404/" in str(resp.url):
            continue
        raw = resp.text
        break

    if raw is None:
        return None

    # Find __INITIAL_STATE__ JSON blob
    m = re.search(r"__INITIAL_STATE__\s*=\s*", raw)
    if not m:
        return None

    text = raw[m.end() :]
    # Find matching closing brace
    depth = 0
    end = 0
    for i, c in enumerate(text):
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
        if depth == 0:
            end = i + 1
            break
    if end == 0:
        return None

    json_str = text[:end].replace(":undefined", ":null")
    data = json.loads(json_str)

    note = data.get("noteData", {}).get("data", {}).get("noteData", {})
    if not note:
        return None

    user = note.get("user", {})
    title = note.get("title", "")
    desc = note.get("desc", "")
    author = user.get("nickName") or user.get("nickname") or ""

    # Images — build permanent URLs via ci.xiaohongshu.com
    images = []
    for img in note.get("imageList", []):
        file_id = img.get("fileId")
        if file_id:
            images.append(f"{_XHS_IMG_CDN}/{file_id}?imageView2/2/w/1080/format/jpg")

    # Tags
    tags = [t.get("name", "") for t in note.get("tagList", []) if t.get("name")]

    # Interaction stats
    interact = note.get("interactInfo", {})
    stats = {
        "likes": interact.get("likedCount", ""),
        "comments": interact.get("commentCount", ""),
        "collects": interact.get("collectedCount", ""),
        "shares": interact.get("shareCount", ""),
    }

    # Comments
    comment_data = data.get("noteData", {}).get("data", {}).get("commentData", {})
    comments = []
    for c in comment_data.get("comments", []):
        ts = ""
        if c.get("time"):
            ts = datetime.fromtimestamp(c["time"] / 1000).strftime("%m-%d %H:%M")
        comment = {
            "user": c.get("user", {}).get("nickname", ""),
            "location": c.get("ipLocation", ""),
            "time": ts,
            "content": c.get("content", ""),
            "likes": c.get("likeViewCount", "0"),
            "replies": [],
        }
        for sc in c.get("subComments", []):
            sc_ts = ""
            if sc.get("time"):
                sc_ts = datetime.fromtimestamp(sc["time"] / 1000).strftime("%m-%d %H:%M")
            comment["replies"].append(
                {
                    "user": sc.get("user", {}).get("nickname", ""),
                    "location": sc.get("ipLocation", ""),
                    "time": sc_ts,
                    "content": sc.get("content", ""),
                    "likes": sc.get("likeViewCount", "0"),
                }
            )
        comments.append(comment)

    return {
        "title": title,
        "author": author,
        "desc": desc,
        "images": images,
        "tags": tags,
        "stats": stats,
        "comments": comments,
    }


def _format_xhs(result: dict) -> str:
    """Format XHS note data into readable markdown."""
    parts = []
    if result["title"]:
        parts.append(f"# {result['title']}")
    if result["author"]:
        parts.append(f"**Author:** {result['author']}")
    if result["tags"]:
        parts.append("**Tags:** " + " ".join(f"#{t}" for t in result["tags"]))

    s = result["stats"]
    stats_items = []
    if s.get("likes"):
        stats_items.append(f"Likes: {s['likes']}")
    if s.get("comments"):
        stats_items.append(f"Comments: {s['comments']}")
    if s.get("collects"):
        stats_items.append(f"Collects: {s['collects']}")
    if s.get("shares"):
        stats_items.append(f"Shares: {s['shares']}")
    if stats_items:
        parts.append("**Stats:** " + " / ".join(stats_items))

    if result["images"]:
        img_list = "\n".join(f"- {img}" for img in result["images"])
        parts.append(f"\n**Images ({len(result['images'])}):**\n{img_list}")

    if result["desc"]:
        # Strip [话题]# markers for cleaner output
        desc = re.sub(r"\[话题\]#\s*", "", result["desc"])
        desc = _truncate(desc, _MAX_BODY_CHARS, "description")
        parts.append(f"\n---\n\n{desc}")

    if result["comments"]:
        shown = result["comments"][:_MAX_COMMENTS]
        total = len(result["comments"])
        extra = f" (showing {len(shown)}/{total})" if total > _MAX_COMMENTS else ""
        parts.append(f"\n---\n\n**Comments{extra}:**\n")
        for c in shown:
            loc = f" ({c['location']})" if c["location"] else ""
            parts.append(f"**{c['user']}**{loc} {c['time']}  [{c['likes']} likes]")
            parts.append(f"> {c['content']}")
            for r in c["replies"]:
                r_loc = f" ({r['location']})" if r["location"] else ""
                parts.append(f"  - **{r['user']}**{r_loc} {r['time']}  [{r['likes']} likes]")
                parts.append(f"    > {r['content']}")
            parts.append("")

    return "\n".join(parts)


def _fetch_wechat(url: str) -> dict | None:
    """Fetch a WeChat article and extract title, author, description, body text, and images."""
    with _make_client(_check_url=url) as client:
        resp = client.get(
            url,
            headers={
                "User-Agent": _MOBILE_SAFARI_UA,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
                "Referer": "https://mp.weixin.qq.com/",
            },
            timeout=_TIMEOUT,
            follow_redirects=True,
        )
    if resp.status_code != 200:
        return None

    raw = resp.text

    # Extract metadata from og: tags
    title = _extract_og(raw, "og:title") or _extract_var(raw, "msg_title") or ""
    description = _extract_og(raw, "og:description") or ""
    cover = _extract_og(raw, "og:image") or _extract_var(raw, "msg_cdn_url") or ""
    author = _extract_var(raw, "nickname") or _extract_og(raw, "og:article:author") or ""

    # Extract article body from div#js_content
    body_text = ""
    images = []
    match = re.search(r'<div[^>]*id="js_content"[^>]*>(.*)', raw, re.DOTALL)
    if match:
        body_html = match.group(1)
        # Cut at the tool bar area
        end = re.search(r'<div class="rich_media_tool"', body_html)
        if end:
            body_html = body_html[: end.start()]

        # Extract image URLs (data-src is the real URL in WeChat articles)
        images = re.findall(r'data-src="(https://mmbiz\.qpic\.cn/[^"]+)"', body_html)
        # Unescape HTML entities in image URLs
        images = [html.unescape(img) for img in images]

        # Strip HTML tags to get text
        body_text = re.sub(r"<[^>]+>", "\n", body_html)
        body_text = html.unescape(body_text)
        # Collapse whitespace
        lines = [l.strip() for l in body_text.split("\n") if l.strip()]
        body_text = "\n".join(lines)

        # Remove trailing JS noise
        for marker in ["var first_sceen__time", "预览时标签不可点"]:
            idx = body_text.find(marker)
            if idx != -1:
                body_text = body_text[:idx].rstrip()

    if not title and not body_text:
        return None

    return {
        "title": title,
        "author": author,
        "description": description,
        "cover": cover,
        "body": body_text,
        "images": images,
    }


def _extract_og(html_str: str, prop: str) -> str | None:
    m = re.search(rf'<meta property="{prop}"\s+content="([^"]*)"', html_str)
    return m.group(1) if m else None


def _extract_var(html_str: str, var_name: str) -> str | None:
    # Match: var nickname = htmlDecode("xxx") or var msg_title = 'xxx'
    m = re.search(rf'var {var_name}\s*=\s*htmlDecode\("([^"]*)"\)', html_str)
    if m:
        return html.unescape(m.group(1))
    m = re.search(rf"var {var_name}\s*=\s*'([^']*)'", html_str)
    if m:
        return html.unescape(m.group(1))
    m = re.search(rf'var {var_name}\s*=\s*"([^"]*)"', html_str)
    if m:
        return html.unescape(m.group(1))
    return None


# ---------------------------------------------------------------------------
# Bilibili
# ---------------------------------------------------------------------------

def _get_bili_cookies() -> str:
    """Build Bilibili cookie string from environment variables."""
    parts = []
    for key in ("BILI_SESSDATA", "BILI_JCT", "BILI_TICKET"):
        val = os.environ.get(key)
        if val:
            env_to_cookie = {
                "BILI_SESSDATA": "SESSDATA",
                "BILI_JCT": "bili_jct",
                "BILI_TICKET": "bili_ticket",
            }
            parts.append(f"{env_to_cookie[key]}={val}")
    return "; ".join(parts)


def _bili_wbi_sign(params: dict, img_key: str, sub_key: str) -> dict:
    """Sign params with Bilibili WBI."""
    mixin_key = reduce(lambda s, i: s + (img_key + sub_key)[i], _WBI_MIXIN_KEY_ENC_TAB, "")[:32]
    params["wts"] = round(time.time())
    params = dict(sorted(params.items()))
    params = {
        k: "".join(c for c in str(v) if c not in "!'()*")
        for k, v in params.items()
    }
    query = urlencode(params)
    params["w_rid"] = md5((query + mixin_key).encode()).hexdigest()
    return params


def _bili_get_wbi_keys(client: httpx.Client) -> tuple[str, str]:
    """Get current WBI img_key and sub_key."""
    resp = client.get(
        "https://api.bilibili.com/x/web-interface/nav",
        timeout=_TIMEOUT,
    )
    data = resp.json().get("data", {})
    wbi_img = data.get("wbi_img", {})
    img_url = wbi_img.get("img_url", "")
    sub_url = wbi_img.get("sub_url", "")
    img_key = img_url.rsplit("/", 1)[-1].split(".")[0] if img_url else ""
    sub_key = sub_url.rsplit("/", 1)[-1].split(".")[0] if sub_url else ""
    return img_key, sub_key


def _extract_bvid(url: str) -> str | None:
    """Extract BV ID from a Bilibili URL (after resolving short links)."""
    url = _resolve_short_url(url)
    m = _BILIBILI_BV_RE.search(url)
    if m:
        return m.group(1)
    m = _BILIBILI_AV_RE.search(url)
    if m:
        return None  # return None, caller will use aid
    return None


def _extract_bili_id(url: str) -> tuple[str | None, int | None]:
    """Extract bvid or aid from URL. Returns (bvid, aid)."""
    url = _resolve_short_url(url)
    m = _BILIBILI_BV_RE.search(url)
    if m:
        return m.group(1), None
    m = _BILIBILI_AV_RE.search(url)
    if m:
        return None, int(m.group(1))
    return None, None


def _fetch_bilibili(url: str) -> str | None:
    """Fetch Bilibili video info: metadata + subtitles + hot comments."""
    bvid, aid = _extract_bili_id(url)
    if not bvid and not aid:
        return None

    # Check cookie expiry
    expiry_warn = _check_cookie_expiry("bili")
    if expiry_warn:
        print(expiry_warn, file=sys.stderr)

    headers = {
        "User-Agent": _DESKTOP_UA,
        "Referer": "https://www.bilibili.com",
    }
    cookies = _get_bili_cookies()
    if cookies:
        headers["Cookie"] = cookies

    proxy = _get_cn_proxy()
    with httpx.Client(proxy=proxy, trust_env=False, headers=headers) as client:
        # 1. Video info
        params: dict = {}
        if bvid:
            params["bvid"] = bvid
        else:
            params["aid"] = aid
        resp = client.get(
            "https://api.bilibili.com/x/web-interface/view",
            params=params, timeout=_TIMEOUT,
        )
        info = resp.json()
        if info.get("code") != 0:
            return None
        vdata = info["data"]

        title = vdata.get("title", "")
        desc = vdata.get("desc", "")
        owner = vdata.get("owner", {})
        stat = vdata.get("stat", {})
        pages = vdata.get("pages", [])
        duration = vdata.get("duration", 0)
        bvid = bvid or vdata.get("bvid", "")
        actual_aid = vdata.get("aid", aid)
        cid = pages[0]["cid"] if pages else None

        # 2. Tags
        tag_resp = client.get(
            "https://api.bilibili.com/x/tag/archive/tags",
            params={"bvid": bvid} if bvid else {"aid": actual_aid},
            timeout=_TIMEOUT,
        )
        tags = []
        tag_data = tag_resp.json()
        if tag_data.get("code") == 0:
            tags = [t.get("tag_name", "") for t in tag_data.get("data", []) if t.get("tag_name")]

        # 3. Subtitles (requires SESSDATA for AI subs)
        subtitle_text = ""
        if cid:
            try:
                img_key, sub_key = _bili_get_wbi_keys(client)
                if img_key and sub_key:
                    sub_params = {"bvid": bvid, "cid": cid} if bvid else {"aid": actual_aid, "cid": cid}
                    signed = _bili_wbi_sign(sub_params, img_key, sub_key)
                    sub_resp = client.get(
                        "https://api.bilibili.com/x/player/wbi/v2",
                        params=signed, timeout=_TIMEOUT,
                    )
                    sub_data = sub_resp.json()
                    # -101 = not logged in (cookie expired or missing)
                    if sub_data.get("code") == -101:
                        print(
                            "WARNING: BILI_SESSDATA expired or invalid — subtitles unavailable, "
                            "please update cookie | env=BILI_SESSDATA",
                            file=sys.stderr,
                        )

                    subtitles_list = (
                        sub_data.get("data", {}).get("subtitle", {}).get("subtitles", [])
                    )
                    # Warn if logged in but no subtitles (possible auth issue)
                    if not subtitles_list and os.environ.get("BILI_SESSDATA"):
                        print(
                            "WARNING: BILI_SESSDATA set but no subtitles returned — "
                            "cookie may be expired | env=BILI_SESSDATA",
                            file=sys.stderr,
                        )
                    # Prefer AI Chinese, then any Chinese, then first available
                    sub_url = None
                    for pref in ("ai-zh", "zh-CN", "zh-Hans"):
                        for s in subtitles_list:
                            if s.get("lan") == pref:
                                sub_url = s.get("subtitle_url", "")
                                break
                        if sub_url:
                            break
                    if not sub_url and subtitles_list:
                        sub_url = subtitles_list[0].get("subtitle_url", "")

                    if sub_url:
                        if sub_url.startswith("//"):
                            sub_url = "https:" + sub_url
                        cc_resp = client.get(sub_url, timeout=_TIMEOUT)
                        cc_data = cc_resp.json()
                        all_lines = [item.get("content", "") for item in cc_data.get("body", [])]
                        # Cap subtitles at 300 lines to avoid token waste
                        if len(all_lines) > 300:
                            subtitle_text = "\n".join(all_lines[:300])
                            subtitle_text += f"\n\n... ({len(all_lines)} lines total, showing first 300)"
                        else:
                            subtitle_text = "\n".join(all_lines)
            except Exception:
                pass  # subtitles are optional

        # 4. Hot comments (legacy API, no WBI needed)
        comments = []
        try:
            comment_resp = client.get(
                "https://api.bilibili.com/x/v2/reply",
                params={
                    "type": 1,
                    "oid": actual_aid,
                    "sort": 1,  # by likes
                    "pn": 1,
                    "ps": 15,
                },
                timeout=_TIMEOUT,
            )
            cmt_data = comment_resp.json()
            if cmt_data.get("code") == 0:
                for c in (cmt_data.get("data", {}).get("replies") or [])[:15]:
                    member = c.get("member", {})
                    content = c.get("content", {})
                    ctime = c.get("ctime", 0)
                    ts = datetime.fromtimestamp(ctime).strftime("%Y-%m-%d %H:%M") if ctime else ""
                    comments.append({
                        "user": member.get("uname", ""),
                        "level": member.get("level_info", {}).get("current_level", 0),
                        "time": ts,
                        "content": content.get("message", ""),
                        "likes": c.get("like", 0),
                        "replies_count": c.get("rcount", 0),
                    })
        except Exception:
            pass  # comments are optional

    # Format output
    return _format_bilibili(
        title=title, desc=desc, owner=owner, stat=stat, tags=tags,
        duration=duration, bvid=bvid, subtitle_text=subtitle_text,
        comments=comments, pages=pages,
    )


def _format_bilibili(
    title: str, desc: str, owner: dict, stat: dict, tags: list,
    duration: int, bvid: str, subtitle_text: str,
    comments: list, pages: list,
) -> str:
    """Format Bilibili video data into readable markdown."""
    parts = []
    if title:
        parts.append(f"# {title}")

    parts.append(f"**UP主:** {owner.get('name', '')}")
    parts.append(f"**BV号:** {bvid}")

    mins, secs = divmod(duration, 60)
    hours, mins = divmod(mins, 60)
    dur_str = f"{hours}:{mins:02d}:{secs:02d}" if hours else f"{mins}:{secs:02d}"
    parts.append(f"**时长:** {dur_str}")

    if tags:
        parts.append("**标签:** " + " ".join(f"#{t}" for t in tags))

    stats_items = []
    for label, key in [
        ("播放", "view"), ("弹幕", "danmaku"), ("评论", "reply"),
        ("点赞", "like"), ("投币", "coin"), ("收藏", "favorite"), ("分享", "share"),
    ]:
        val = stat.get(key, 0)
        if val:
            stats_items.append(f"{label}: {val:,}")
    if stats_items:
        parts.append("**数据:** " + " / ".join(stats_items))

    if len(pages) > 1:
        page_list = ", ".join(f"P{p['page']}: {p.get('part', '')}" for p in pages[:10])
        if len(pages) > 10:
            page_list += f" ... (共{len(pages)}P)"
        parts.append(f"**分P:** {page_list}")

    if desc:
        parts.append(f"\n---\n\n**简介:**\n{desc}")

    if subtitle_text:
        parts.append(f"\n---\n\n**字幕全文:**\n{subtitle_text}")

    if comments:
        parts.append("\n---\n\n**热门评论:**\n")
        for c in comments:
            parts.append(
                f"**{c['user']}** (Lv{c['level']}) {c['time']}  "
                f"[{c['likes']} 赞 / {c['replies_count']} 回复]"
            )
            parts.append(f"> {c['content']}")
            parts.append("")

    return "\n".join(parts)


# ---------------------------------------------------------------------------
# YouTube
# ---------------------------------------------------------------------------

def _fetch_youtube(url: str) -> str | None:
    """Fetch YouTube video transcript + metadata via youtube-transcript-api + oEmbed."""
    video_id = _extract_youtube_id(url)
    if not video_id:
        return None

    # 1. Metadata via oEmbed (lightweight, no API key)
    meta = {}
    try:
        with httpx.Client(trust_env=False) as client:
            resp = client.get(
                "https://www.youtube.com/oembed",
                params={"url": f"https://www.youtube.com/watch?v={video_id}", "format": "json"},
                timeout=_TIMEOUT,
            )
            if resp.status_code == 200:
                meta = resp.json()
    except Exception:
        pass

    # 2. Transcript via youtube-transcript-api
    transcript_text = ""
    transcript_lang = ""
    try:
        from youtube_transcript_api import YouTubeTranscriptApi

        ytt = YouTubeTranscriptApi()
        # Try Chinese first, then English, then any available
        fetched = None
        for langs in [["zh-Hans", "zh-Hant", "zh"], ["en"], None]:
            try:
                if langs:
                    fetched = ytt.fetch(video_id, languages=langs)
                else:
                    # Try to get any available transcript
                    transcript_list = ytt.list(video_id)
                    for t in transcript_list:
                        fetched = t.fetch()
                        transcript_lang = t.language
                        break
                if fetched:
                    if not transcript_lang:
                        transcript_lang = langs[0] if langs else "unknown"
                    break
            except Exception:
                continue

        if fetched:
            transcript_text = "\n".join(s.text for s in fetched)
    except ImportError:
        transcript_text = "[youtube-transcript-api not installed]"
    except Exception:
        pass

    if not meta and not transcript_text:
        return None

    return _format_youtube(meta, video_id, transcript_text, transcript_lang)


def _format_youtube(meta: dict, video_id: str, transcript: str, lang: str) -> str:
    """Format YouTube video data into readable markdown."""
    parts = []

    title = meta.get("title", "")
    if title:
        parts.append(f"# {title}")

    author = meta.get("author_name", "")
    if author:
        author_url = meta.get("author_url", "")
        parts.append(f"**Channel:** {author}" + (f" ({author_url})" if author_url else ""))

    parts.append(f"**Video ID:** {video_id}")
    parts.append(f"**URL:** https://www.youtube.com/watch?v={video_id}")

    thumbnail = meta.get("thumbnail_url", "")
    if thumbnail:
        parts.append(f"**Thumbnail:** {thumbnail}")

    if transcript:
        transcript = _truncate(transcript, _MAX_BODY_CHARS, "transcript")
        lang_note = f" ({lang})" if lang else ""
        parts.append(f"\n---\n\n**Transcript{lang_note}:**\n{transcript}")
    else:
        parts.append("\n---\n\n*No transcript/subtitles available for this video.*")

    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Zhihu
# ---------------------------------------------------------------------------

def _get_zhihu_cookies() -> str:
    """Build Zhihu cookie string from environment variables."""
    parts = []
    mapping = {
        "ZHIHU_COOKIE_Z_C0": "z_c0",
        "ZHIHU_COOKIE_ZSE_CK": "__zse_ck",
        "ZHIHU_COOKIE_XSRF": "_xsrf",
        "ZHIHU_COOKIE_ZAP": "_zap",
    }
    for env_key, cookie_name in mapping.items():
        val = os.environ.get(env_key)
        if val:
            parts.append(f"{cookie_name}={val}")
    return "; ".join(parts)


def _fetch_zhihu(url: str) -> str | None:
    """Fetch Zhihu content.

    Strategy: API first (fast, structured), Firecrawl fallback (reliable).
    Zhihu aggressively rate-limits cloud IPs on API, so Firecrawl with
    waitFor=5000 is the reliable fallback for all URL types.
    z_c0 (login session) significantly improves API success rate.
    """
    expiry_warn = _check_cookie_expiry("zhihu")
    if expiry_warn:
        print(expiry_warn, file=sys.stderr)

    headers = {
        "User-Agent": _DESKTOP_UA,
        "Referer": "https://www.zhihu.com/",
    }
    cookies = _get_zhihu_cookies()
    if cookies:
        headers["Cookie"] = cookies
    proxy = _get_cn_proxy()

    def _firecrawl_truncated(u: str) -> str | None:
        result = _fetch_firecrawl(u, wait_for=5000)
        return _truncate(result, _MAX_BODY_CHARS, "zhihu page") if result else None

    # Case 1: specific answer URL — API first, Firecrawl fallback
    m = _ZHIHU_ANSWER_RE.match(url)
    if m:
        aid = m.group(2)
        result = _fetch_zhihu_answer(aid, headers, proxy)
        if result:
            return result
        return _firecrawl_truncated(url)

    # Case 2: question page — Firecrawl (API needs x-zse signing)
    m = _ZHIHU_QUESTION_RE.match(url)
    if m:
        return _firecrawl_truncated(url)

    # Case 3: zhuanlan article — Firecrawl (API needs signing)
    m = _ZHIHU_ARTICLE_RE.match(url)
    if m:
        return _firecrawl_truncated(url)

    return None


def _fetch_zhihu_answer(answer_id: str, headers: dict, proxy: str | None) -> str | None:
    """Fetch a single Zhihu answer via API.

    Zhihu aggressively rate-limits cloud IPs. Retries once after a short
    delay on 403.
    """
    resp = None
    for attempt in range(2):
        if attempt > 0:
            time.sleep(5)
        with httpx.Client(proxy=proxy, trust_env=False) as client:
            resp = client.get(
                f"https://www.zhihu.com/api/v4/answers/{answer_id}",
                params={"include": "content,excerpt,voteup_count,comment_count"},
                headers=headers, timeout=_TIMEOUT,
            )
        if resp.status_code == 200:
            break
    if resp is None or resp.status_code != 200:
        return None
    data = resp.json()
    if "error" in data:
        return None

    question = data.get("question", {})
    author = data.get("author", {})
    content_html = data.get("content", "")
    content_text = re.sub(r"<[^>]+>", "", content_html).strip() if content_html else ""
    excerpt = data.get("excerpt", "")
    voteup = data.get("voteup_count", 0)
    comments = data.get("comment_count", 0)
    created = data.get("created_time", 0)

    parts = []
    q_title = question.get("title", "")
    if q_title:
        parts.append(f"# {q_title}")
    author_name = author.get("name", "匿名用户")
    parts.append(f"**回答者:** {author_name}")
    if voteup:
        parts.append(f"**赞同:** {voteup:,}")
    if comments:
        parts.append(f"**评论:** {comments:,}")
    if created:
        ts = datetime.fromtimestamp(created).strftime("%Y-%m-%d")
        parts.append(f"**日期:** {ts}")

    if content_text:
        content_text = _truncate(content_text, _MAX_BODY_CHARS, "answer")
        parts.append(f"\n---\n\n{content_text}")
    elif excerpt:
        parts.append(f"\n---\n\n{excerpt}")

    return "\n".join(parts) if any([content_text, excerpt]) else None



def _fetch_jina(url: str) -> str | None:
    """Fetch URL content via Jina Reader (free, no API key needed)."""
    # Jina Reader is an international service — never use CN proxy
    with httpx.Client(trust_env=False) as client:
        resp = client.get(
            f"https://r.jina.ai/{url}",
            headers={"Accept": "text/markdown"},
            timeout=_TIMEOUT,
            follow_redirects=True,
        )
    if resp.status_code == 200 and resp.text.strip():
        return resp.text.strip()
    return None


def _fetch_firecrawl(url: str, wait_for: int = 0) -> str | None:
    """Fetch URL content via Firecrawl API (JS rendering, anti-bot bypass).

    Args:
        wait_for: ms to wait after page load before scraping (for JS-heavy sites).
    """
    api_key = os.environ.get("FIRECRAWL_API_KEY")
    if not api_key:
        return None
    payload: dict = {"url": url, "formats": ["markdown"]}
    if wait_for:
        payload["waitFor"] = wait_for
    with httpx.Client(trust_env=False) as client:
        resp = client.post(
            "https://api.firecrawl.dev/v1/scrape",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=60 + (wait_for // 1000),
        )
    if resp.status_code != 200:
        return None
    data = resp.json()
    if not data.get("success"):
        return None
    md = data.get("data", {}).get("markdown", "")
    return md.strip() if md else None


def _extract_zsxq_topic_id(url: str) -> str | None:
    """Extract topic_id from various ZSXQ URL formats."""
    url = _resolve_short_url(url)
    # wx.zsxq.com/topic/{topic_id} or wx.zsxq.com/dweb/topic/{topic_id}
    m = re.search(r"zsxq\.com/(?:dweb/)?topic/(\d+)", url)
    if m:
        return m.group(1)
    # articles.zsxq.com/id_{topic_id}.html
    m = re.search(r"articles\.zsxq\.com/id_(\w+)\.html", url)
    if m:
        return m.group(1)
    return None


def _fetch_zsxq(url: str) -> str | None:
    """Fetch a ZSXQ (知识星球) topic via API.

    Requires ZSXQ_ACCESS_TOKEN env var (cookie-based auth, v2 API only).
    """
    token = os.environ.get("ZSXQ_ACCESS_TOKEN", "")
    if not token:
        print("ERROR: ZSXQ_ACCESS_TOKEN not set — cannot fetch ZSXQ content", file=sys.stderr)
        return None

    # Resolve short links (t.zsxq.com/xxx) to canonical wx.zsxq.com/topic/{id}
    url = _resolve_short_url(url)
    topic_id = _extract_zsxq_topic_id(url)
    if not topic_id:
        print(f"ERROR: cannot extract topic_id from ZSXQ URL | url={url}", file=sys.stderr)
        return None

    headers = {
        "Accept": "application/json",
        "Origin": "https://wx.zsxq.com",
        "Referer": "https://wx.zsxq.com/",
        "User-Agent": _DESKTOP_UA,
        "X-Version": "2.89.0",
    }
    cookies = {"zsxq_access_token": token}

    with _make_client(_check_url="https://api.zsxq.com/") as client:
        # Fetch topic
        resp = client.get(
            f"https://api.zsxq.com/v2/topics/{topic_id}",
            headers=headers,
            cookies=cookies,
            timeout=_TIMEOUT,
        )
        if resp.status_code != 200:
            print(f"ERROR: ZSXQ API returned {resp.status_code} | topic_id={topic_id}", file=sys.stderr)
            return None
        data = resp.json()
        if not data.get("succeeded"):
            code = data.get("code", "unknown")
            print(f"ERROR: ZSXQ API error code={code} | topic_id={topic_id}", file=sys.stderr)
            return None
        topic = data["resp_data"].get("topic", {})

        # Fetch comments
        comments = []
        try:
            cr = client.get(
                f"https://api.zsxq.com/v2/topics/{topic_id}/comments?count=20&sort=asc",
                headers=headers,
                cookies=cookies,
                timeout=_TIMEOUT,
            )
            if cr.status_code == 200:
                cd = cr.json()
                if cd.get("succeeded"):
                    comments = cd.get("resp_data", {}).get("comments", [])
        except Exception:
            pass  # comments are optional

    return _format_zsxq_topic(topic, comments)


def _format_zsxq_topic(topic: dict, comments: list) -> str:
    """Format a ZSXQ topic + comments into readable markdown."""
    parts = []
    topic_type = topic.get("type", "")
    create_time = topic.get("create_time", "")[:19]

    # Title / header
    if topic_type == "talk":
        talk = topic.get("talk", {})
        owner = talk.get("owner", {})
        text = talk.get("text", "")
        parts.append(f"# {owner.get('name', '未知')} 的帖子")
        parts.append(f"**时间:** {create_time}")
        if owner.get("description"):
            parts.append(f"**作者简介:** {owner['description']}")
        parts.append(f"\n---\n\n{_truncate(text, _MAX_BODY_CHARS, 'post')}")
        # Images
        images = talk.get("images", [])
        if images:
            img_lines = []
            for img in images[:5]:
                orig = img.get("original", {}).get("url") or img.get("large", {}).get("url", "")
                if orig:
                    img_lines.append(f"- {orig}")
            if img_lines:
                extra = f" (showing 5/{len(images)})" if len(images) > 5 else ""
                parts.append(f"\n**图片 ({len(images)}{extra}):**\n" + "\n".join(img_lines))

    elif topic_type == "q&a":
        question = topic.get("question", {})
        answer = topic.get("answer", {})
        q_owner = question.get("owner", {})
        a_owner = answer.get("owner", {})
        parts.append(f"# 问答: {q_owner.get('name', '未知')} → {a_owner.get('name', '未知')}")
        parts.append(f"**时间:** {create_time}")
        parts.append(f"\n**问题:**\n{_truncate(question.get('text', ''), _MAX_BODY_CHARS, 'question')}")
        if answer.get("text"):
            parts.append(f"\n**回答:**\n{_truncate(answer['text'], _MAX_BODY_CHARS, 'answer')}")
        # Answer images
        images = answer.get("images", [])
        if images:
            img_lines = []
            for img in images[:5]:
                orig = img.get("original", {}).get("url") or img.get("large", {}).get("url", "")
                if orig:
                    img_lines.append(f"- {orig}")
            if img_lines:
                parts.append(f"\n**图片:**\n" + "\n".join(img_lines))
    else:
        parts.append(f"# 知识星球帖子")
        parts.append(f"**类型:** {topic_type}")
        parts.append(f"**时间:** {create_time}")

    # Stats
    stats = []
    if topic.get("likes_count"):
        stats.append(f"赞 {topic['likes_count']}")
    if topic.get("comments_count"):
        stats.append(f"评论 {topic['comments_count']}")
    if topic.get("readers_count"):
        stats.append(f"阅读 {topic['readers_count']}")
    if topic.get("digested"):
        stats.append("精华")
    if stats:
        parts.append(f"\n**互动:** {' / '.join(stats)}")

    # Comments
    if comments:
        parts.append(f"\n**评论 (前{len(comments)}条):**")
        for c in comments[:_MAX_COMMENTS]:
            c_owner = c.get("owner", {})
            c_text = c.get("text", "")
            c_likes = c.get("likes_count", 0)
            reply_to = ""
            if c.get("repliee"):
                reply_to = f" → @{c['repliee'].get('name', '')}"
            likes_str = f" [{c_likes}赞]" if c_likes else ""
            parts.append(f"- **{c_owner.get('name', '未知')}**{reply_to}: {c_text}{likes_str}")

    return "\n".join(parts)


def main():
    parser = argparse.ArgumentParser(description="Fetch readable content from a URL")
    parser.add_argument("url_positional", nargs="?", help="URL to fetch")
    parser.add_argument("--url", help="URL to fetch")
    parser.add_argument("--max-chars", type=int, default=0, help="Truncate output (0=unlimited)")
    args = parser.parse_args()

    url = args.url or args.url_positional
    if not url:
        print("ERROR: no URL provided", file=sys.stderr)
        sys.exit(1)

    try:
        if _is_wechat_url(url):
            result = _fetch_wechat(url)
            if not result:
                print(f"ERROR: failed to fetch WeChat article | url={url}", file=sys.stderr)
                sys.exit(1)

            output_parts = []
            if result["title"]:
                output_parts.append(f"# {result['title']}")
            if result["author"]:
                output_parts.append(f"**Author:** {result['author']}")
            if result["description"]:
                output_parts.append(f"**Description:** {result['description']}")
            if result["cover"]:
                output_parts.append(f"**Cover:** {result['cover']}")
            if result["images"]:
                shown = result["images"][:5]
                img_list = "\n".join(f"- {img}" for img in shown)
                extra = f" (showing 5/{len(result['images'])})" if len(result["images"]) > 5 else ""
                output_parts.append(f"\n**Images ({len(result['images'])}{extra}):**\n{img_list}")
            if result["body"]:
                body = _truncate(result["body"], _MAX_BODY_CHARS, "article")
                output_parts.append(f"\n---\n\n{body}")

            output = "\n".join(output_parts)
        elif _is_xhs_url(url):
            result = _fetch_xhs(url)
            if not result:
                print(f"ERROR: failed to fetch Xiaohongshu note | url={url}", file=sys.stderr)
                sys.exit(1)
            output = _format_xhs(result)
        elif _is_bilibili_url(url):
            output = _fetch_bilibili(url)
            if not output:
                print(f"ERROR: failed to fetch Bilibili video | url={url}", file=sys.stderr)
                sys.exit(1)
        elif _is_youtube_url(url):
            output = _fetch_youtube(url)
            if not output:
                print(f"ERROR: failed to fetch YouTube video | url={url}", file=sys.stderr)
                sys.exit(1)
        elif _is_zhihu_url(url):
            output = _fetch_zhihu(url)
            if not output:
                print(f"ERROR: failed to fetch Zhihu content | url={url}", file=sys.stderr)
                sys.exit(1)
        elif _is_zsxq_url(url):
            output = _fetch_zsxq(url)
            if not output:
                print(f"ERROR: failed to fetch ZSXQ content | url={url}", file=sys.stderr)
                sys.exit(1)
        else:
            content = _fetch_jina(url)
            if not content:
                # Firecrawl fallback: JS rendering + anti-bot bypass
                content = _fetch_firecrawl(url)
            if not content:
                print(f"ERROR: failed to fetch URL (tried Jina + Firecrawl) | url={url}", file=sys.stderr)
                sys.exit(1)
            output = _truncate(content, _MAX_JINA_CHARS, "page")

        if args.max_chars and len(output) > args.max_chars:
            total_chars = len(output)
            output = output[: args.max_chars] + f"\n\n... (truncated at {args.max_chars} of {total_chars} chars)"

        print(output)

    except httpx.TimeoutException:
        print(f"ERROR: timeout fetching url={url}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"ERROR: {e} | url={url}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
