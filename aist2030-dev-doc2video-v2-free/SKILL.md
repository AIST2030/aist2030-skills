---
id: aist2030-dev-doc2video-v2-free
name: AIST2030 文案直出视频 v2（音效试听 + 自定义素材 + 画中画）
displayName: AIST2030 文案直出视频 v2（社区版）
slug: aist2030-dev-doc2video-v2-free
module: 开发工具
version: 2.1.0
internal_version: v2.1
owner: AIST2030
source: 自建
author: 贵州省团之家智付科技有限公司
description: '输入：一段口播文案（纯文本）与可选规格。输出：一条可发布的竖版故事成片视频
  （1080×1440，逐句配音 + 词级卡拉OK字幕 + 实拍素材打底 + 提炼信息图形叠加，可选音效/画中画）。
  适用边界：口播/盘点/种草类短视频批量生产；不含 BGM、不调用剪映、不使用真实 App 截图。'
tags: [文案转视频, 口播视频, 短视频生产, Remotion, TTS配音, 卡拉OK字幕, 音效, 画中画, doc2video, text-to-video
capability: 把一段口播文案自动转成"故事成片级"竖版视频：配音、分镜、素材、字幕、音效、质检全链路。
pricing:
  model: free
  amount_fen: 0
role: doc2video 产线编排助手（v2）。拿到一段口播文案，按本技能标准流程产出"故事成片级"竖版视频。
      v2 相对 v1 新增：①**音效试听勾选闭环**；②**用户自定义素材通道**；③**画中画PiP**。
      v2.1 相对 v2.0 新增（2026-10-18 贵阳选题实测回灌）：
      ④**风格自适应 + vivid 鲜活预设**（cinematic/tech/warm/vivid 四档按选题挑）；
      ⑤**一页多素材播放列表**（按实测时长排段 + 0.6s 交叉淡接 + 单段上限 6.5s + 自动循环，
        根治单素材循环的停滞/重复感）；
      ⑥**动效变体库**（金句 3 款/卡片 4 款/封面逐字弹入/大数字进度环/结论条扫光，相邻必不同款）；
      ⑦**页码横线误认修复**（章节锚条改为从顶边垂下的竖向色条）。
      内置四道自动闸门（素材亮度体检 / triggerWord 校验 / 抽帧QC / 成片五检）。
      负责「AI 分镜」这一需要语义理解的环节；其余一律调用 scripts/ 下已固化脚本，不凭记忆手写 ffmpeg。
context: '输入物：一段口播文案（纯文本，可含中英混排、数字、专有名词），以及可选规格（竖版 1080×1440 / 音效勾选 / 自定义素材 / 画中画视频）。

  背景：把文案直接变成可发布的视频成片，效果对标剪映「故事成片」——
  实拍视频打底 + **文字主体**图形叠加 + 逐句配音 + 词级卡拉OK高亮 + 可选音效/画中画。
  ★ 版式定型（用户历次反馈）：主要内容是文字信息 —— 关键词/金句/信息排列占画面主体位置，
    视频只作背景增加观赏性；**不要 BGM**（用户明令）。

  已知约束（硬）：
  1) 剪映未接入 WorkBuddy，**不要尝试调用剪映**，本技能是它的自研替代。
  2) 素材只走 Mixkit（视频）一个已验证白名单站；**图片通道已废除**（用户明令，只采视频）。
     Pixabay / aigei 实测 403，Pexels 需 key 且本机未配—— 一律不碰。
  3) 本机无系统 ffmpeg，必须用 envs/default 里 imageio_ffmpeg 自带的那个。
  4) 中文界面/真实App 截图受版权约束，**界面一律代码重绘示意**，不用真实截图。
  5) **素材检索词要对齐页面语义，不只对齐视觉风格**；夜景素材在深底上≈黑屏，
     抓完必须过亮度体检（见③闸门）。
  6) **每个 triggerWord 必须逐字出现在该页旁白里**，否则元素永不入场且渲染不报错（见④闸门）。
  7) **风格按选题自适应**（theme.ts ACTIVE_STYLE）：科技/AI/数码 → tech；
     本地餐饮/门店/民生消费 → vivid（活力橙+微信绿）；品牌/文创 → warm；通用叙事 → cinematic。
     别无脑用默认值。

  '
task: '把「一段口播文案」转化为「一条可发布成片」，严格按以下流程执行：

  ## 流程总览（六段）

  ```
  ① 断句配音  gen_narration.py       文案 → 分句 → edge-tts → 词级时间轴 timeline.json
  ② AI 分镜   ★由你（agent）做       定风格(vivid/tech/warm/cinematic) + 逐页图形叠加 + 检索词
                                      → shotplan.json + Root.tsx 的 OVERLAYS/PLAYLIST
  ③ 素材检索  fetch_media.py         Mixkit 视频 → 体检 → 落盘（可混入用户自定义素材）
                                      → gen_media_durations.py 实测每条素材时长（播放列表排段依据）
  ④ 音效试听  fetch_sfx.py + build_sfx_audition.py   抓音效库 → 生成自包含试听页 → 用户勾选 → 回写 sfxConfig.ts
  ⑤ 合成渲染  Remotion               播放列表打底 + 文字主体叠加 + 词级卡拉OK字幕 + 音效（无 BGM）+ 可选 PiP
  ⑥ 质检交付  render.py + qc_video.py  抽帧人工过目 → 整片 → loudnorm -16 LUFS → 五道闸门 → 成片
  ```

  ## ★ 三条并行可选能力（用户可任意组合，缺省都不启用）

  ### A. 音效试听勾选闭环（推荐默认开启）
  ```
  python scripts/fetch_sfx.py --out <项目>/remotion/public/sfx          # 抓一批 Mixkit 音效（多分类）
  python scripts/build_sfx_audition.py --sfx-dir <...sfx> --out <...sfx_audition.html>
  ```
  →把 `output/sfx_audition.html` 交给用户（present_files），
    让他试听→勾选→点「导出选择」得到 `{"enabled":[...文件名...]}`，
    你据此回写 `remotion/src/sfxConfig.ts` 的 enabled 数组。
  sfxConfig.map 把「封面/章节/金句/关键词/大数字/结论条」六个触发点映射到具体音效；
  某触发点映射的文件不在 enabled 中 → 该点静音（尊重用户勾选）。

  ### B. 用户自定义素材通道
  用户把自己的实拍素材放进 `<项目>/remotion/public/custom_media/`，命名 `p{n}.mp4`（整页替换）
  或 `{shot}.mp4`（单镜头替换），然后：
  ```
  python scripts/fetch_media.py --plan shotplan.json --out <项目>/remotion/public/media --custom <项目>/remotion/public/custom_media
  ```
  命中的走用户素材（不联网），未命中的仍走 Mixkit。混合使用。

  ### C. 画中画 PiP（用户提供讲解视频）
  用户放 `remotion/public/pip/pip.mp4`，把 `pipConfig.ts` 的 `enabled` 改 true，
  即可在右下角叠加一张圆角静音循环的讲解小窗（自动避让底部字幕）。
  可调 size / position / bottomGap。

  ## 编排入口（一条命令跑主流水线）

  ```
  # ① + ③ + 抽帧质检（不自动整片渲染、不含音效试听/分镜——分镜必须你亲自做）
  python scripts/pipeline.py --project <项目根> --script script.txt --stage all
  # 人工过目 output/qc/ 抽帧后，整片渲染 + 响度归一
  python scripts/pipeline.py --project <项目根> --stage render --yes
  ```
  ⚠ 纪律：整片 20+ 分钟，**必须先人工过目抽帧**再渲染，跳过需显式 --yes。

  ## ★ 四道自动闸门（减少返工= 省钱省算力，务必都跑）

  ```
  # 闸门③ 素材亮度体检（防夜景黑屏）：对每批 public/media/p*.mp4 抽帧算灰度均值，<12 判黑场
  python -c "import glob,subprocess,numpy as np,sys; FF=...[imageio_ffmpeg路径]; ... 见 references/gates.md"

  # 闸门④ triggerWord 校验（防元素永不入场）：静态比对 Root.tsx 的 triggerWord vs 旁白
  python scripts/check_triggers.py --project <项目根>

  # 闸门⑤ 抽帧 QC：每页取最长镜头中间帧渲静帧，人工过目
  python scripts/render.py --project <项目根> --mode qc

  # 闸门⑥ 成片五道质检：时长/分辨率/音轨/响度/黑帧
  python scripts/qc_video.py "<成片路径>"
  ```

  ## 硬约束与避坑（血泪，勿改）

  1. **先抽帧后整片**。整片 20+ 分钟，盲渲返工代价极高。
  2. **素材检索词对齐页面语义**。讲「PC 办公入口」别抓 city 夜景（既黑屏又语义不符）；
     办公/桌面用 lifestyle/business。
  3. **夜景/暗场素材在深底上≈黑屏**。抓完必过亮度体检，均值<12 就换素材。
  4. **triggerWord 逐字对齐旁白**，否则元素静默不入场。改文案必跑 check_triggers.py。
  5. **fetch_media.py --only 报「待处理 0 个」≠ 没活干**，多半是 shotplan 字段名不匹配
     （本脚本已兼容 id/page，改结构后仍要验一次生效）。
  6. **不要 BGM**（用户明令）。Remotion 直出响度偏低，成片后必须 loudnorm 归一到 -16 LUFS。
  7. **不要按渲染退出码判成败**。本机 wmic 被沙箱拉黑，Remotion 收尾探测资源会让整条命令被判
     failed——**以日志「成功N/N」+ 产物文件为准**（render.py 已内置该判定）。
  8. **界面类内容一律代码重绘**，禁用真实 App 截图（版权）。
  9. 并发≤4（8核16GB，可用内存常<2GB，开高会 OOM）。
  10. 不装系统 ffmpeg，一律用imageio_ffmpeg 自带二进制（render.py/fetch_media.py 已内置定位）。
  11. **★ 音效必须用 data URI 内联，不能用 `staticFile()`**。这是**唯一可靠解法**：
      `<Audio src={staticFile("sfx/x.mp3")}>` 走 HTTP 取文件，长片渲染中会**确定性崩**
      （本项目两次都精确崩在第 8355 帧，报 `Could not play audio ... MediaError`），
      而 Remotion 在 `Audio.js` 里把音频 `onError` **硬编码成 `cancelRender()`**——
      **Error Boundary 完全拦不住**，整片报废且无法容错，只能从源头消除文件 I/O。
      流程：`scripts/embed_sfx.py --project<根> --files a.mp3,b.mp3`
      → 生成 `src/data/sfxData.ts`（`data:audio/mpeg;base64,...`）
      → `sfxFile()` 直接返回该 URI，`Sfx` 里`<Audio src={file} />` **不要再套 staticFile**。
      体积无压力：Mixkit 音效 5~35KB/个，base64 后 20 个也就 1MB 出头。
12. **★ 音效改动必须渲一段带音频的片段验证，不能只抽静帧**。`still` 不播音频，
      静帧 QC 全绿也可能在整片里崩。改完渲**跨越崩溃点至少 500 帧**：
      `node node_modules/@remotion/cli/remotion-cli.js render <comp> out.mp4 --frames=8300-9000 --concurrency=2`
      注意 100帧片段不足以暴露问题（本项目 121 帧通过、整片仍崩），要 500+ 帧且必须放后台跑（前台会超时被 SIGTERM）。
13. **★ 同一页内不同触发点不要映射到同一个音效文件**，且每个 `<Sfx>` 必须带
      「类型前缀 + 触发时刻」的稳定 key（模板已内置，别删）。否则同页同类音效会互相顶掉。
14. 音效落盘后建议统一重转标准 CBR mp3，降低浏览器解码兼容风险：
      `ffmpeg -i x.mp3 -ac 1 -ar 44100 -b:a 128k -write_xing 0 -id3v2_version 0 y.mp3`
  15. **★ 渲染前必查磁盘余量 ≥ 20G**。Remotion 每帧截图写 `os.tmpdir()`（默认 C 盘），
      C 盘被历史渲染残留塞满时会在渲染中途 `ENOSPC` 直接废掉整片（本项目实测第 14307 帧崩）。
      `render.py` 已内置把临时目录改到 `<项目根>/_rtmp`（跟随项目所在盘），别绕过。
  16. **★ 清临时目录前必须先杀进程**。`rm -rf` 在目录仍被 chrome/node 占用时会**静默失败**
      （不报错、`df` 不变，白跑一趟）。先 PowerShell 工具终止进程，再删。
      查/杀进程**必须用 PowerShell 工具**，不能从 Bash 调`powershell -Command`（会被安全检查拦）。
      同理，写含 PowerShell 管道命令的 heredoc 也会被拦——追加记忆用 Write/Edit 工具。
  17. **★ 一页多素材播放列表**（v2.1）：素材落盘后必跑
      `python scripts/gen_media_durations.py --project <项目根>` 实测每条素材时长写入
      `src/data/mediaDurations.json`——播放列表排段、交叉淡接、单段上限 6.5s 全靠它。
      Root.tsx 的 `PLAYLIST[页id]` 是**文件名数组**（按期望顺序），改素材后必须重跑 durations。
      长素材到 6.5s 自动交棒下一个，根治"整页一条视频循环"的停滞/重复感。
  18. **★ public/ 会被 webpack 整包拷进渲染临时目录**：`public/media/_raw/`（原始下载片，
      可能几百 MB）在 ffmpeg 转码完成后**必须删除**，否则 bundle 阶段直接 ENOSPC。
      渲染前 `df -h` 查项目所在盘余量 ≥ 20G（临时目录已由 render.py 改到 `<项目根>/_rtmp`）。
  19. **复用 node_modules 用 PowerShell 建 junction**：`New-Item -ItemType Junction
      -Path <新项目>\node_modules -Target <老项目>\node_modules`——Git Bash 里
      `mklink /J` 的斜杠参数会被吃掉，别用。engine 已内置 `src/index.ts`
      （registerRoot 入口），自建项目缺它会全挂 "No entry point specified"。
  20. **章节锚条是竖向色条（从画面顶边垂下、6px 宽），别改回横线**——编号前的 34×4 横线
      会被观众看成汉字"一"（"一 ·"读成"一一/一二"误读，2026-10-18 用户反馈）。
      竖条不可能被误读成任何汉字，同时配 ①②③ 圆圈号双保险。

  ## 交付物

  - 成片 `<项目>/output/成片.mp4`（或指定名）
  - 抽帧 `<项目>/output/qc/`、音效试听页 `<项目>/output/sfx_audition.html`
  - 一句话向用户汇报：风格档位（vivid/tech/warm/cinematic）、音效勾选结果、素材来源与每页播放列表条数、PiP 是否开、质检结论。
  '
---