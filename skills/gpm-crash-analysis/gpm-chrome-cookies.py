"""
从本地 Chrome 浏览器读取 GPM/SSO cookies，保存为 gpm-api.js 可用的格式。
前提：Chrome 中已登录过 gpm.bytedance.com（通过飞书 SSO）。

用法：python gpm-chrome-cookies.py
输出：cookies.json（与 gpm-api.js 兼容）
"""

import json
import os
import sys

try:
    import browser_cookie3
except ImportError:
    print("[ERROR] browser_cookie3 not installed. Run: pip install browser_cookie3")
    sys.exit(1)


def main():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    cookies_file = os.path.join(script_dir, "cookies.json")

    print("[*] Reading cookies from Chrome...")
    print("[*] Make sure you have logged into gpm.bytedance.com in Chrome.\n")

    try:
        cj = browser_cookie3.chrome(domain_name=".bytedance.com")
    except Exception as e:
        print(f"[ERROR] Failed to read Chrome cookies: {e}")
        print("[TIP] Make sure Chrome is closed, or try running as Administrator.")
        sys.exit(1)

    # Collect cookies for relevant domains
    target_domains = [".bytedance.com", "bytedance.com", ".feishu.cn", "feishu.cn"]
    cookies = []

    for cookie in cj:
        if any(d in cookie.domain for d in target_domains):
            cookies.append({
                "name": cookie.name,
                "value": cookie.value,
                "domain": cookie.domain,
                "path": cookie.path,
                "expires": cookie.expires or -1,
                "httpOnly": bool(getattr(cookie, "_rest", {}).get("HttpOnly", False)),
                "secure": cookie.secure,
            })

    if not cookies:
        print("[ERROR] No GPM/bytedance cookies found in Chrome.")
        print("[TIP] Open Chrome and login to https://gpm.bytedance.com first.")
        sys.exit(1)

    # Also try to get feishu.cn cookies for SSO
    try:
        cj_feishu = browser_cookie3.chrome(domain_name=".feishu.cn")
        for cookie in cj_feishu:
            if any(d in cookie.domain for d in target_domains):
                # Avoid duplicates
                if not any(c["name"] == cookie.name and c["domain"] == cookie.domain for c in cookies):
                    cookies.append({
                        "name": cookie.name,
                        "value": cookie.value,
                        "domain": cookie.domain,
                        "path": cookie.path,
                        "expires": cookie.expires or -1,
                        "httpOnly": bool(getattr(cookie, "_rest", {}).get("HttpOnly", False)),
                        "secure": cookie.secure,
                    })
    except Exception:
        pass  # feishu cookies are optional

    saved = {
        "cookies": cookies,
        "savedAt": __import__("datetime").datetime.now().isoformat(),
        "source": "chrome",
        "expiresHint": "Cookies from Chrome. Re-run this script if API returns 401.",
    }

    with open(cookies_file, "w", encoding="utf-8") as f:
        json.dump(saved, f, indent=2, ensure_ascii=False)

    domains = list(set(c["domain"] for c in cookies))
    print(f"[*] Saved {len(cookies)} cookies to {cookies_file}")
    print(f"[*] Domains: {', '.join(domains)}")
    print("\n[*] Done! gpm-api.js will automatically use these cookies.")


if __name__ == "__main__":
    main()
