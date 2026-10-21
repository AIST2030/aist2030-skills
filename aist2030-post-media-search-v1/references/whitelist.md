# AIST2030-post-media-search-v1 · 白名单与密钥说明

> 本文件为技能运行时参考，**不存储任何 API key**。

## 1. 运行时白名单（可访问域）
- **`https://api.pexels.com`**（API 始终）
  - 图片检索：`GET /v1/search`
  - 视频检索：`GET /v1/videos/search`
- **`https://videos.pexels.com`**（**仅 `mute=true` 下载视频时**访问，用于下载视频并 ffmpeg 静音）
- 用户提供的 `https://www.pexels.com/zh-cn/api/key/` 仅是"获取 API key 的网页"，**运行时绝不访问**。
- 图片 CDN 直链（`images.pexels.com` 等）**始终只作输出文本，不访问不下载**。
- 视频 CDN 直链 `videos.pexels.com` **默认只作输出文本**；仅当 `mute=true` 时下载并静音，符合"禁止外链"硬约束（下载是受控的 mute 分支行为，非站外跳转）。

## 1.5 静音分支（mute=true）运行依赖与缓存目录
- **依赖**：`ffmpeg` + `ffprobe`（静音与读真实宽高/音轨用）。未安装则 mute 分支不可用，自动回退只回原视频直链并标注「未静音」。
- **缓存目录**（相对运行根目录，建议 `cache/`）：
  - `cache/raw/`：下载的**原素材**（带原始音轨），仅供中间处理，**不作为交付物**。
  - `cache/muted/`：**静音成品**（ffmpeg 剥离音轨，`ffmpeg -i raw.mp4 -an -c:v copy muted.mp4`），**唯一交付目录**。
- **静音命令**（不重编码，秒级）：`ffmpeg -i <raw.mp4> -an -c:v copy <cache/muted/xxx.mp4>`
- **回退**：无 ffmpeg / 无下载权 → 回退只回原视频直链并标注「未静音」，不中断流程。

## 2. API Key 配置（环境变量，禁止写死）
- 技能运行时从环境变量 **`PEXELS_API_KEY`** 读取 key。
- 未设置时，技能会提示用户先配置，再执行；**SKILL.md 正文与本项目不保存 key 明文**。
- 配置方式（任选其一）：
  - 临时（当前终端）：`export PEXELS_API_KEY="你的key"`
  - 持久（用户 shell 配置，如 `~/.bashrc` / `~/.zshrc`）：追加 `export PEXELS_API_KEY="你的key"`
  - 容器/工作流环境变量：在运行环境里注入 `PEXELS_API_KEY`
- 在 Pexels 官网 `https://www.pexels.com/zh-cn/api/key/` 登录后「Your API Key」处获取。

## 3. 请求头必带字段
- `Authorization: <PEXELS_API_KEY>`
- `User-Agent: <自定义标识>`（如 `AIST2030-media-search`）
> 实测：缺 `User-Agent` 会被 Pexels 安全服务拦截返回 **403 / 错误码 1010**，必须带。

## 4. 常用参数
| 参数 | 图片 API | 视频 API | 说明 |
|---|---|---|---|
| `query` | ✅ | ✅ | 关键词（中文优先，无果换英文） |
| `per_page` | ✅ | ✅ | 单页条数，默认 15（≤80） |
| `orientation` | ✅ | ✅ | `landscape`/`portrait`/`square`，默认横版 |
| `image_type` | ✅（photo） | — | 图片固定 `photo`，硬排插画/海报/3D/矢量 |
| `locale` | ✅(zh-CN) | — | 图片结果语种，默认 zh-CN |
| `size` | — | ✅ | 视频可选 `small`/`medium`/`large` |

## 5. 免费额度
- Pexels 免费 API：**200 次请求 / 小时**。技能已做"单call拉足 + 请求间轻量延时 0.5–1s"节流，勿高频循环重试。
