# 白名单与 API 接法参考（产品 360° 环绕视频技能内置）

> 本文件随 `AIST2030-post-product-360-v1` 一起分发。仅在下列白名单域内操作；禁止任何站外/外跳。

## 白名单（硬约束）

| # | 用途 | 域名 | 说明 |
|---|---|---|---|
| 1 | 出片（keyframe_animation） | `apihub.agnes-ai.com` | Agnes AI 视频生成 API |
| 2 | 取知识库（产品图/卡） | 乐享 MCP（`lexiang-app.com` 域） | 读产品卡与多角度产品图 |
| 3 | 取知识库（备选） | IMA 连接器 | 当产品库在 IMA 时读取 |

## Agnes AI API 接法

### 鉴权（免费 key 内置）
- `Authorization: Bearer sk-***REDACTED***`
- 此 key 为免费 key，可公开使用，无需配置环境变量。

### 创建任务（keyframe_animation）
```
POST https://apihub.agnes-ai.com/v1/videos
Authorization: Bearer sk-***REDACTED***
Content-Type: application/json
{
  "model": "agnes-video-v2.0",
  "prompt": "<合成的中文/英文 prompt>",
  "num_frames": 201,
  "frame_rate": 24,
  "extra_body": {
    "mode": "keyframes",
    "image": [
      "<图1公网URL>",
      "<图2公网URL>",
      "...(2-3张)"
    ]
  }
}
```
- `extra_body.image`：**2–3 张公网可访问图片 URL**
- `num_frames`：必须 `8n+1`（合法值 81/121/161/201/241/281/321/361/401/441）；**默认 201**（≈8秒@24fps）
- `frame_rate`：1–60，**默认 24**
- 分辨率：自动标准化到 480p/720p/1080p

### 异步轮询
```
GET https://apihub.agnes-ai.com/agnesapi?video_id=<VIDEO_ID>
Authorization: Bearer sk-***REDACTED***
```
- 状态流：`processing → completed` / `failed`
- 成功响应含 `metadata.url`（视频 URL）或 `remixed_from_video_id`
- 轮询间隔：3–5 秒；设总超时（建议 5 分钟）

### 速率限制
- **免费用户**：视频生成 **1 RPM**（每分钟最多 1 次 POST）
- 轮询查询不计入 RPM
- 两次 POST 请求必须间隔 ≥ 60 秒

## 知识库读取（乐享 MCP）
- 产品库：按 `product_name` 全局检索；例「泸州传奇」→ 空间 `b1db7387ec3b48b2aa7b5592f532587a` + 多张产品图（kb_file）。
- 取图用于 Agnes：优先取公网可访问 URL；若需鉴权/内网 → `file_download_file` 下载本地 → Base64 或上传到临时公网 URL。

## 内置参考资料（离线兜底）
- `product_categories.md`：30+ 产品分类 → 默认推荐运镜
- `camera_prompts.md`：20 种运镜 → Agnes prompt 模板 + 通用风格后缀
