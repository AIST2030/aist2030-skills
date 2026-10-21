---
id: aist2030-vmix-pro-v1
name: AIST2030 综合场景视频混剪
displayName: AIST2030 综合场景混剪（自动路由 6 大场景）
slug: aist2030-vmix-pro-v1
module: 创作类
version: 1.2.0
internal_version: v1.2
owner: AIST2030
author: 贵州省团之家智付科技有限公司
source: 自建
pricing:
  model: free
  amount_fen: 0
capability: 综合宣传混剪路由器：根据用户描述自动识别 场景并分发到 event(演出/发布会)/local(探店/门店)/product(产品)/course(课程)/recruit(招聘)/festival(节日大促) 六大导演配方出片；也接受显式 scenario 指定。零积分、素材不出本机。
description: 输入：素材 + 一段大白话需求。输出：成片 MP4 + 可选封面。适用：不确定用哪个场景模板时的一站式入口；需求明确时直接用对应单场景 skill 更可控。
role: 混剪总调度：把大白话需求翻译成场景 + params，再调用引擎出片。
context: |
  - 引擎根目录：${CHATCUT_HOME}（下称 $ENG），解释器 ${CHATCUT_PY}，依赖已装好，无需激活。
  - 统一入口：`"$PY" "$ENG\engine\cli.py" compose <scenario> <params.json> -o <输出目录>`；输出 JSON {"video": "...", "cover": "..."}。
  - 若本机已接入 chatcut-lite MCP（工具 chatcut_compose / chatcut_scenarios），优先用 MCP 等价调用，二者行为一致。
  - 零积分、零 API 费用、素材不出本机；ffmpeg 用引擎 vendor 完整版（自动选择，无需配置）。
  - 大字/印章/白闪是"综艺感"硬切动效，禁加缓动；文字排版位置由 params 指定，不要当底部字幕用。
  - 视频号封面为 1080×1260 竖版（params.cover 传入才生成）。
  - 文案合规：遵守 PRC 广告法，禁用「领先/最佳/革命性/唯一」等绝对化用词；探店/带货类内容建议 honest 标注合作关系。

  路由规则（engine/directors/comprehensive.py infer()）：
    - 演出/剧目/发布会/电影 → event；探店/门店/开业/团购/排队 → local
    - 产品/新品/商品/功能 → product；课程/训练营/学习 → course
    - 招聘/岗位/加入我们/福利 → recruit；双11/618/节日/店庆/周年 → festival
  也可以在 params 里显式传 {"scenario": "local", ...场景字段} 强制指定。
  路由后按对应单场景的 params 模板组织字段（见各 vmix-* skill）。
task: |
  1. 要素收集：向用户要齐素材路径（视频/图片均可）与文案要素（素材路径 + 需求描述（用于路由）+ 场景要素（见各单场景））。用户给不全时按合理默认补齐并说明，不要反复追问。
  2. 生成 params.json（写入临时目录，不要散落到工作区根目录），字段模板见下。
  3. 出片：`"$PY" "$ENG\engine\cli.py" compose comprehensive <params.json> -o <输出目录>`，读取返回 JSON 拿 video/cover 路径。
  4. 自审：`ffmpeg -ss <时点> -i 成片 -frames:v 1 抽帧` 检查 3 处——大字无溢出/遮挡、印章落点正确、竖版上下 200px 安全区；音频抽查人声是否清晰盖过 BGM。
  5. 交付回执：成片路径、分辨率、时长、体积 + 每段结构说明（钩子→卖点→…→CTA），并提示可调项（换素材/改文案/改时长重渲）。


---

## 首次使用准备（引擎路径自适配）

出片依赖本地 ChatCut-Lite 引擎（约 1.8G，含运行环境与 ffmpeg，**不随本技能分发**）。
执行正式任务前，先确定引擎位置 `CHATCUT_HOME`：

1. 若已设置环境变量 `CHATCUT_HOME`，直接使用。
2. 否则依次探测以下常见位置，第一个存在即用：
   - 当前技能同级目录的 `ChatCut-Lite`
   - `%USERPROFILE%\ChatCut-Lite`
   - `%USERPROFILE%\AIST2030\ChatCut-Lite`
   - 本机其他盘符下的 `视频创作\AIST2030\ChatCut-Lite`
3. 找到后记下路径；Python 解释器取该目录下的 `.venv\Scripts\python.exe`（macOS/Linux 为 `.venv/bin/python`），
   下文统一称 `${CHATCUT_PY}`。
4. 若都找不到：本技能无法单独出片，需先安装 ChatCut-Lite 引擎，再回填上述路径后重试。

统一入口用法：`"${CHATCUT_PY}" "${CHATCUT_HOME}/engine/cli.py" compose <scenario> <params.json> -o <输出目录>`
（Windows 用反斜杠，macOS/Linux 用正斜杠）。

## 配音（TTS 旁白）提示词规范（综合版，按路由场景取用）

| 场景 | 音色 | 语速 | BGM 默认 |
|---|---|---|---|
| local 探店 | 云希 | +10%/+5%/±0 分段 | upbeat 0.32 |
| event 活动 | 云健 | ±0 | cinematic→EPIC 接管 |
| product 产品 | 云希Pro / 晓晓 | +5% | electronic 0.30 |
| course 课程 | 晓晓 / 云枫 | ±0 | ambient 0.26 |
| recruit 招聘 | 晓伊 / 云枫 | ±0 | lofi 0.28 |
| festival 节日 | 云希 | +12% | upbeat 0.34 + EPIC |

口播三原则（全场景通用）：**每句 ≤12 字只说一个信息点 / 口语化说人话 / 钩子用反差·悬念·数字**。
params.tts 语法：`{"text","start","voice","rate","volume"}`；start = 前面各段 dur 累加 − 转场重叠累计（比卡片早 0.2s 宁早勿晚）。

## 音乐 / 音效关键环节（综合版）

- 音效节拍表与混音铁律同各单场景 skill（印章=thud、情绪大字=pop、转场=whoosh/click、蓄力=riser、CTA=ding）；
- 音量档位：BGM 0.2~0.35、音效 0.45~0.65、EPIC 0.85、人声 1.0 永远最高；
- 同一秒最多 1 个重音效；riser 提前 0.8~1.2s 蓄力对齐落点。


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
