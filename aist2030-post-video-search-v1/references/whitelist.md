# 白名单站点参考（搜视频技能内置）

> 本文件随 `AIST2030-post-video-search-v1` 一起分发，记录两站搜索入口、可达性与直链/下载形态。
> 仅在白名单两域内操作；禁止任何站外/外跳。搜索入口如站点改版，以站点实际站内搜索框行为为准。

## 白名单（硬约束）

| # | 站点 | 域名 | 用途 |
|---|---|---|---|
| 1 | Pixabay 视频（中文站） | `pixabay.com/zh/videos/` | 免费可商用视频（Pixabay License） |
| 2 | Mixkit | `mixkit.co/free-stock-video/` | 免费可商用视频（无水印、无需登录） |

## 各站搜索入口与可达性（实测 2026-07-18）

### 1) Pixabay 视频 ✅ 可达、可出链、可下载（主数据源）
- 站内搜索 URL：`https://pixabay.com/zh/videos/search/<关键词>/`（关键词 UTF-8，可中文）
  - 示例：`https://pixabay.com/zh/videos/search/%E5%92%96%E5%95%A1/`（咖啡）→ 返回数百条
- 结果页静态可见，直链形态直接暴露：
  - `https://cdn.pixabay.com/video/<年>/<月>/<日>/<ID>-<码>_large.mp4`
  - 示例：`https://cdn.pixabay.com/video/2026/07/15/364184_large.mp4`
- 分辨率标注等级：`4K` / `HD` / `SD`（非精确像素）；**不标横屏/竖屏** → 横屏判定须浏览器读真实宽高。
- 下载：CDN 开放（HEAD 200, video/mp4），可直接 `curl/wget` 下载；`_large.mp4` 常为 4K（约 90MB+），优先取满足 ≥720 的较小分辨率以省带宽。
- 免费可商用（Pixabay License）。

### 2) Mixkit ⚠️ 可达，但直链受 referer 保护，须浏览器抓真实下载地址
- 列表/频道：`https://mixkit.co/free-stock-video/`（可达，展示视频流与类目）
- 搜索：站内搜索框（或频道页筛选）；WebFetch 静态页只给视频**详情页** URL（如 `https://mixkit.co/free-stock-video/<slug>-<id>/`），不给 mp4 直链。
- 详情页暴露精确像素：`HD Ready 1080x720` / `Full HD 1920x1080` / `4K 4096x2160`，可据此判横屏与 ≥720。
- **下载地址**：真实 mp4 形如 `https://assets.mixkit.co/videos/preview/mixkit-<slug>-<id>-large.mp4`，但**直接猜 URL 会被 CloudFront 返 403（referer 保护）**；必须用**浏览器自动化**进入详情页、点击下载/捕获带正确 referer 的网络请求拿到可用直链。
- 免费、无水印、无需登录。

## 白名单循环顺序
`1 (Pixabay) → 2 (Mixkit) → 1 (Pixabay) …`

每站访问前 `sleep(random 1–3s)`；某站打不开/受限/无合格视频 → 切下一站；两站皆不行 → 返回 `【执行失败】`。

## 过滤类目（与 SKILL.md 一致）
- 匹配类目：人物、自然风光、植物、动物、交通工具、家居生活、建筑、宇宙航天、体育竞技、食品餐饮、电子数码、节日庆典、学习办公、网络科技。
- 自动屏蔽：宣传广告、带 logo 或水印的视频、抽象艺术、恐怖、畸形、血腥、不适画面、人物大头特写。

## 选取规则
- 优先横屏（**浏览器读真实宽高**，width>height）；无横屏再退竖屏（标注）。
- 匹配度最高的计第1，取**第2个**。
- 分辨率≥720：Pixabay 取 HD/4K 弃 SD；Mixkit 取像素高≥720（优先较小者省带宽）。
- 多场景各取；关键词重复取不同视频。
- 只输出最终视频文件直链/下载地址，不输出页面/详情页 URL。

## 静音下载文件夹策略
- `cache/raw/`：下载的**原素材**（带原始音轨），可后续删除，不作为交付物。
- `cache/muted/`：**静音成品**（ffmpeg 剥离音轨），唯一交付物目录。
- 静音命令：`ffmpeg -i <raw.mp4> -an -c:v copy <cache/muted/xxx.mp4>`（不重编码）。
- 无 ffmpeg / 无下载权 → 回退只出原视频直链，标注"未静音"。
