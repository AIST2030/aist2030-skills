---
id: aist2030-tool-link-image-fetch-v3
name: AIST2030 链接批量取图
displayName: AIST2030 链接批量取图
slug: aist2030-tool-link-image-fetch-v3
module: 工具类
version: 3.0.0
owner: AIST2030
source: 自建
author: 贵州省团之家智付科技有限公司
role: link-image-fetch 执行助手，擅长在 工具类 场景下按标准流程完成任务交付。
context: 用户输入与素材，经本技能流程处理后产出目标结果；已知约束见 constraint 与边界说明。
task: 将用户关于「link-image-fetch」的需求转化为标准化交付物，遵循 quality_gate 与 constraint。
format: 结构化结果 + 必要的过程说明，可直接被下游技能或用户消费。
constraint: 仅处理本技能职责范围内的任务；涉及外部密钥/支付/合规时须显式向用户确认；不越权调用其他系统。
quality_gate: 交付前自检：必填字段完整、产出可用、边界清晰、无越权行为。
anti_dup: 与同类 工具类 技能互斥，按语义匹配唯一触发，避免重复执行。
input_schema: 用户需求描述 / 必要素材（链接、文件、参数）。
output_schema: 标准化交付物 + 状态回显（成功 / 失败原因）。
capability: 提供「link-image-fetch」能力：通过网页分享链接，**批量**提取对话/帖子/文章里的图片，并尽量拿到**原图**：，按既定流程交付结果，适用
  工具类 场景。
description: 输入：通过网页分享链接，**批量**提取对话/帖子/文章里的图片，并尽量拿到**原图**： 相关需求或素材。 输出：按本技能流程产出的结果与可交付物。
  适用边界：仅当用户明确需要「link-image-fetch」能力、且属于 工具类 场景时调用；不属于本技能职责的需求应交由其他技能处理。
tags:
- image
- extractor
- batch
- watermark-free
- doubao
- wechat
- share-link
  - 取图
  - 批量下载
  - 图片抓取
  - 链接取图
pricing:
  model: per_call
  amount_fen: 1
---

# 链接批量取无水印图 Skill（多平台可扩展）

## 功能

通过网页分享链接，**批量**提取对话/帖子/文章里的图片，并尽量拿到**原图**：

- 优先取平台自身提供的"原图(raw)"版本（多数分享内容平台本就开放，无需任何图像处理）；
- 当某链接只有带水印模板、没有 raw 原图时，自动下载带水印版并用 **OpenCV inpainting 兜底抹除角标水印**（需环境装 `opencv-python`）；
- 支持一次传入**多个链接**，批量处理；
- 落盘后缀按**文件头嗅探**（PNG/JPG/GIF/WEBP），不会一律存成 `.png`。

**已支持平台**

| 平台 | 链接形态 | 原图手段 |
|---|---|---|
| 豆包 | `doubao.com/thread/<id>` | 调分享 API，取 `image_raw.png` 模板 |
| 微信公众号文章 | `mp.weixin.qq.com/s?...` | 抓静态 HTML，CDN 宽度上限 `/640` → `/0` |

## 架构（可扩展）

```
scripts/
  fetch.py              # CLI 入口：按链接 host 分发到对应平台适配器，支持多链接
  common.py             # 共享能力：下载/去重/OpenCV 去水印兜底/URL 清洗/后缀嗅探
  platforms/
    __init__.py
    doubao.py           # 豆包适配器（已实现）
    wechat.py           # 微信公众号文章适配器（已实现）
    wenxin.py           # 文心/其他平台（待按同模式补充）
```

**新增一个平台只需**：在 `platforms/` 下新建 `<平台>.py`，实现
`SUPPORTED_HOSTS`（匹配 host 列表）和 `extract(share_url) -> [{'hash','raw_url','wm_url'}]`，
再在 `fetch.py` 的 `PLATFORMS` 字典登记即可。平台原生"取原图"逻辑写在适配器内，
OpenCV 兜底由 `common.py` 统一提供。

**entry 可选字段**：

- `skip_inpaint: True` —— 该平台图片本身无角标水印，跳过 OpenCV 兜底（微信已启用，
  否则 inpainting 只会把边角糊掉）。

## 豆包适配器原理

豆包分享页是 React SPA，图片不内联在初始 HTML。通过逆向前端 JS chunk 确认数据接口：

1. **识别分享ID类型**：URL 路径中的 ID 以 `x` 开头 → `im/message/share/get`；否则 `samantha/thread/share/snapshot/get`
2. **调用 API 获取完整对话 JSON**
3. **递归提取图片 URL**：普通对话走 `file_list[].url_list[]`；图片生成类对话图片嵌套在字符串化 JSON 里，全文正则抓取已签名的 `image_raw.png` 链接
4. **选原图版本**：将模板后缀替换为 `image_raw.png` 即得平台原图
5. **下载/兜底**：带 Referer 防盗链下载；raw 失败回退带水印版并(可选)OpenCV 去水印

### 图片 URL 模板（byteimg）

```
基础: https://p{N}-flow-imagex-sign.byteimg.com/tos-cn-i-a9rns2rl98/rc_gen_image/{hash}.jpeg~tplv-a9rns2rl98-{template}.png?...
template:
- image_raw.png               → 平台原图(优先, 无水印)
- image_dld_watermark_1_5.png → 下载水印版(右下角"豆包AI生成")
- downsize_watermark_1_5.png  → 缩略+水印版
```

## 微信公众号适配器原理

公众号图文页是**服务端直出的静态 HTML**，无需登录态、无需调内部接口，抓 HTML 正则即可：

1. **抓页面**：用 iPhone 微信 UA 请求 `mp.weixin.qq.com/s?...`（公开文章可直接访问）。
2. **限定正文区**：从 `id="js_content"` 截到 `js_pc_qr_code` / `rich_media_area_extra` 等结束标记，
   **避免抓到文末推荐位、评论区、二维码的图**。
3. **抽图**：按文档顺序扫 `data-src` / `data-croporisrc` / `data-backsrc` / `data-original` /
   `data-cover` / `src` 属性 + CSS `background-image:url(...)`，只保留 `mmbiz.qpic.cn`
   （排除 `mmbiz.qlogo.cn` 头像/二维码）。
4. **取原图（关键，已实测）**：

```
正文 URL: https://mmbiz.qpic.cn/sz_mmbiz_jpg/<hash>/640?wx_fmt=jpeg&from=appmsg&tp=wxpic&wxfrom=5&wx_lazy=1&watermark=1#imgIndex=1
                                              └ 宽度上限
转换:  /640 → /0        # 原始分辨率（实测 PNG 1080x864 → 1402x1122）
       只保留 wx_fmt     # 丢掉 watermark / tp / wxfrom / wx_lazy
       去 #imgIndex=N
       ⚠️ sz_ 前缀必须保留！去掉会返回 243 字节的错误占位 PNG
```

5. **两个必踩的坑**：
   - **视频封面**：在 `<iframe class="video_iframe">` 的 `data-cover` 里，是**整体 URL 编码**的
     （`http%3A%2F%2F...`），必须 `unquote` 后才能用 —— 否则报 `unknown url type`。
   - **重复图**：长文常把同一组图**插两次**。下载后用感知哈希（16x16 灰度均值哈希，
     汉明距离 ≤8）排重，重复项移入 `_重复图(可删)` 子目录，不要直接删。

## 使用方法

```bash
# 豆包单链接
python scripts/fetch.py "https://www.doubao.com/thread/x5HR4bO3BP8FqbIdp" ./out

# 微信公众号文章
python scripts/fetch.py "https://mp.weixin.qq.com/s?__biz=...&mid=...&idx=1&sn=..." ./out

# 多链接批量（跨平台混着来也行）
python scripts/fetch.py "https://www.doubao.com/thread/AAA" "https://mp.weixin.qq.com/s?BBB" ./out
```

- 第一个 http(s) 参数起均为链接；最后一个非 http 参数视为输出目录（默认 `fetched_images`）。
- OpenCV 兜底依赖 `opencv-python`：`pip install opencv-python`。正常走 raw 原图时不需要。
- 微信平台 `skip_inpaint=True`，不走 OpenCV，无额外依赖。

## 注意事项

- 图片 URL 含签名(`x-signature`)与过期时间(`x-expires`)，有效期通常数年，建议尽快下载。
- Referer 头必须设为原分享页 URL，否则防盗链 403（`common.py` 已按传入链接自动设置）。
- `image_raw` 为平台对分享内容公开提供的原图版本；仅当拿不到 raw 时才用 OpenCV 兜底。
- OpenCV inpainting 对**角落角标水印**(如右下角平台标识)有效；对平铺/半透明/复杂水印效果有限，属尽力而为。

## ⚠️ 链接类型限制

**豆包**

- `doubao.com/thread/<id>`（分享页）：公开可访问，可直接提取（已验证）。
- `doubao.com/chat/<id>`（个人对话页）：需登录态，无 session 会返回"登录已过期"，**无法直接提取**。请让用户在豆包内对该对话点「分享」生成 `thread` 链接后再提取。**不要索取登录 cookie**。

**微信**

- 仅支持 `mp.weixin.qq.com/s?...` 图文页。**不支持**需要关注后才能看、已删除、违规下架、被"环境异常"拦截的文章。
- 文末推荐位/评论区/二维码的图片会被主动排除（只取 `js_content` 正文区）。
- 文章内的**视频**只能取到封面图，视频本体不在本技能范围内。

## 使用边界声明

本技能仅用于提取**用户本人分享链接中、用户本人生成/上传的图片**，供个人与受控的内部团队留存使用。不得用于去除他人版权内容的水印、不得用于规避平台技术保护措施、不得对外分发本工具或用于商业牟利。图片版权归原作者/平台所有，使用须遵守对应平台服务条款。
