# 多维表格操作详细用法

所有脚本位于 `.claude/skills/feishu-bitable/scripts/`，使用共享鉴权模块 `feishu_auth.py`。

## 字段类型编号

- 1 = 文本 (Text)
- 2 = 数字 (Number)
- 3 = 单选 (Single Select)
- 4 = 多选 (Multi Select)
- 5 = 日期 (DateTime)
- 7 = 复选框 (Checkbox)
- 11 = 人员 (Person)
- 13 = 电话 (Phone)
- 15 = 超链接 (URL)
- 17 = 附件 (Attachment)
- 18 = 单向关联 (Single Link)
- 21 = 双向关联 (Duplex Link)
- 22 = 地理位置 (Location)
- 1001 = 创建时间 (Created Time)
- 1002 = 修改时间 (Modified Time)
- 1003 = 创建人 (Created User)
- 1004 = 修改人 (Modified User)
- 1005 = 自动编号 (Auto Number)

## 创建新多维表格

```bash
uv run python .claude/skills/feishu-bitable/scripts/bitable_tables.py \
  --action create-app --name "表格名称" [--folder <folder_token>]
```

返回 `app_token`、`default_table_id`、`url`。

## 数据表管理

列出所有表：
```bash
uv run python .claude/skills/feishu-bitable/scripts/bitable_tables.py \
  --app <app_token> --action list [--brief]
```

创建新表：
```bash
uv run python .claude/skills/feishu-bitable/scripts/bitable_tables.py \
  --app <app_token> --action create \
  --name "表名" \
  --fields '[{"field_name":"名称","type":1},{"field_name":"数量","type":2}]'
```

⚠️ **主字段类型限制**：任何新建表（含 create-app 默认表）的第一个字段（primary field）会被强制为 Text (type 1)，即使指定了其他类型。需要日期做主字段时，改用文本字段写入 `"2026-02-17"` 格式字符串。

## 字段管理

列出所有字段：
```bash
uv run python .claude/skills/feishu-bitable/scripts/bitable_fields.py \
  --app <app_token> --table <table_id> --action list [--brief]
```

添加字段：
```bash
uv run python .claude/skills/feishu-bitable/scripts/bitable_fields.py \
  --app <app_token> --table <table_id> --action create \
  --name "字段名" --type 1
```

添加单选字段（带选项）：
```bash
uv run python .claude/skills/feishu-bitable/scripts/bitable_fields.py \
  --app <app_token> --table <table_id> --action create \
  --name "状态" --type 3 \
  --options '["待处理","进行中","已完成"]'
```

添加双向关联字段（Duplex Link）：
```bash
uv run python .claude/skills/feishu-bitable/scripts/bitable_fields.py \
  --app <app_token> --table <src_table_id> --action create \
  --name "关联公司" --type 21 \
  --property '{"table_id":"<dst_table_id>","back_field_name":"关联记录"}'
```

`--property` 用于 link 等需要额外配置的字段类型。对于 type 21（双向关联），property 需要 `table_id`（目标表）和 `back_field_name`（反向字段名）。

⚠️ **双向关联字段读写格式不同**：
- **写入**（create/update record）：传字符串数组 `["recXXX", "recYYY"]`
- **读取**（search record 返回值）：返回对象 `{"link_record_ids": ["recXXX", "recYYY"]}`
- 读取结果不能直接用于写入，需提取 `link_record_ids` 值。参考 `crm_ops.py` 的 `_extract_link_ids()` helper。

删除字段：
```bash
uv run python .claude/skills/feishu-bitable/scripts/bitable_fields.py \
  --app <app_token> --table <table_id> --action delete --field-id <field_id>
```

## 记录操作

搜索/列出记录：
```bash
uv run python .claude/skills/feishu-bitable/scripts/bitable_records.py \
  --app <app_token> --table <table_id> --action search [--brief] \
  [--select-fields "名称,状态,数量"]
```

带筛选条件搜索：
```bash
uv run python .claude/skills/feishu-bitable/scripts/bitable_records.py \
  --app <app_token> --table <table_id> --action search \
  --filter '{"conjunction":"and","conditions":[{"field_name":"状态","operator":"is","value":["已完成"]}]}'
```

创建单条记录：
```bash
uv run python .claude/skills/feishu-bitable/scripts/bitable_records.py \
  --app <app_token> --table <table_id> --action create \
  --fields '{"名称":"测试项","数量":42,"状态":"待处理"}'
```

批量创建记录：
```bash
uv run python .claude/skills/feishu-bitable/scripts/bitable_records.py \
  --app <app_token> --table <table_id> --action batch_create \
  --records '[{"fields":{"名称":"项目A","数量":10}},{"fields":{"名称":"项目B","数量":20}}]'
```

更新记录：
```bash
uv run python .claude/skills/feishu-bitable/scripts/bitable_records.py \
  --app <app_token> --table <table_id> --action update \
  --record-id <record_id> --fields '{"状态":"已完成"}'
```

批量更新记录：
```bash
uv run python .claude/skills/feishu-bitable/scripts/bitable_records.py \
  --app <app_token> --table <table_id> --action batch_update \
  --records '[{"record_id":"recXXX","fields":{"状态":"已完成"}}]'
```

删除记录：
```bash
uv run python .claude/skills/feishu-bitable/scripts/bitable_records.py \
  --app <app_token> --table <table_id> --action delete --record-id <record_id>
```

批量删除：
```bash
uv run python .claude/skills/feishu-bitable/scripts/bitable_records.py \
  --app <app_token> --table <table_id> --action batch_delete \
  --record-ids '["recXXX","recYYY"]'
```

## 分享多维表格

复用 feishu-doc 的 `doc_share.py`：

```bash
uv run python .claude/skills/feishu-doc/scripts/doc_share.py \
  --id <app_token> --type tenant_read --doc-type bitable
```

权限层级：`off` → `tenant_read` → `tenant_edit` → `anyone_read` → `anyone_edit`

创建后必须先授权：
```bash
uv run python .claude/skills/feishu-doc/scripts/doc_share.py \
  --id <app_token> --type owner --doc-type bitable
```

## 参数速查

- `--app`: 多维表格 app_token（必填）
- `--table`: 数据表 table_id（除 table list/create 外必填）
- `--action`: 操作类型（list/create/update/delete/search/batch_create/batch_update/batch_delete）
- `--name`: 表名或字段名
- `--type`: 字段类型编号
- `--fields`: 记录字段值，JSON 格式
- `--records`: 批量操作时的记录数组，JSON 格式
- `--record-id`: 单条记录 ID
- `--record-ids`: 批量删除时的记录 ID 数组
- `--field-id`: 字段 ID
- `--filter`: 搜索筛选条件，JSON 格式
- `--options`: 单选/多选字段的选项列表，JSON 格式
- `--page-size`: 分页大小（默认 20，最大 500）
- `--page-token`: 分页 token
- `--brief`: 精简搜索输出，节省 context
- `--select-fields`: 逗号分隔的字段名，配合 `--brief` 只返回指定列
