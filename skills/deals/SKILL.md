---
name: deals
description: 生活服务折扣助手。通过聚推客联盟 API 生成 CPS 折扣链接，覆盖餐饮、外卖、酒店、打车、电影票、快递、门票等。当用户提到吃喝玩乐出行住宿相关需求，或提到具体品牌（瑞幸、美团、饿了么、滴滴、飞猪等）时触发。
---

# 生活服务折扣助手

通过聚推客联盟 API 生成折扣链接，用户手机打开即可享受折扣价下单。

API Key 从环境变量 `$JUTUIKE_API_KEY` 读取。如未配置，提示用户到 https://www.jutuike.com 注册并在后台获取 API Key。

## API

- 转链: `GET https://api.jutuike.com/union/act?apikey=$JUTUIKE_API_KEY&sid={timestamp}&act_id={id}`
- 订单查询: `GET https://api.jutuike.com/union/orders?apikey=$JUTUIKE_API_KEY&start_time=...&end_time=...`（时间范围≤1小时）
- 饿了么活动列表: `POST https://api.jutuike.com/ele/getEleCouponList`（参数: apikey=$JUTUIKE_API_KEY）
- 饿了么活动转链: `POST https://api.jutuike.com/ele/kbact`（参数: apikey=$JUTUIKE_API_KEY, sid, activity_id）

## 推荐策略

用户说什么 → 推荐什么（同场景可同时给多个链接）：

- 点咖啡 → 瑞幸(33, 5.5折) / 库迪(136, 5.5折)
- 点外卖 → 美团拼好饭(9, 6.9元起) + 饿了么红包(69) + 京东外卖(97, 满8减7)
- 点餐/团购 → 美团吃喝玩乐(27, 3折起) / 聚合点餐(57)
- 订酒店 → 飞猪天天特惠(146) + 美团酒店(65)
- 打车 → 滴滴(42) + 花小猪(49)
- 看电影 → 电影票(76, 佣金10-50%)
- 寄快递 → 特价快递(122, 4折起)
- 门票/景点 → 景点门票(105) / 演唱会(153)
- 租车 → 飞猪租车(145)
- 指定品牌 → 查 activities.md 匹配 act_id

完整活动列表见 `references/activities.md`。

## 流程

1. **识别需求** — 从用户消息提取场景/品牌，匹配 act_id
2. **调用 API** — `curl -s "https://api.jutuike.com/union/act?apikey=$JUTUIKE_API_KEY&sid=$(date +%s)&act_id=${ACT_ID}"`，提取 `data.h5`
3. **返回链接** — 简洁格式，只给品牌名+折扣+H5短链，不输出小程序信息

输出格式（飞书移动端友好）：

```
{品牌} {折扣}
链接：{h5_url}
```

多个链接逐行列出。末尾加一句"打开链接选择门店/商品，直接下单"。

## 注意

- CPS 推广模式，链接含推广标识，用户下单享折扣+产生佣金
- 链接有时效性，过期需重新生成
- 同场景多个活动时，优先推荐折扣力度大的
