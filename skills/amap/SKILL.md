---
name: amap
description: 高德地图地理位置服务。当用户涉及以下场景时触发：(1) 地址/坐标查询（"这个地址在哪"、"经纬度转地址"）(2) 天气查询（"北京天气"）(3) 路线规划（"从A到B怎么走"、骑行/步行/驾车/公交）(4) 搜索地点/POI（"附近的咖啡店"、"找一下XX餐厅"）(5) 距离测量（"两地距离"）(6) IP 定位。
---

# 高德地图地理位置服务

基于高德 Web 服务 API，提供地理编码、天气、路线规划、POI 搜索等能力。

API Key 从环境变量 `$AMAP_API_KEY` 读取。如未配置，提示用户到 https://console.amap.com/dev/key/app 创建。

## 路由

所有 API 端点的详细参数和调用示例 → 读取 `references/api-endpoints.md`

包含 12 个工具：maps_geo, maps_regeocode, maps_ip_location, maps_weather, maps_direction_driving/walking/bicycling/transit, maps_distance, maps_text_search, maps_around_search, maps_search_detail

## 常见组合用法

### 地址→路线规划
1. 先用 maps_geo 将地址转坐标
2. 再用对应路线接口规划

### "附近的XX"
1. 如果用户没给坐标，先用 maps_geo 获取参考地点坐标
2. 再用 maps_around_search 搜索

### 旅游攻略
1. maps_text_search 搜索景点
2. maps_weather 查天气
3. maps_direction_driving/transit 规划路线
4. maps_distance 测距

## 输出格式

结果用自然语言精简呈现（飞书移动端友好）：
- 地址查询：直接给出地址和坐标
- 天气：温度、天气、风力，预报按天列出
- 路线：总距离(km)、总时长(分钟)、关键路段
- POI 搜索：名称、地址、电话，最多 5-8 个
- 距离：直接给出 km 和预计时长

距离自动转换：米→公里（保留1位小数），秒→分钟/小时。

## 注意

- 坐标格式统一为"经度,纬度"（高德标准，不是纬度在前）
- 高德使用 GCJ-02 坐标系，与 GPS/WGS-84 有偏移
- 骑行用 **v4** 接口（其他用 v3），`errcode=0` 表示成功
- 频率限制：个人开发者日配额有限，避免不必要的重复调用
