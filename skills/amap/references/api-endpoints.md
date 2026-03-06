# 高德地图 API 端点详细参数

所有接口通过 curl 调用。基础格式：
```bash
curl -s "https://restapi.amap.com/v3/<endpoint>?key=$AMAP_API_KEY&<params>"
```

## 1. maps_geo — 地理编码（地址→坐标）

```bash
curl -s "https://restapi.amap.com/v3/geocode/geo?key=$AMAP_API_KEY&address=北京市朝阳区阜通东大街6号&city=北京"
```

- `address`（必填）：结构化地址
- `city`（可选）：城市名或 citycode

返回 `geocodes[].location`（经度,纬度）。

## 2. maps_regeocode — 逆地理编码（坐标→地址）

```bash
curl -s "https://restapi.amap.com/v3/geocode/regeo?key=$AMAP_API_KEY&location=116.481488,39.990464"
```

- `location`（必填）：经度,纬度

返回 `regeocode.formatted_address`。

## 3. maps_ip_location — IP 定位

```bash
curl -s "https://restapi.amap.com/v3/ip?key=$AMAP_API_KEY&ip=114.247.50.2"
```

- `ip`（必填）：IPv4 地址

## 4. maps_weather — 天气查询

```bash
# 实时天气
curl -s "https://restapi.amap.com/v3/weather/weatherInfo?key=$AMAP_API_KEY&city=110000&extensions=base"
# 预报天气
curl -s "https://restapi.amap.com/v3/weather/weatherInfo?key=$AMAP_API_KEY&city=110000&extensions=all"
```

- `city`（必填）：城市名或 adcode（如北京=110000）
- `extensions`：`base`=实时（默认），`all`=预报

如果用户给的是城市名而不是 adcode，先调 maps_geo 获取 adcode，或直接传城市名试试。

## 5. maps_direction_driving — 驾车路线

```bash
curl -s "https://restapi.amap.com/v3/direction/driving?key=$AMAP_API_KEY&origin=116.481028,39.989643&destination=116.434446,39.90816"
```

- `origin`（必填）：起点经度,纬度
- `destination`（必填）：终点经度,纬度

返回 `route.paths[]`，包含 distance（米）、duration（秒）、steps。

## 6. maps_direction_walking — 步行路线

```bash
curl -s "https://restapi.amap.com/v3/direction/walking?key=$AMAP_API_KEY&origin=116.481028,39.989643&destination=116.434446,39.90816"
```

步行距离限 100km 内。

## 7. maps_direction_bicycling — 骑行路线

```bash
curl -s "https://restapi.amap.com/v4/direction/bicycling?key=$AMAP_API_KEY&origin=116.481028,39.989643&destination=116.434446,39.90816"
```

注意：骑行用 **v4** 接口。距离限 500km 内。响应中 `errcode=0` 表示成功（不是 `status=1`）。

## 8. maps_direction_transit — 公交路线

```bash
curl -s "https://restapi.amap.com/v3/direction/transit/integrated?key=$AMAP_API_KEY&origin=116.481028,39.989643&destination=116.434446,39.90816&city=北京&cityd=北京"
```

- `origin`（必填）：起点坐标
- `destination`（必填）：终点坐标
- `city`（必填）：起点城市
- `cityd`（必填）：终点城市

## 9. maps_distance — 距离测量

```bash
curl -s "https://restapi.amap.com/v3/distance?key=$AMAP_API_KEY&origins=116.481028,39.989643&destination=116.434446,39.90816&type=1"
```

- `origins`（必填）：起点坐标（可多个，用 `|` 分隔）
- `destination`（必填）：终点坐标
- `type`（可选）：0=直线，1=驾车（默认），3=步行

## 10. maps_text_search — 关键字搜索 POI

```bash
curl -s "https://restapi.amap.com/v3/place/text?key=$AMAP_API_KEY&keywords=肯德基&city=北京&citylimit=true"
```

- `keywords`（必填）：搜索关键字
- `city`（可选）：城市限定
- `types`（可选）：POI 类型代码
- `citylimit`（可选）：`true` 限定城市范围

返回 `pois[]`，包含 name、address、location、tel 等。

## 11. maps_around_search — 周边搜索 POI

```bash
curl -s "https://restapi.amap.com/v3/place/around?key=$AMAP_API_KEY&location=116.481488,39.990464&keywords=咖啡&radius=1000"
```

- `location`（必填）：中心点坐标
- `keywords`（可选）：搜索关键字
- `radius`（可选）：搜索半径（米），默认 3000
- `types`（可选）：POI 类型代码

## 12. maps_search_detail — POI 详情

```bash
curl -s "https://restapi.amap.com/v3/place/detail?key=$AMAP_API_KEY&id=B000A7BD6C"
```

- `id`（必填）：POI ID（从搜索结果获取）
