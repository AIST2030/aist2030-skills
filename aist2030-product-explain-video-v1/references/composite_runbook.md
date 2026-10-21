# 合成 Runbook（v2 · AI 运镜底片 + 文字动效层）

> 本文件指导把「口播 + AI 运镜底片 + 文字动效层 + BGM」合成成片。
> v2 两处关键变化（与 v1 不同）：
> ① 视觉素材是 **AI 运镜片段（mp4）**，不是静态图做 Ken Burns；
> ② **不烧字幕**，文字以「带透明通道的文字动效层 mov（qtrle RGBA）」叠加，关键字/金句做成动效展示。

## 0. 准备
```
PL="<adu-motion-video>/scripts/pipeline.sh"
bash "$PL" doctor   # 检查 Node/Python/FFmpeg/Chrome
```
缺依赖且允许 → `bash "$PL" setup`。先读 adu-motion-video 的 references/rules.md 与 start-creating.md。

## 1. 素材组织
为本产品新建工程目录（任务文件夹内）：
```
产品讲解视频v1/
  work/<产品名>/
    voice/        # 口播 MP3 + 口播时间轴.json（含 keyword/quote 标记，无 SRT）
    shots/        # product-360 / product-video / image-awake / 本地兜底 输出的 AI 运镜 mp4
    text_layer/   # 文字动效层 mov（qtrle RGBA 透明通道，adu 风格原子动作）
    cards/        # HyperFrames 远景场景合成 mp4（若有）
    bgm/          # media-search 取到的 BGM
```
保持源工程只读，输出到新路径。

## 2. 写 brief.json（对齐 adu 的 adaptive-composition）
- `narrationDuration` = 口播实际时长（target 输出时钟）
- `stages` = 阶段（对应 length_presets 分段），每段含 短标题 + **AI 运镜 mp4 路径** + 对应口播段落点
- `music` = `{mode:"track",path:"<bgm>",offset:0}` 显式绑定本期 BGM
- `brand` = 本期账号/品牌
- `faceTracking` = 未用数字人时默认 fixed 或留空（无人物则不需要）
- **不传 SRT**；文字动效由 text_layer 叠加，不在 brief 里绑字幕。

## 3. 规划与构建（adu 主路径）
```
bash "$PL" macro-plan 包ID@版本 brief.json 新规划目录
# 查看 report.md，缺项回 brief 补齐
bash "$PL" macro-build 包ID@版本 新规划目录/spec.json 剪好口播.mp4 新工程
bash "$PL" stills 新工程 0,4,12,...   # 抽帧核对
bash "$PL" audio 新工程 && bash "$PL" mix 新工程 && bash "$PL" render 新工程 新片_v1.mp4
bash "$PL" check 新片_v1.mp4
```
> adu 工程本身不含文字动效层时，可在 `render` 后用 ffmpeg 把 `text_layer/*.mp4`
> 以 `overlay`/`blend` 叠加到成片对应时间轴（见 §8 叠加配方）。
> 若从零即走自研 ffmpeg 产线（无剪好口播视频），直接用 §8。

## 4. 模板与画幅选择
- 竖屏：`brief.layout="portrait"` → 按 portraitSelection 选候选包（anim4-showcase-macro 等支持竖屏）
- 横屏：默认 landscape，选展示类包（03-A 多屏展陈 / classic-performance）
- 方形：横屏成片后用 FFmpeg 居中裁切 1080×1080

## 5. 自检
- stills 抽查每个 cue 前中后、最长文字、场景接缝、片尾
- **文字动效层**：抽帧确认 keyword/quote 在口播对应时刻出现/退场，不与产品主体重叠遮挡
- check 的帧数/解码/响度不能替代视觉验收，须完整看听
- 终片绑定真实 SHA 通过 `preview` 发布

## 6. 文字动效层叠加配方（去字幕的核心）
文字动效层是**带 alpha 的 mov（qtrle RGBA）**（见 typographic_motion.md 的 Chrome 渲染配方）。叠加到 AI 运镜底片：
```bash
# 文字层 transparent.mov (qtrle RGBA, 勿用 vp9+alpha) 叠到成片对应段
ffmpeg -i 成片.mp4 -i text_layer.mov \
  -filter_complex "[1:v]scale=1920:1080[tx];[0:v][tx]overlay=format=auto:eof_action=pass[out]" \
  -map "[out]" -map 0:a -c:v libx264 -crf 19 -c:a copy 成片_加文字动效.mp4
```
- 文字层时间轴须与口播一致（同 fps、同 END），用 `enable='between(t,start,end)'` 控制每段显隐。
- 背景透明的文字层可直接 overlay；若导出为黑底不透明，先 `colorkey`/ chromakey 抠掉背景再 overlay。

## 8. 自研 ffmpeg 快速产线（无剪好口播视频时的轻量路线，2026-10-07 标杆样例实测 + v2 升级）

输入「文案 + 产品图」时，adu 完整工程包不适配，走自研 ffmpeg 产线：
**TTS(edge-tts) → AI 运镜底片(云端/本地兜底) → Chrome 渲染文字动效层(透明) → ffmpeg concat + overlay 文字层 + 混流**。
参考实现：`样例_省团收款码/step1~6*.py`（v2 升级版会加 text_layer 渲染与 overlay）。

### 实测踩坑（必读，都是真金白银换来的）
1. **edge-tts 间歇性 NoAudioReceived**：先 `pip install -U edge-tts`（旧版 token 校验问题），再加重试（5 次退避）。本机坏代理(127.0.0.1:50841)会影响连接，跑 TTS 前清掉 HTTP_PROXY/HTTPS_PROXY。
2. **Chrome headless 截图默认白底**：`--screenshot` 不带 `--default-background-color=00000000` 时透明底变白底。**文字动效层需要透明背景**，务必加该参数；若导出为 PNG 序列再合成，也需透明。文字层直接渲成带 alpha 的视频（Chrome 截 RGBA PNG 序列 → ffmpeg 拼 **qtrle(RGBA)**）。**本机坑点：勿用 vp9+alpha webm**——本机 ffmpeg 的 libvpx-vp9 解码器不暴露 VP9-alpha 轨道，overlay 时透明区会被当成黑色盖住底图，表现为"产品画面变黑只剩文字"。卡片类不透明底则单独处理。
3. **zoompan 必须"单帧输入 + d=N 产帧"**：错误写法 `-loop 1 -t dur -i img` + `zoompan d=N` 会变成 输入帧数×N 帧爆炸（5.8s 段渲染成 14 分钟）。正确写法：`-i img`（不 loop）+ `-filter_complex "...zoompan=...:d=N"` + `-frames:v N`。**仅本地兜底 Ken Burns 才用，v2 主路径是 AI 运镜片段**。
4. **ASS Format 必须含 Effect 字段**（仅在仍用 ASS 兜底时出现）：`Format: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text` 少写 Effect 而 Dialogue 仍给 10 个值时，libass 会把空 Effect 用逗号拼进文本 → 每行字幕开头多一个「，」。**v2 默认不烧字幕，此坑可避**。
5. **竖图放横版**：`split → 底图 scale+crop+boxblur 填充 → 前景 scale=-1:960 居中 overlay`，再整体 zoompan 推近，比硬裁切观感好（仅本地兜底用）。
6. **分段渲染后必须 ffprobe 校验每段时长**再 concat，防爆炸/丢段静默混入成片。
7. AI 运镜片段（云端/本地）接入前用 ffprobe 校验分辨率/时长/fps，与成片参数统一后再 concat。

### 产线参数速查
- 竖屏 1080×1920 / 横屏 1920×1080 @30fps，crf 18（段）/ 19（终版），preset medium
- TTS：edge-tts zh-CN-YunxiNeural，rate +8%（口播带货节奏），按标点分段生成再 concat，逐段测时长落 `口播时间轴.json`（分镜时间码以它倒推）
- 文字动效层：Chrome headless `--window-size=1920,1080 --default-background-color=00000000 --screenshot?t=K/FPS` 抽透明帧 → ffmpeg 拼 **qtrle(RGBA)**（本机勿用 vp9+alpha，解码丢 alpha）；配色取自 product_3d_profile.brand_color，强调色 #FFD24D
- AI 运镜底片：product-360/千帆出片直接入轨；本地兜底用 §3 的 depth-aware 处理
