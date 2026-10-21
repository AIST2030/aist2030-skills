# ChatCut-Lite 排错手册

按「症状 → 根因 → 修法」组织，都是实测踩过的坑。

---

## 环境类

### `找不到 ChatCut-Lite 引擎本体`
**根因**：脚本按固定路径找引擎，路径变了。
**修法**：改 `scripts/ccl.py` 顶部 `ENGINE_CANDIDATES`，加入实际路径。当前路径：
`E:\视频创作\AIST2030\ChatCut-Lite`

### `ModuleNotFoundError: No module named 'PIL'`
**根因**：用了系统 Python，依赖装在项目 `.venv` 里。
**现象**：脚本已内置自动切换逻辑，若仍报错说明 `.venv` 不完整。
**修法**：双击 `启动.bat` 走首次安装流程，或手动
`ChatCut-Lite\.venv\Scripts\python.exe -m pip install numpy pillow flask edge-tts faster-whisper "av<14" opencc-python-reimplemented`

### doctor 显示「完整版：✗ 否（缺 libx264）」
**根因**：用到了本机F 盘的极简 ffmpeg。
**关键**：本机 `F:\Work_Buddy\数字人口播\tools\yovoice-cli\tools\ffmpeg.exe` 是
`--disable-everything` 构建，**只能做音频转码**，没有 libx264 / xfade / subtitles / overlay。
**修法**：在 `ChatCut-Lite\vendor` 执行 `npm i ffmpeg-static ffprobe-static`（首次约 26 分钟）。

---

## 网络类

### `httpx.ProxyError: 502 Bad Gateway` / `LocalEntryNotFoundError: ConnectTimeout`
**根因**：本机注入了 `HTTP_PROXY=127.0.0.1:50841`，对 huggingface 一律 502；直连又超时。
**修法**（已内置 `disable_proxy()`，手动跑时需自己清）：
```bash
# 清代理 + 装无代理 opener
python -c "
import os, urllib.request
for k in ['HTTP_PROXY','HTTPS_PROXY','http_proxy','https_proxy','ALL_PROXY','all_proxy']: os.environ.pop(k,None)
urllib.request.install_opener(urllib.request.build_opener(urllib.request.ProxyHandler({})))
"
# 镜像 + 禁Xet
export HF_ENDPOINT=https://hf-mirror.com
export HF_HUB_DISABLE_XET=1
export HF_HOME=<E盘路径>/workspace/cache/hf
```

### `RuntimeError: CAS Client Error: 401 Unauthorized (xethub)`
**根因**：HuggingFace 的 Xet 加速后端在镜像上未授权。
**修法**：`HF_HUB_DISABLE_XET=1`。

---

## 依赖冲突

### `TypeError: open() got an unexpected keyword argument 'metadata_errors'`
**根因**：faster-whisper 与新版 PyAV(av19) 不兼容。
**修法**：`pip install "av<14"`（13.1.0 可用）。

---

## 剪辑类（引擎内部，脚本已修，此处记录原理）

### `Filter not found` / `Invalid stream specifier: xxx`
**根因1**：`amix` 多输入写成 `"[a],[b]amix=..."`（多了逗号）。必须 `"[a][b]amix=..."`。
拼标签绝不能用 `",".join()`，要用 `"".join()`。
**根因 2**：一个滤镜输出直接喂给两个下游。必须显式 `asplit=2`（做 ducking 时必踩）。

### MG 动画不显示 / 图层莫名消失
**根因**：`overlay` 的 `eof_action`。当 MG 序列比主视频短时，
默认行为与 `pass` 都会让图层在序列结束后**不再叠加**。
**修法**：必须用 `eof_action=repeat`，配合 `enable='between(t,start,end)'` 控制显隐。

### 成片被截短（画面尾巴没了）
**根因**：mux 阶段用了 `-shortest`。`sidechaincompress`（人声压背景音）会让音频轨略短于画面，
`-shortest` 会把整条片子截到音频长度。
**修法**：`-af "apad,atrim=0:{vdur}" -t {vdur}`。

### 纯音频输入做成片时，时长严重偏长
**症状**：时间线算出 12s，成片却是 70s。
**根因**：纯色画面底时长只有 17.8s，但每个片段按原音频时间轴 `src_in` 去裁剪，
多次裁剪累积后读到片尾，导致输出被拉长。
**修法**：纯色底按需补足长度，且视频片段统一取 `src_in=0`。

### 中文繁体
**根因**：whisper 中文模型有时输出繁体。
**修法**：已内置 opencc `t2s` 转简体。

### 口头禅误删导致语义残缺
**症状**：把「这个方法」的「这个」删了，变成「方法」。
**修因**：单纯按词表匹配不够。
**修法**：已实现语义保护——
- `_BOUND_PREFIX`（这个/那个/就是…）+ `_BOUND_SUFFIX`（方法/问题/时候…）搭配时回滚
- `_TAIL_ONLY`（对吧/是吧/是不是…）只在句尾删除，句中保留

---

## 磁盘与性能

### C 盘吃紧
**根因**：ffmpeg / whisper 默认往C 盘临时目录写。
**修法**：已在 `config.py` 与 `启动.bat` 强制
`TMP = TEMP = TMPDIR = workspace/cache`，`HF_HOME` 也在 E 盘。
手动跑脚本时记得先 export 这几个变量。

### 渲染很慢
**说明**：默认 `-preset veryfast -crf 18`，质量与速度平衡。
追求速度可改 `-preset ultrafast`；追求体积可提高 crf。
## P12 后半段全静音（2026-10-18 海底两万里实战）
- 症状：成片只有开头一段有声，之后 20+ 秒无语音无音乐无音效。
- 根因1：`build_audio` 阶段1 只做 `atrim(src_in,dur)` 源内截取，**忽略 `c.start`**（无 adelay）→ 所有音频片段都从 0s 叠着放。以前被长旁白掩盖。
- 根因2：`sidechaincompress` 输出时长取主/侧链输入**较短者** → 人声总线短于全片时，BGM 被截断。竖版靠长 TTS 逃过一劫。
- 修复：片段处理后 `adelay={start*1000}:all=1` 摆到时间线；voicebus 先 `apad=whole_dur=mix_dur` 再 `asplit=2` 进侧链。mix_dur=max(start+dur)。
- 排查捷径：`silencedetect=noise=-35dB:d=1` 一步定位静音区间；注意 **改完引擎必须重启 server.py**（渲染跑在服务进程里，老进程用的还是旧代码——本次踩坑：第一次重渲仍静音就是因为没重启服务）。

## P13 服务端渲染任务线程无声消失（2026-10-18 v3 实战）
- 症状：/api/job 一直 running（progress 0.2 渲染中），py-spy dump 发现进程只剩 MainThread，_v.mp4 已产出但 _a.m4a 从未创建，也无 ffmpeg 子进程。
- 处置：server.py work() 增加 except BaseException 兜底落 error 状态；应急路径 = 拿 cache/render_xxx_v.mp4 离线直跑 build_audio + 后期合成（finish_v3.py 模式），不依赖服务端。
- 沉淀：engine/fx.py —— 综艺感动效图层系统（flash 闪现 / stamp 砸章 / bounce 弹入，全部硬切无缓动；text_block_png 自由排版、seal_png 圆形印章）。Mixkit 音效直链：assets.mixkit.co/active_storage/sfx/<id>/<id>-preview.mp3，id↔名称从分类页 DOM 顺序配对提取。
- 排版原则（用户定调）：文字是重要信息，禁止全部底部字幕式；按内容自由适配（居中大字/左上/顶部/右下/竖排/印章），静帧卡完全静止（去 zoompan/去 noise 颗粒）杜绝抖动，进出场纯硬切。

## P14 冲击力编排 + 视觉起点语义 bug（2026-10-18 v3 冲击力版）
- 引擎升级：build_video 的 transitions 值支持 (名称, 时长) 元组，逐转场独立时长（前段柔和 fade + 后段 fadewhite 0.16~0.24s 白闪快切可共存）。fadewhite 是综艺爆点标配转场。
- ★visual_starts 历史 bug：引擎语义转场 k = 段 k-1→k 之间（循环从 1 开始，TRANS[0] 无效），但 visual_starts 把 TD[0] 也减了 → 所有视觉起点系统性偏早 0.4s（=TD[0]）。图层/音效与画面渐近错位。修法：`if i >= 1 and i in TD` 才减。校验手段：probe 拼接产物时长必须 == visual_starts 的 total（30.167==30.16 ✓）。
- 冲击力三板斧（用户反馈"榜单起画面音乐太平淡"的解法）：① 白闪快切转场 ② 盖章瞬间全屏白闪 2-3 帧（lavfi color source + overlay enable，放 fx 图层之上）③ 音乐三层递进：主 BGM(90BPM) → +合拍鼓点层(kick 每拍+clap 每两拍，起点对齐主 BGM 拍点 ceil(t/beat)*beat) → +electronic 高潮层；卡片/盖章落点叠 thud 低频重击(胸腔感)。响度弧线 -19/-24.5/-20 dB。
- 坑：finish 脚本里标签拼接必须带方括号统一处理（`base = vlabel if vlabel.startswith("[") else f"[{vlabel}]"`），否则 "w1fade" 被当滤镜名报 Filter not found。
