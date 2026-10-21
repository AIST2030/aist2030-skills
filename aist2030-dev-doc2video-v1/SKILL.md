---
id: aist2030-dev-doc2video-v1
name: AIST2030 文案直出视频（故事成片级）
displayName: AIST2030 文案直出视频
slug: aist2030-dev-doc2video-v1
module: 开发工具
version: 1.2.0
internal_version: v1.2
owner: AIST2030
source: 自建
author: 贵州省团之家智付科技有限公司
pricing:
  model: per_call
  amount_fen: 1
role: doc2video 产线编排助手。拿到一段口播文案，按本技能的标准流程产出"故事成片级"竖版视频；
      负责「AI 分镜」这一需要语义理解的环节，其余环节一律调用 scripts/ 下已固化的脚本，
      不重复造轮子、不凭记忆手写 ffmpeg 命令。
context: '输入物：一段口播文案（纯文本，可含中英混排、数字、专有名词），以及可选的成片规格。

  背景：需要把文案直接变成可发布的视频成片，效果对标剪映「故事成片」——
  实拍视频打底 + **文字主体**图形叠加 + 逐句配音 + 词级卡拉OK高亮。
  ★ 2026-10-17 版式定型：主要内容是文字信息 —— 关键词/金句/信息排列占画面主体位置，
  视频只作背景增加观赏性；**不要 BGM**（用户明令）。

  已知约束（硬）：
  1) 剪映未接入 WorkBuddy（无连接器、无 MCP、无公开成片 API），**不要尝试调用剪映**，
     本技能就是它的自研替代。
  2) 素材只走 Mixkit（视频）一个已验证白名单站；**图片通道已移除**（2026-10-17 用户明令：
     只采集视频，早期怀疑卡顿是图片导致——实测证伪，真因是渲染层 CSS filter/blend，
     但图片通道仍按用户要求废除）。Pixabay / aigei 实测 403，Pexels 需 API key 且本机未配置
     —— 一律不碰。
  3) 本机无系统 ffmpeg，必须用 envs/default 里 imageio_ffmpeg 自带的那个。
  4) 中文界面/真实 App 截图受版权约束，**界面一律代码重绘示意**，不用真实截图。

  '
task: '把「一段口播文案」转化为「一条可发布成片」，严格按以下流程执行：

  ## 流程总览（五段）

  ```
  ① 断句配音  gen_narration.py   文案 → 分句 → edge-tts → 词级时间轴 timeline.json
  ② AI 分镜   ★由你（agent）做   逐镜定：画面意图 / 检索词 / 图形叠加 → shotplan.json
  ③ 素材检索  fetch_media.py     Mixkit 视频 → 下载转码落盘（无图片）
  ④ 合成渲染  Remotion           实拍视频打底 + 文字主体图形叠加 + 词级卡拉OK高亮（无 BGM）
  ⑤ 质检交付  render.py          抽帧人工确认 → loudnorm -16 LUFS → 成片
  ```

  ## 编排入口（推荐：一条命令跑全流程）

  ```
  # ① ② ③ + 抽帧质检（不自动整片渲染）
  python scripts/pipeline.py --project <项目根> --script script.txt --stage all
  # 人工过目 output/qc/ 抽帧后，整片渲染 + 响度归一
  python scripts/pipeline.py --project <项目根> --stage render --yes
  ```
  ⚠ 纪律：`pipeline.py` **故意不自动跑整片渲染**。整片 20+ 分钟，
  必须先人工过目抽帧，确认画面/字幕无误再渲染。要跳过需显式 `--yes`。

  ## ① 断句配音（脚本，不改）

  复用 scripts/gen_narration.py（源自 weixin-xiaowei-video 实战验证版）：
  edge-tts 合成 → WebVTT 词级对齐 → 首尾静音裁剪 → 输出 timeline.json。
  产物 audio/ 下每段一个 mp3，timeline.json 含每句 words[]（词级时间戳，
  这是字幕踩点和图形触发的全部依据）。

  配音参数（2026-10-17 从 PPT 解说任务移植，用户认可）：
  - 音色 `zh-CN-XiaoxiaoNeural`（女声 Warm 播客感）、rate `+25%`、pitch `-8Hz`；
    ⚠ rate 已对齐 PPT 解说任务（用户明令 +25%，不是 -4%）；改了要同步改
    `gen_narration.py` 的 `RATE` 常量与本文档。
  - `PRONUNCIATION` 发音替换表（AI→"A I"、MoE/MCP/PC/GEO/PDF/API/App/WeLM
    逐字母读等），仅在 TTS 层应用，时间轴 words[] 仍对齐原文；
  - 中英文之间加空格优化分词（"原生 AI 助手"）；edge-tts 不支持 SSML phoneme，
    发音问题只能文本层解决。

  ## ② AI 分镜（★核心，本技能的价值所在）

  这是唯一必须由 agent 完成的环节，脚本做不了。对**每一个镜头**输出：

  - `intent`（画面意图），四选一：
    - `narrative` 叙事/氛围 → 走实拍素材（通道 A）
    - `data` 数据/清单/对比 → 走代码图形（通道 B），实拍表达不了数字
    - `ui` 产品界面/操作路径 → 代码重绘界面示意（通道 B，禁止真实截图）
    - `statement` 观点/结论 → 实拍打底 + 大字叠加（A+B）
  - `query`：给素材检索用的**视觉意象关键词**，不是产品名。
    ⚠ 关键经验：搜"微信小微入口"在素材站搜不到任何东西，
    必须转译成通用视觉词，如 手机 / 聊天 / 打字 / 办公 / 城市夜景 / 手指点击。
  - `overlay`：要叠加什么图形（大数字 / 图标卡片 / 列表 / 进度条 / 关键词）。

  输出 shotplan.json（字段见 scripts/ 下说明），供 ③ 消费。

  ## ③ 素材检索（脚本）

  ⚠ **先跑预分配，再并行下载**（这是多进程安全的前提）：
  ```
  # 1) 预分配：按分类解析并锁定每个镜头的 video id，全片不重复
  python fetch_media.py --plan shotplan.json --out <项目>/remotion/public/media --assign-only
  # 2) 下载（可起多个受管后台任务，按 --only 分页并行）
  python fetch_media.py --plan shotplan.json --out <项目>/remotion/public/media --only p1,p2
  python fetch_media.py --plan shotplan.json --out <项目>/remotion/public/media --only p3,p4
  ```
  - 自动做真人节流（1–3s 随机停顿），禁止机器连续请求。
  - 视频：走 Mixkit **分类页**（默认 720 → 1080 → 360 换档），下载后 `-an` 静音 +
    scale/crop 到目标画幅 + **烘调色**（gblur 柔化 + `eq=saturation=0.82:contrast=1.10:gamma=0.96`，
    见下方性能禁忌）。query 直接写分类名即可，也支持 `cat:` / `slug:` 前缀。

  - **⛔ 调色参数铁律（2026-10-17 二次事故，21 个素材全废）**：
    ffmpeg `eq` 的 **`brightness` 是加法偏移，取值 −1.0~1.0，不是乘法系数**。
    写成 `brightness=1.08` → 整幅 +275 → 所有素材被冲成**纯白**（亮度均值 255），
    成片背景变成一片灰白雾，用户直接反馈"背景看不到视频了"。
    **要提亮/压影调一律用 `gamma`（<1 压暗中间调）或 `contrast`，永远不要再碰 brightness。**
    验收方法：转码后抽一帧算灰度均值，应与 raw 源相差不超过 ±15；
    `python -c "…scale=90:120 -f rawvideo -pix_fmt gray…"` 一行即可测。

  - **图片通道已废除**（2026-10-17 用户明令"只采集视频"）：cc0.cn 检索代码已从
    fetch_media.py 移除，plan 里遇 image 类型显式跳过。早期"卡顿是图片导致"的猜测
    已证伪（真因是渲染层 CSS filter），但通道仍按用户要求废除，勿再加回。
  - 输出 media_manifest.json 回报每镜成败；**失败的镜头不报错、回退纯图形层**。

  ### ⚠ Mixkit 三条铁律（2026-10-17 实测，别重复踩）
  1. **Mixkit 的搜索页不可用**：`?q=` 与 `/search/?s=` 返回的都是首页推荐列表
     （换关键词 video id 完全不变，实测 4 个词返回同一批 id）。
     连 Chrome headless dump-dom 渲染也拿不到真搜索位。
     → **不要浪费时间做搜索**，直接用分类页。
  2. **分类页可用且必用**：`https://mixkit.co/free-stock-video/<category>/`
     实测可用分类见脚本内 `MIXKIT_CATEGORIES`（约 90 个纯分类）。
  3. **必须全片去重**：同一分类服务多个镜头时，脚本会自动顺延取该分类的
     下一个视频；不做去重会出现大量重复画面。
  4. **★ 3D 渲染黑名单，选分类时先查**：`technology / abstract / light /
     ai-generated / double-exposure / background / intro / space / earth`
     下大量是 CG 渲染素材（粉色紫色块、粒子特效），与「深蓝黑+暖金」品牌
     基调冲突，观感廉价（实测：p3_s1 用 technology 拿到粉色 3D 渲染，
     整组换掉才合格）。**优先用实拍白名单**（脚本内 `REAL_FOOTAGE_CATS`）：
     business / people / man / woman / family / lifestyle / street / city /
     night / traffic / road / house / fire / smoke / sunset / sea / sky …
  5. **语义映射 > 关键词匹配**：分镜时按「文案情绪」选实拍分类，
     如"三条红线"→fire（红色警示）、"入口铺开到 28 个"→traffic（车流=
     全面铺开）、"下期再见"→sunset（暖金收尾）。脚本对黑名单分类会打印警告。

  ### ⚠ 原子落盘（并发渲染的隐形杀手）
  下载与转码一律先写 `<名字>.part<原扩展名>`（如 `p1_s0.part.mp4`），成功后
  `os.replace` 原子改名。否则 Remotion 并发渲染时会加载到半成品 mp4 →
  Video 组件卡死 → 整帧超时。（实测踩过：QC 抽帧 1600 帧因此 timeout）
  ⚠⚠ **临时名必须保留原扩展名**：写成 `p1_s0.mp4.part` 会让 ffmpeg 报
  "Unable to choose an output format"，全片 0/21 失败（实测踩过）。

  ### 素材语义的现实边界（要如实告知用户）
  Mixkit 是通用生活类素材库，**强项是自然/人物/城市/生活**，
  没有"手机界面/聊天窗口/办公软件"这类产品向素材。
  因此本产线的实拍层主要承担**氛围与情绪**，信息由图形叠加层承载。
  界面类内容一律**代码重绘示意**（也规避了 App 截图版权风险）。

  ## ④ 合成渲染（Remotion）

  用 templates/engine/ 下的通用引擎（2026-10-17 二轮返工后的定型版，
  weixin-xiaowei-video 验证）：

  ★ **版式总原则（用户两轮反馈后的最终定位）**：
    - 主画面 = **提炼**内容：封面大标题 / 金句大字体动画 / 关键词卡片 /
      大数字滚动 / 结论条。每页只放 1–2 类，绝不堆满；
    - **完整讲稿走底部单行卡拉OK字幕**（Caption，原样式，坚决一行）；
    - ⛔ 反面案例：第一版把讲稿全文放大到主屏当"hero 文字"→ 用户否掉：
      "不是把所有字幕搬到主画面，我们要做提炼关键词和金句、大字体动画、多样式丰富画面"。

  - `Root.tsx`：`MEDIA`（shot id → 文件名）+ `OVERLAYS`（每页策展内容）两张表驱动全片；
    **无 BGM**（用户明令）；音效由 MediaScene 内的 `<Sfx>` 触发。
  - `scenes/MediaScene.tsx` 文字主体场景：
    - `OverlaySpec = { cover?, section?, golden[]?, keywords[]?, bigNumber?, banner? }`；
      全部语音 `triggerWord` 触发，跨镜头用 `triggerAny(page,…)` 找词；
    - **关键词自适应布局 `gridCells(n)`**（用户明令"不要无论多少项都拥挤横排一排"）：
      1=通栏 / 2=一行两张 / **3=正三角（上1下2，带金色连线动画）** / 4=2×2 /
      5=3+2 / 6=3+3 / 7=3+2+2 / 8=3+3+2 / 9=3×3；
    - **等宽原则**：多行网格所有行共用第一行（最多列）的卡片宽度，少的行整体居中。
      否则 3+2 的第二行会被拉宽，同页出现两种卡片尺寸，观感廉价；
    - **入场与高亮解耦（重要）**：`kEnter`（整组 ~0.6s 内依次浮现，版式立刻完整）
      与 `kHi`（严格跟语音，说到哪个词哪张卡发光）分开算。
      早期两者共用触发时刻 → p5 三条红线里第三词说得晚，正三角长时间缺一角，像 bug；
    - 大数字滚动按 `1-(1-p)^3` 缓动；金句逐字入场 + 左侧金条 scaleY 生长；
    - 音效：whoosh（封面/章节头/金句）、pop（卡片）、sparkle（大数字）、
      alert（结论条），音量 0.13–0.20，**只点缀不抢旁白**。
  - `theme.ts` **风格预设系统**：`STYLES = { cinematic, tech, warm }`，
    切风格只改 `ACTIVE_STYLE` 一行；含 tint/letterbox/grain/vignette/glowRgb/cardBg；
    另导出 `textUnits()`（视觉宽度 中文1.0/英数0.58）与 `fitFontSize()`。
  - `MediaLayer.tsx` 素材层：Ken Burns 缓动（按 `durationInFrames` 算进度）、缺失兜底。
    压暗只用**纯渐变**（40% 处 `dim*0.55`≈0.30，底部 0.86），保住深色底又不糊死视频。
    ⚠ **调色必须烘进 ffmpeg 转码**，渲染层**禁用 CSS `filter` / `mixBlendMode`**——
    会导致 Chrome 每帧重新光栅化视频层，全片卡顿（2026-10-17 实测踩坑，
    用户报"视频卡顿"后定位至此，移除即流畅）。
  - `Atmosphere.tsx` 全局氛围（微光/颗粒/暗角）；颗粒层同样禁用 mixBlendMode。
  - `Caption.tsx` 词级时间工具（trigger/triggerAny/usePageT）+ 底部单行字幕本体。
  - `ui.tsx` 图形原件库（图标/章节头/品牌标/页码），全部接 `S.*` 风格色。

  ### ⚠ JavaScript `\W` 是 ASCII-only（汉字全匹配 `\W`）—— 关键陷阱

  用 `/[\s\W]/` 过滤"标点"时，**汉字全部被当标点**，clean↔text 索引映射只剩英文字母，
  中文词的 ci 全错位（实测词"是"映射到"M"的位置），断行/收词全线崩坏。
  Python 的 `\W` 是 Unicode 感知的，所以同算法 Python 模拟正常、TS 渲染异常。
  正解：词字符判定写 `/[\u4e00-\u9fffA-Za-z0-9]/`（见 MediaScene.tsx `isWordChar`）。

  ### ⚠ 缩写保护（两处都要守，2026-10-17 实测）

  edge-tts 会把品牌/缩写逐字母分词（W/E/L/M，AIST2030→`A|I|S|T 2030`），
  缩写串**中间位置不是合法断点**，硬切会出 "T 2030下一期…" 这种半截词。

  1) **底部单行字幕（Caption.tsx `chunkShot`）**：溢出断点时用 `LETTER_TOKEN`
     识别"自身与前一词均为单字母"的边界，把断点回退到字母串之前；
     再用 `displayWord()` 把 `"T 2030"` 显示合并成 `"T2030"`，消除字幕里莫名空格。
  2) **主画面提炼大字（MediaScene 关键词/金句）**：收集词序列时跳过
     「自身与前一词均为单字母」的衔接，避免金句被拆成散字母。
  换文案若含新缩写，先确认这两处是否覆盖，否则会出现半截词 bug。

  场景组件按文案内容现场写，放进 remotion/src/scenes/。

  ## ⑤ 质检交付

  - **先抽帧后整片**：整片渲染 20+ 分钟，盲渲代价高。按时间轴算出关键帧区间，
    各渲 10–15 帧抽检，全过再开整片（此经验来自张一鸣项目，务必沿用）。
  - 音频 double-pass loudnorm 到 **-16 LUFS**。
  - 成片落在项目 output/ 下，中间产物清理干净。

  '
format: '交付物：
  1. 成片 mp4（项目 output/ 下）
  2. shotplan.json（分镜决策，可复用于同类选题）
  3. media_manifest.json（素材来源清单，便于署名与复查）

  过程回报：每段结束一行状态（成功/失败/回退原因），不堆砌日志。

  '
constraint: '- 禁止调用剪映 / CapCut 的任何能力（未接入），不要为此浪费时间试探。
- 素材白名单硬约束：仅 mixkit.co（视频，分类页）；图片通道已废除；
  禁止访问 pixabay.com、aigei.com、api.pexels.com（403 / 401，碰了也是白跑）。
- 不得下载或使用受版权保护的 App 真实截图；界面一律代码重绘。
- ffmpeg 只能用 envs/default 内 imageio_ffmpeg 自带的：
  C:/Users/Administrator/.workbuddy/binaries/python/envs/default/Lib/site-packages/
  imageio_ffmpeg/binaries/ffmpeg-win-x86_64-v7.1.exe
  或由脚本 `imageio_ffmpeg.get_ffmpeg_exe()` 自动解析，禁止手写其他路径。
- Windows 下 wmic.exe 被安全策略拉黑，命令退出码可能异常 —— **判成功一律以产物为准**。
- 渲染并发 ≤ 3~4（8 核 / 16GB，可用内存常低于 2GB）。
- 所有产出物必须落在本次任务的项目文件夹内，严禁散落到工作区根目录。

  '
quality_gate: '交付前自检：
  □ 五个环节都跑过，无跳步（尤其②分镜不能省）
  □ media_manifest.json 里失败项已确认有图形层兜底，无白屏
  □ **转码后抽帧测灰度均值**，与 raw 源相差 ≤ ±15（防 eq.brightness 冲白事故）
  □ 抽帧质检通过后才整片渲染
  □ 成片 -16 LUFS、无破音、词级高亮与旁白对得上
  □ **背景实拍视频肉眼可见**（不是一片灰雾/纯色），且画面仍是深色底
  □ **底部字幕严格单行**（不换行、不跳行、不压结论条）
  □ 主画面只有提炼内容（金句/关键词/大数字/封面/结论条），没有搬讲稿全文
  □ 每页关键词按项数走了自适应布局（3=三角 4=矩形 5=3+2 …），无拥挤横排
  □ 卡片入场后版式完整（无长时间缺角），高亮与语音同步
  □ 全片无 BGM 音轨（用户明令），音效仅在入场点轻点缀
  □ 素材来源可追溯（manifest 有 source 字段）

  '
anti_dup: 与 aist2030-dev-ppt-narration-video-v2（PPT 备注驱动）互斥：
  那条走 PPT/备注 → 动效视频；本技能走**纯文案 → 视频**，不经过 PPT。
  用户说"不靠PPT、靠文案直接出"时走本技能。
input_schema: 一段口播文案（纯文本）+ 可选成片规格（默认 1080x1440 3:4 竖版 / 30fps）
output_schema: 成片 mp4 + shotplan.json + media_manifest.json
capability: 提供「文案直出故事成片级视频」能力：一段口播文案 → 自动分镜 → 白名单素材检索 →
  配音词级对齐 → Remotion 合成 → 质检成片，全流程可复用，换文案即可重出片。
description: 输入：一段口播文案（如产品盘点、知识科普、观点输出），可选成片规格。
  输出：故事成片级竖版视频 mp4 + 分镜表 + 素材来源清单。
  适用边界：仅处理"文案 → 视频"；素材只用 Mixkit 免费可商用视频源（分类页）；
  涉及 PPT/备注驱动时应改用 aist2030-dev-ppt-narration-video-v2。
  当用户说"这段文案出个视频""故事成片""文案直接出片"时调用。
tags:
- doc2video
- 文案转视频
- 故事成片
- Remotion
- Mixkit
- cc0
- 竖版视频
- 自动分镜
