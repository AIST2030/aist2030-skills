---
id: aist2030-chatcut-lite-v1
name: AIST2030 ChatCut-Lite 本地 AI 视频剪辑
displayName: AIST2030 ChatCut-Lite 本地 AI 视频剪辑（零积分）
slug: aist2030-chatcut-lite-v1
module: 开发类
version: 1.2.0
internal_version: v1.2
owner: AIST2030
author: 贵州省团之家智付科技有限公司
source: 自建
pricing:
  model: free
  amount_fen: 0
capability: 本地跑完一条视频的完整后期链路：faster-whisper 词级转写与中文口语清理（口头禅剔除 + 长停顿压缩 + 语义保护）、ASS 智能字幕（5 套样式）、ffmpeg 多轨合成与 10 种 xfade 转场、8 种可改文字配色的 MG 动画图层、edge-tts 免费 TTS 旁白、7 种程序化 BGM、6 种程序化音效、人声侧链压低背景乐。全链路零积分、零 API 费用、素材不出本机。
description: 输入：一个或多个本地素材（视频 / 音频 / 图片）+ 大白话需求（可选）。 输出：① 成片 MP4（分辨率/时长/体积回显）；② 语音清理报告（原始时长、保留时长、压缩秒数、删除的口头禅逐条列出）；③ ASS 字幕文件；④ 引擎 JSON 工程（可再次微调重渲）；⑤ MG 透明 PNG 序列。 适用边界：只处理本地已有素材，AI 生成视频/图片不在本技能范围（需外部模型额度）；默认输出 1920×1080@30fps，竖版需显式传 --width1080 --height 1920；首次运行 whisper 模型需联网下载（已配置 hf-mirror 镜像），之后完全离线。
role: 本地视频后期流水线，擅长把口播录音或素材直接做成带字幕、配乐、MG 动画的成片，以语义保护的口语清理提升内容紧凑度，以侧链压缩保证人声清晰度，所有计算在本地完成、不消耗任何 AI 积分。
context: '输入物：本地视频/音频/图片路径 + 自然语言需求。

  背景：ChatCut 等云端AI 剪辑器按积分计费，Seedance 等模型单独收费，成本不可控；本技能用本机 ffmpeg + faster-whisper + edge-tts 复刻其80% 核心能力，零边际成本。

  已知约束：
  - 引擎本体在 E:\视频创作\AIST2030\ChatCut-Lite\，依赖装在该目录的 .venv 内；脚本会自动切换解释器，无需手工激活。
  - 必须使用完整版 ffmpeg（vendor/node_modules/ffmpeg-static）。本机F 盘 yovoice-cli 自带的 ffmpeg 是--disable-everything 极简版，无 libx264/xfade/subtitles，不能用于剪辑。
  - 中文口头禅表含「呃/啊/嗯/那个/就是说/然后/对吧」等；已实现语义保护：「这个+方法/问题」类搭配不会被误删，「对吧/是吧」只在句尾删除。
  - whisper 中文可能输出繁体，已接 opencc t2s 转简体。
  - MG 动画叠加必须用 overlay 的 eof_action=repeat，否则图层在序列结束后消失。
  - mux 阶段禁用 -shortest：sidechaincompress 会让音频略短于画面，会把成片截短。
  - 纯音频输入时自动生成纯色画面底，且视频片段统一取 src_in=0，避免裁剪越界导致时长错乱。
  - 所有中间产物强制落workspace/cache（已配TMP/TEMP/TMPDIR），不占用 C 盘。
  - HuggingFace 走 hf-mirror 镜像 + HF_HUB_DISABLE_XET=1；本机代理 127.0.0.1:50841 会导致 502，需 disable_proxy()。'
task: '1. 环境自检：运行 `ccl.py doctor`，确认「完整版 ffmpeg ✓」「faster-whisper ✓」「Pillow ✓」「edge-tts ✓」。任一项缺失先修复再继续，不要带着残缺环境往下做。

  2. 需求归类：把用户的大白话翻译成下列组合（可多选）。语音清理→--clean；字幕→--subtitle --subtitle-style；配乐→--music <风格>；旁白→先跑tts 再作为素材；MG→跑 mg 取 PNG 序列并在 render 时带上 renderers；转场→在工程 meta.transitions 里按片段下标指定。

  3.【若用户未指定】用默认值直接执行，不要反复追问：字幕样式 default、配乐 lofi、输出 1920×1080@30fps、口头禅清理开启、停顿压缩阈值 0.45s。若用户明确说了"要竖版/抖音风格"等，才覆盖默认值。

  4. 一键成片（最常用）：`ccl.py auto <素材> --clean --subtitle --subtitle-style <样式> --music <风格> -o <输出目录>`。纯音频素材会自动配纯色底。

  5. 精细分步（用户要调整时）：
     - 语音清理 + 字幕：`ccl.py clean <素材> --style <样式> -o <目录>`，读产出的 *_clean.json 拿到 keeps/cues/removed。
     - 旁白：`ccl.py tts "<文案>" --voice 晓晓 -o <目录>`
     - 配乐：`ccl.py music <秒数> --style lofi -o <目录>`
     - 音效：`ccl.py sfx whoosh -o <目录>`
     - MG：`ccl.py mg --style bar_chart --text "标题|甲:120,乙:340" --color "#1f4fd8" -o <目录>`
     - 渲染：`ccl.py render <project.json> -o <目录>`

  6. 交付回执：必须向用户汇报成片路径、分辨率、时长、体积，以及语音清理的具体收益（省了多少秒、删了哪些口头禅逐条列出）。MG 与配乐若已启用也要说明。

  7. 自审：抽帧（ffmpeg -ss <t> -frames:v 1）确认字幕无遮挡、MG 未超出安全区、人声清晰盖过BGM；竖版另检上下 200px 安全区。'
---

# ChatCut-Lite 本地 AI 视频剪辑

>零积分、零 API 费用、素材不出本机的视频后期流水线。

## 快速开始

```bash
# 1. 环境自检
python scripts/ccl.py doctor

# 2. 一键成片（最常用）
python scripts/ccl.py auto input.mp3 --clean --subtitle --subtitle-style tiktok --music lofi -o out/

# 3. 只做语音清理
python scripts/ccl.py clean input.mp4 --style tiktok -o out/
```

## 能力对照

| 能力 | 参数 | 说明 |
|---|---|---|
| 语音清理 | `--clean` | 转写 + 去口头禅 + 压停顿，带语义保护 |
| 字幕 | `--subtitle --subtitle-style <样式>` | 5 套样式：default / bold_white / tiktok / bottom_clean / top |
| 配乐 | `--music <风格>` | lofi / ambient / electronic / cinematic / jazz / ambient_pad / upbeat |
| 旁白 | `tts "<文案>" --voice <音色>` | 7 个中文音色，零成本 |
| 音效 | `sfx <类型>` | click / whoosh / pop / riser / ding / thud |
| MG 动画 | `mg --style <模板> --text "<内容>"` | 8 种模板，文字配色可改 |
| 转场 | 工程 `meta.transitions` | 10 种 xfade |
| 竖版 | `--width 1080 --height 1920` | 字幕字号自动缩小 |

## MG 动画模板

| 模板 | text 格式 | 用途 |
|---|---|---|
| `title` | 纯文本 | 居中标题卡 |
| `lower_third` | `姓名\|头衔` | 下三分之一人名牌 |
| `bar_chart` | `标题\|甲:120,乙:340` | 柱状图递进升起 |
| `pie_chart` | `标题\|甲:45,乙:35` | 饼图 + 图例 |
| `chapter` | `02\|标题` | 章节页码 |
| `typewriter` | 纯文本 | 打字机 + 光标 |
| `underline` | 纯文本 | 重点强调下划线 |
| `progress` | `AI 渲染中\|92` | 加载进度条 |

## 引擎本体

`E:\视频创作\AIST2030\ChatCut-Lite\`

- `启动.bat` — 双击启动本地 Web 编辑器（手动精修用）
- `engine/` — 引擎源码（timeline / ffmpeg_engine / asr / mg / assets）
- `workspace/` — uploads / projects / cache / exports，全部落E 盘
- `vendor/` — 完整版 ffmpeg + ffprobe

## 调度模式（WorkBuddy 驱动 Web 服务）

服务跑着的时候（默认 `127.0.0.1:8770`），用 `scripts/ccl_remote.py` 远程调度，
**一次调用 = 自动剪辑全流程**，比逐条跑本地子命令更省事：

```bash
PY=/c/Users/Administrator/.workbuddy/binaries/python/versions/3.13.12/python.exe
S=/c/Users/Administrator/.workbuddy/skills/aist2030-chatcut-lite-v1/scripts/ccl_remote.py

# 探活（服务没起就先跑 ChatCut-Lite/启动.bat）
$PY $S ping

# 一句话出片：素材 + 清理 + 字幕 + BGM，同步等到成片
$PY $S auto --input "E:\素材\口播.mp3" --clean --subtitle tiktok --music lofi

# 纯文案出片（TTS 旁白 + 纯色底 + 字幕）
$PY $S auto --tts "大家好，今天讲三件事" --voice 云希 --subtitle bold_box

# 加 MG 图层 / 竖版 / 指定输出名
$PY $S auto --input 视频.mp4 --clean --subtitle tiktok \
  --mg bar_chart:渠道构成:线上120,线下80:#4ade80 \
  --width 1080 --height 1920 --out 我的成片.mp4

# 异步渲染（长片用）：立即返回 job id，再查进度
$PY $S auto --input 大视频.mp4 --clean --async
$PY $S status <job_id>
```

行为要点：
- `--input` 可多次：第一个是主素材，其余顺序接到片尾；**纯音频自动配纯色画面底**
- `--clean` 走 ASR（模型已缓存在 E 盘，首次约 10s），删口头禅带语义保护
- 默认**同步等待**渲染完成（最长 300s），返回里直接给 `path` 成片绝对路径
- 也可以直接 POST `http://127.0.0.1:8770/api/agent/auto`（JSON 同名参数），端点在 `server.py`
- 手动精修：打开 `http://127.0.0.1:8770`，项目在 Web 里可见可改

决策规则：用户说"剪这个/出个片"→ 先 `ping`，活着就 `auto`；死了就提示跑 `启动.bat`。
渲染完把 `path` 的成片交给用户（present_files），并转述 log 里的清理数据（删了几个口头禅、省了多少秒）。
同时把返回里的 `ui` 地址（http://127.0.0.1:8770/?pid=xxx）发给用户——浏览器打开即见该项目时间线，Web 界面每 4 秒自动同步外部变更。

## 资源融合（本地库 + 全网素材）

| 端点/用法 | 作用 |
|---|---|
| `GET /api/library` | 本地素材库（E:\视频创作\AIST2030 顶层媒体文件） |
| `POST /api/agent/asset_search` | `{"query":"city night","kind":"video"}` → Mixkit 1080p 直链；`kind:"image"` → cc0.cn 原图直链 |
| `POST /api/agent/asset_fetch` | `{"pid","url"或"path","add":true}` → 下载/复制进项目并接上时间线 |
| `auto` 的 `broll` 参数 | `{"query":"mountain aerial","count":2}` → 自动搜 Mixkit、下 720p、接在片尾当 B-roll |
| `auto` 的 `assets` 参数 | 本地路径或 http 直链数组，顺序接在主素材后 |

**踩坑（2026-10-18 实测）**：
- cc0.cn 已改版：必须**带 Cookie 会话** POST（`HTTPCookieProcessor`），302 直接落到新结果页 `/e/search/result/?searchid=<id>`；图片标签是普通 `src="//img.cc0.cn/..."`，不再有 `data-original`
- cc0 图床防盗链：`Referer` 必须是 `https://cc0.cn/`（站点根），用图片自身地址当 Referer 会 403
- Mixkit 搜索页 HTML 直接含 mp4 直链，`-360` 换 `-720`/`-1080` 即对应清晰度；补镜头用 720p（1080p 一条约 180MB）
- 关键词：视频用英文命中率高，图片用中文


详细排错见 `references/troubleshooting.md`。

---

## 导演配方系统（v1.1 新增：七大场景一键出片）

在原口播后期链路之上，新增「导演配方」层：`engine/directors/` 下 7 个场景配方，把纯数据 params 变成带综艺感动效的成片（大字闪现/圆章砸落/白闪爆点 + 程序化 BGM/EPIC 能量轨/音效），全程走同一条 ffmpeg 管线，零积分、素材不出本机。

| 场景 | scenario | 结构 |
|---|---|---|
| 活动/演出/电影预告 | event | 钩子→奇观卡→信任盖章卡→CTA→金句（EPIC 接管） |
| 本地生活·探店 | local | 3秒反差钩子→卖点→菜品特写+情绪大字→价格锚点盖章→CTA |
| 产品/商品 | product | hero→特性卡→价格盖章→号召 |
| 课程/知识付费 | course | 痛点→大纲亮点→背书→报名 CTA |
| 招聘/雇主品牌 | recruit | 氛围→岗位福利→投递 CTA |
| 节日/大促 | festival | 氛围开场→机制→爆款价→号召 |
| 综合路由 | comprehensive | 关键词推断场景后分发 |

**调用方式（二选一，行为一致）**：
- CLI：`"$ENG/.venv/Scripts/python.exe" "$ENG/engine/cli.py" compose <scenario> <params.json> -o <输出目录>`，返回 `{"video": "...", "cover": "..."}`
- MCP：若已接入 chatcut-lite MCP，调用工具 `chatcut_compose(scenario, params_json, out_dir)`

**注意**：
- params.json 中的文字三元组用 JSON 数组写法 `["文本", 字号, [r,g,b,a]]`（seal 章内行用 `["文本", 字号]`）
- 竖版探店默认 1080×1920；event 默认 1920×1080
- 对应单场景 skill：aist2030-vmix-event/local/product/course/recruit/festival/pro；MCP 接入细节见 aist2030-chatcut-mcp-v1

**踩坑（v1.1 已修复，勿回退）**：
- `_composite_fx` 拼滤镜图时每个输入前**必须有 `-i`**，漏掉会报误导性的 "Invalid file index 0"（根因排查了半天：与 bash/python/杀毒无关，就是少了 -i）
- ffmpeg 长渲染禁止 capture_output（64KB 管道死锁被系统杀），统一走 `engine/ffproc.py::run_ff`（日志文件 + bash 脚本派发 + 输入可读预检 + 退避重试）


---

## 配音（TTS）与音乐音效规范（v1.1.1 精要）

- **配音**：params.tts = `[{"text","start","voice","rate","volume"}]`；voice 直接写中文名（云希/云健/云扬/晓晓/晓伊/云希Pro/云枫），rate 如 "+10%"；start = 卡片完全可见时刻（前面各段 dur 累加 − 转场重叠累计，宁早 0.2s）。
- **文案三原则**：每句 ≤12 字只说一个信息点 / 口语化说人话 / 钩子用反差·悬念·数字。全片旁白 ≤4 句，旁白是佐料。
- **音乐**：BGM 风格 lofi/ambient/electronic/cinematic/jazz/ambient_pad/upbeat，音量 0.2~0.35；EPIC 能量轨 0.85 只给重节奏段。
- **音效节拍**：印章=thud(+0.05s)、情绪大字=pop(+0.02s)、转场=whoosh/click、蓄力=riser(提前1s)、CTA=ding；同一秒最多 1 个重音效。
- 各场景的音色/语速/BGM 定制表见对应 vmix-* skill（v1.1.0 起内置「配音与音乐音效规范」章节）。


---

## 音乐资源库（v1.2 新增：真实曲库替代程序化合成，质量可控）

**曲库来源**：breakingcopyright.com（1400+ 首免费可商用、无需注册、直链 MP3、首页即热门榜）。引擎已内置 `engine/musiclib.py`：自动抓曲库（7 天缓存）→ 按情绪标签选热门曲 → 下载到本地缓存 → 裁剪成片时长 + 0.4s 淡入 + 2s 淡出。

**用法（三选一）**：
- 默认：导演已按场景自动选曲（探店/节日=happy+energetic、产品=electronic-dance、活动=epic+cinematic、课程=inspirational+calm、招聘=chill+acoustic），params 不用写；
- 指定情绪：`"bgm": {"mood": ["happy", "chill"], "volume": 0.3}`（mood 数组=B曲库标签，可混多个）；
- 本地文件：`"bgm": {"src": "D:/music/xxx.mp3", "volume": 0.3}`。

**程序化合成**（lofi/ambient/electronic/cinematic/jazz/ambient_pad/upbeat）仅作曲库不可达时的自动兜底。

**授权合规**：曲库为 CC 授权，个别作者要求署名——发布时视频简介加一行 `Music: <曲名> (breakingcopyright.com)`（引擎 musiclib.credit_text 可生成）。音效（thud/pop/whoosh/riser/ding/click）保持程序化生成（短促打击类质量可控、零授权风险）。

**参考站点盘点**（手动找素材时用）：breakingcopyright.com（首选，直链）/ Mixkit free-stock-music / freePD（CC0）/ Bensound（需署名）/ DOVA-SYNDROME（CC0，日系）；音效站：freesfx、freePD、耳聆网。Pixabay/Pexels 本机 403 不可用。
