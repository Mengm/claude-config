---
name: notify
description: 发送通知（短信/邮件）。当用户要求发短信、发邮件、通知、提醒时触发。也可被 scheduler 定时任务、其他 skill 组合调用。
---

# 通知发送

支持两种通道：短信（UniSMS）和邮件（Resend）。根据用户意图选择通道。

## 环境变量

在项目根目录 `.env` 中配置：

```
# 短信 - UniSMS
UNISMS_ACCESS_KEY_ID=xxxx
UNISMS_ACCESS_KEY_SECRET=xxxx
UNISMS_SIGNATURE=DutyAI
UNISMS_TEMPLATE_ID=pub_verif_basic3

# 邮件 - Resend
RESEND_API_KEY=re_xxxx
RESEND_FROM=DutyAI <noreply@yourdomain.com>
```

如未配置，提示用户获取：
- UniSMS: https://unisms.apistd.com/console/access-key
- Resend: https://resend.com/api-keys

## 短信

```bash
uv run python .claude/skills/notify/scripts/send_sms.py \
  --to 13800138000 \
  --content "你好，这是一条测试短信"
```

使用模板：
```bash
uv run python .claude/skills/notify/scripts/send_sms.py \
  --to 13800138000 \
  --template-id pub_verif_basic3 \
  --template-data '{"code": "1234", "ttl": "5"}'
```

群发：
```bash
uv run python .claude/skills/notify/scripts/send_sms.py \
  --to 13800138000 13900139000 \
  --content "会议提醒：今天下午3点开会。"
```

### 短信参数

- `--to` (必填): 手机号，支持多个
- `--content`: 短信正文（与模板二选一）
- `--template-id`: 模板 ID（默认使用环境变量 UNISMS_TEMPLATE_ID）
- `--template-data`: 模板变量，JSON 字符串
- `--signature`: 短信签名（默认使用环境变量 UNISMS_SIGNATURE）

### 短信注意事项

- 发送前必须展示短信内容（收件人、正文）让用户确认
- 短信签名和模板需在 UniSMS 控制台预先审核通过
- 费用约 0.035 元/条
- 国内号码无需加国际前缀，国际号码使用 E.164 格式（如 +12894260331）

## 邮件

```bash
uv run python .claude/skills/notify/scripts/send_email.py \
  --to recipient@example.com \
  --subject "测试邮件" \
  --body "Hello from DutyAI"
```

带附件和 CC：
```bash
uv run python .claude/skills/notify/scripts/send_email.py \
  --to alice@example.com bob@example.com \
  --subject "会议纪要" \
  --html "<h1>会议纪要</h1><p>...</p>" \
  --attachments /path/to/file1.pdf /path/to/file2.docx \
  --cc manager@example.com
```

### 邮件参数

- `--to` (必填): 收件人，支持多个
- `--subject` (必填): 邮件主题
- `--body`: 纯文本正文（与 --html 二选一）
- `--html`: HTML 正文
- `--attachments`: 附件文件路径，支持多个
- `--cc`: 抄送
- `--bcc`: 密送
- `--reply-to`: 回复地址
- `--from`: 覆盖默认发件人

### 邮件注意事项

- 发送前必须展示邮件内容（收件人、主题、正文摘要）让用户确认
- 附件总大小不超过 40MB
- 免费额度：3000 封/月
- **已验证域名**：`memtrix.dev`（Namecheap，到期 2026-04-14）。默认发件人 `RESEND_FROM=DutyAI <noreply@memtrix.dev>`
- **域名未验证错误**：如果报错含 "testing emails" 或 "verify a domain"，说明当前使用的是 Resend 测试域名（`onboarding@resend.dev`），只能发到注册邮箱。需要在 https://resend.com/domains 验证自定义域名后才能给任意邮箱发送
- **API Key 缺失**：如果报错含 "API key"，检查 `.env` 中 `RESEND_API_KEY` 是否配置
