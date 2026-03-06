# 反爬经验与代理架构

## 代理架构

按域名精确路由，不用全局代理：

```
请求 URL
  ├─ 命中 _CN_DOMAINS 列表 → 走 CN_PROXY_URL（阿里云 tinyproxy）
  ├─ 短链域名（xhslink.com, b23.tv）→ 先直连解析短链 → 再走代理访问目标
  └─ 其他 → 直连（不走代理）
```

- `CN_PROXY_URL`（非 `HTTP_PROXY`）— 仅 web-read 读取，不污染全局 httpx
- `trust_env=False` 确保 httpx 不读系统代理变量

## 阿里云代理的坑

- **ICP 备案拦截**：阿里云 ECS 对 HTTP 明文出站请求做 ICP 检查，未备案域名返回 403。HTTPS CONNECT 隧道不受影响
- **短链域名 TLS 重置**：`xhslink.com` 对阿里云 IP 段做 SNI 检测/IP 封禁。解决：客户端侧先直连 HEAD 解析短链，再走代理访问主站域名
- **云 IP 反爬标记**：云厂商 IP 段（阿里云、AWS 等）容易被反爬系统标记，频繁请求会触发临时封禁

## 小红书反爬

### SSR 数据提取

移动端 UA 请求后，`__INITIAL_STATE__` JSON 包含完整数据：
- `noteData.data.noteData` — 标题、正文、标签、图片列表
- `noteData.data.commentData` — 评论区（含楼中楼、IP 归属地）
- `noteData.data.noteData.interactInfo` — 互动数据（赞/评/藏/转）
- `noteData.data.noteData.user` — 作者信息（字段名 `nickName` 不是 `nickname`）
- JSON 中有 `:undefined`（非标准），需先替换为 `:null` 再 parse

### 图片 CDN 签名绕过

```
CDN（带签名）: sns-webpic-qc.xhscdn.com/{timestamp}/{sig}/{fileId}!h5_1080jpg  → 有时效，过期 403
源站（无签名）: ci.xiaohongshu.com/{fileId}?imageView2/2/w/1080/format/jpg     → 永久可用 ✅
```

`fileId` 从 `__INITIAL_STATE__` 的 `imageList[].fileId` 获取。

### 通用 CDN 绕过方法论

1. 从页面数据提取 `fileId`/资源标识符
2. 用备用 CDN 域名逐个测试（`ci.`/`img.`/`static.` + 主域名）
3. 去掉签名部分，只带 fileId

## 微信公众号

- 图片 URL（`mmbiz.qpic.cn`）无签名，永久有效，直接从 `data-src` 提取
- 用移动端 Safari UA + httpx 直接抓 HTML，提取 `og:title`、`msg_title`、`js_content` 等
- WebFetch / Jina Reader 均无法读取（302 验证码拦截）

## 排障原则

- **先验证 URL 有效性**：微信文章会过期/删除，小红书短链会失效。先用 log 中成功过的 URL 确认
- **不要对反爬站点密集重试** — 会加速触发临时封禁，污染后续所有测试
- **不同平台反爬思路有共性**：移动端 UA + HTML/JSON 直接解析
