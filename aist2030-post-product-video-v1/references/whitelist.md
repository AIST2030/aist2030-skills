# 白名单与 API 接法参考（产品视频生成技能内置）

> 本文件随 `AIST2030-post-product-video-v1` 一起分发。仅在下列白名单域内操作；禁止任何站外/外跳。
> 域名或接口如有调整，以百度智能云千帆官方文档与乐享/IMA 连接器实际行为为准。

## 白名单（硬约束）

| # | 用途 | 域名 / 接口 | 说明 |
|---|---|---|---|
| 1 | 出片（视频生成） | `qianfan.baidubce.com` | 百度千帆 `qianfan-video-latest` 视频生成 API |
| 2 | 取知识库（运镜库/产品库） | 乐享 MCP（`lexiang-app.com` 域） | 读「20 种运镜手法」与产品卡/图 |
| 3 | 取知识库（备选） | IMA 连接器 | 当运镜/产品库在 IMA 时读取 |

- **唯一出片域**：`https://qianfan.baidubce.com`（创建 + 查询任务均在此域）。
- **取知识库域**：乐享 `lexiang-app.com` / IMA；仅读，不写。

## 千帆 API 接法

### 鉴权（环境变量，禁止写死）
- 读环境变量 `QIANFAN_API_KEY`（形如 `bce-v3/ALTAK-...`）。
- 所有请求头带 `Authorization: Bearer <QIANFAN_API_KEY>`。
- SKILL.md / 本文件**不存储** key；未设置则提示用户配置后再跑。

### 创建任务（图生视频 img2video）
```
POST https://qianfan.baidubce.com/beta/video/generations/qianfan-video
Authorization: Bearer <QIANFAN_API_KEY>
Content-Type: application/json
{
  "model": "qianfan-video-latest",
  "type": "img2video",
  "model_parameters": {
    "images": ["<主帧图 公网URL 或 data:image/jpeg;base64,....>"],
    "prompt": "<文心生成的中文分镜 prompt，≤2000 字符>",
    "duration": 8,
    "resolution": "1080p",
    "audio": true
  }
}
```
- 无图（纯文本生成）：`type` 改 `text2video`，去掉 `images` 字段。
- `images` **仅 1 张**：公网 URL 或 Base64（解码后 ≤10MB）；输出比例跟随首帧图。
- `duration`：1–16 整数秒（默认 8）；`resolution`：540p/720p/1080p（默认 1080p）；`audio`：默认 true。

### 异步轮询（必须轮询到 success 再交付）
```
GET https://qianfan.baidubce.com/beta/video/generations/qianfan-video?task_id=<id>&model=qianfan-video-latest
Authorization: Bearer <QIANFAN_API_KEY>
```
- 状态流：`created → queueing → processing → success / failed`。
- 成功响应含 `creations[].url`（视频）、`creations[].cover_url`（封面）、`usage`（model/duration/resolution/credits）。
- **轮询策略**：间隔 3–5 秒轮询；设总超时（建议 5 分钟）；超时/失败 → 返回【执行失败】并附原因；**不反复刷新、不超量请求**。
- 关键限制：千帆**无结构化运镜/fps/style 参数**——运镜只能写进 `prompt` 文本（见 `camera_moves.md`）。

## 知识库读取（乐享 MCP）
- 运镜库：entry `4cbb41ea5b5142aabefd476f1ecd8d9a`（乐享 AI 空间，team AIGC）「纯产品特写运镜手法知识库（AI生成专用版）」。
- 产品库：按 `product_name` 全局检索；例「泸州传奇」→ 产品卡 entry `84d2be601c0b44b2aeb8515844d62c68`（空间 `b1db7387ec3b48b2aa7b5592f532587a`）+ 多张产品图（kb_file）。
- 取图用于千帆：优先取公网可访问 URL；若需鉴权/内网 → `file_download_file` 下载本地 → Base64（≤10MB）传入 `images`。

## 失败与兜底
- 乐享/IMA 不可达 → 运镜库用内置 `camera_moves.md` 兜底；产品卡缺失 → 提示用户拖图或给产品名。
- 千帆超时/失败 → 【执行失败】+ 原因；不重试轰炸。
