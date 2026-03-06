# 实战踩坑经验

从 web-read skill 和项目实际使用中积累的爬虫经验。批量场景比单次请求风险更高，这些教训在批量爬取时尤其重要。

## 1. 调第三方私有 API：先查库源码（field-note #33）

**反模式**：凭空猜 API 端点（`/api/gallery/creator/note/user/posted`）→ 返回 `{"success": true, "notes": []}` → 花大量时间试 6 个变体 → 最后发现正确端点在 xhs 库源码里早就写好了。

**正确做法**：
```python
import inspect
from xhs import XhsClient
# 先看库怎么调的
print(inspect.getsource(XhsClient.get_notes_statistics))
```

第三方私有 API 没有公开文档，**已有库的源码就是唯一的"文档"**。不要猜端点、猜 header、猜签名方式。

## 2. 先小批验证再全量（field-note #32）

**反模式**：一口气写完分页逻辑 + 解析 + 输出 + 反爬 → 全部提交 → 回头发现 API 字段名不对、cookie 过期、解析逻辑错误。

**正确做法**：
1. 先用 curl 或单行 Python 测试 1 个请求，确认有数据返回
2. 解析第 1 页的结构，确认字段名
3. 扩展到分页逻辑，爬 3-5 页验证
4. 确认无误后再全量

## 3. "success: true + 空数据"陷阱（field-note #33）

**最危险的响应**：代码不报错、HTTP 200、结构正确，但数据为空。常见原因：
- Cookie/session 过期（还能请求但没权限看数据）
- 端点路径错误（服务器兜底返回空结构）
- 参数名拼错（被忽略而非报错）
- Referer/Origin header 缺失

**判断标准**：必须看到有实际内容的成功响应才算验证通过。

## 4. 云服务器 IP 反爬（field-note #35）

**实测结果**（小红书）：
- 所有 `xiaohongshu.com/explore/*` 和 `/discovery/item/*` URL 被重定向到 `/404/sec_*` 安全页面
- `__INITIAL_STATE__` HTML 标签存在但 `noteData.data.noteData` 为空
- edith API cookie 频繁过期（`{"code": -100, "msg": "登录已过期"}`）
- `site:xiaohongshu.com` 搜索引擎搜索几乎无效（JS 渲染页面不被索引）

**实测结果**（知乎）：
- 云服务器 IP 被限流，API 返回 403 错误码 40362
- 需要 Firecrawl 兜底（`waitFor=5000` 让 JS 渲染完成）

**应对策略**：
- 优先使用 `CN_PROXY_URL` 代理
- 批量场景间隔加大到 2-3 秒
- 被封后不要密集重试，会加速触发永久封禁
- 考虑用 API 替代页面爬取（如 xhs 库的 API 方法）

## 5. 代理架构经验（web-read anti-crawl.md）

**按域名精确路由**，不用全局代理：
- `CN_PROXY_URL` 仅用于 `_CN_DOMAINS` 列表中的国内平台
- `trust_env=False` 确保 httpx 不读系统代理变量
- 短链域名（xhslink.com, b23.tv）先直连解析短链，再走代理访问目标

**阿里云代理的坑**：
- HTTP 明文出站有 ICP 检查（未备案 403），HTTPS CONNECT 隧道不受影响
- `xhslink.com` 对阿里云 IP 段做 SNI 检测/IP 封禁

## 6. Cookie 管理

- Cookie 会过期，批量爬取前先验证有效性（发一个测试请求）
- 项目已有 per-user cookie 绑定机制（XHS、B站、知乎、知识星球）
- Cookie 过期检测逻辑参考 web-read 的 `_COOKIE_WARN_DAYS` 机制
- 环境变量：`XHS_COOKIE_*`、`BILI_SESSDATA`、`ZHIHU_COOKIE_*`、`ZSXQ_ACCESS_TOKEN`

## 7. 字段完整性验证——列表 API ≠ 详情 API（field-note #36）

**反模式**：成都 12345 列表 API 跑了 32,148 条后才发现只返回标题/日期/部门，不含正文和回复。然后花大量时间逆向详情 API（参数名、嵌套格式、Playwright DOM 提取），写增量补充脚本。

**正确做法**：
1. 跑完前 10 条后，打印所有字段名和样本值
2. 对照需求检查：哪些字段是分析必需的？缺了哪些？
3. 如果列表 API 缺字段，**立即**探查详情 API，不要等全量跑完
4. 字段检查清单写进脚本注释或 README，避免下次重复踩坑

**判断标准**：`必需字段全部有非空值` 才算验证通过，不是 `脚本能跑不报错` 就算通过。

## 8. 分页去重验证——爬到的数据可能全是重复的（field-note #36）

**反模式**：武汉城市留言板爬了 9,840 条，看起来正常。分析时才发现只有 20 条唯一记录，重复了 492 次——分页参数没生效，每页返回相同数据。

**正确做法**：
1. 爬完前 3 页后，对比第 1 页和第 3 页的数据是否相同
2. 用 `set(record['id'] for record in data)` 检查唯一 ID 数量
3. 如果没有唯一 ID，用标题 + 时间组合去重
4. 唯一记录数 / 总记录数 < 90% → 分页逻辑有 bug，停下来排查

**判断标准**：`唯一记录占比 > 95%` 才继续全量跑。低于这个值就是分页参数没生效。

## 9. 一手数据优先（field-note #34）

有能力直接抓取时，**先抓 10 篇同赛道原始内容 + 评论 + 数据**，再看二手分析做交叉验证。二手分析有来源偏差（卖课号）和赛道偏差（美妆规律不适用于 AI 工具）。
