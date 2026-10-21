---
id: aist2030-vmix-recruit-v1
name: AIST2030 招聘雇主品牌混剪
displayName: AIST2030 招聘/雇主品牌宣传混剪
slug: aist2030-vmix-recruit-v1
module: 创作类
version: 1.2.0
internal_version: v1.2
owner: AIST2030
author: 贵州省团之家智付科技有限公司
source: 自建
pricing:
  model: free
  amount_fen: 0
capability: 招聘宣传混剪：公司氛围开场→岗位亮点与福利卡→团队/办公环境实拍→投递 CTA 盖章；upbeat BGM。零积分、素材不出本机。
description: 输入：办公环境/团队素材 + 岗位信息 + 福利清单。输出：竖版/横版成片 MP4 + 可选封面。适用：招聘海报视频、雇主品牌、校招宣传。
role: 雇主品牌导演：氛围代入 + 福利清单节奏化 + 投递入口盖章收口。
context: |
  - 引擎根目录：${CHATCUT_HOME}（下称 $ENG），解释器 ${CHATCUT_PY}，依赖已装好，无需激活。
  - 统一入口：`"$PY" "$ENG\engine\cli.py" compose <scenario> <params.json> -o <输出目录>`；输出 JSON {"video": "...", "cover": "..."}。
  - 若本机已接入 chatcut-lite MCP（工具 chatcut_compose / chatcut_scenarios），优先用 MCP 等价调用，二者行为一致。
  - 零积分、零 API 费用、素材不出本机；ffmpeg 用引擎 vendor 完整版（自动选择，无需配置）。
  - 大字/印章/白闪是"综艺感"硬切动效，禁加缓动；文字排版位置由 params 指定，不要当底部字幕用。
  - 视频号封面为 1080×1260 竖版（params.cover 传入才生成）。
  - 文案合规：遵守 PRC 广告法，禁用「领先/最佳/革命性/唯一」等绝对化用词；探店/带货类内容建议 honest 标注合作关系。

  params.json 字段模板：
    {"name":"加入我们","hook_shot":{"src":"办公氛围","dur":2.8},
     "hook":[["找一群", 100, [255,255,255,255]],["把事做成的人", 72, [255,214,110,255]]],
     "reveal":{"src":"团队实拍","dur":3.0,"cap":[["AI 应用工程师 · 贵阳", 72, [255,255,255,255]]]},
     "tastes":[{"src":"福利画面","cap":[["六险一金 · 弹性办公", 60, [255,240,220,255]]],"emo":["真香", 88, [255,214,110,255]]}],
     "cta":{"title":"简历投递","lines":["hr@example.com"]},
     "outro":[["等你来", 90, [255,214,110,255]]],"out":"成片.mp4"}
task: |
  1. 要素收集：向用户要齐素材路径（视频/图片均可）与文案要素（素材路径、公司名、岗位名、3-4 条福利、投递方式）。用户给不全时按合理默认补齐并说明，不要反复追问。
  2. 生成 params.json（写入临时目录，不要散落到工作区根目录），字段模板见下。
  3. 出片：`"$PY" "$ENG\engine\cli.py" compose recruit <params.json> -o <输出目录>`，读取返回 JSON 拿 video/cover 路径。
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

## 配音（TTS 旁白）提示词规范

**音色与语速**（params.tts[].voice 直接写中文名即可，引擎自动映射；rate 如 "+10%" 提速 / "-5%" 放慢）：
- 本场景推荐：**晓伊**（女声·温柔）或 **云枫**（男声·磁性）｜语速 `+0%`

**口播文案写法（提示词三原则，写给用户的文案也按这个改）**：
1. **每句 ≤ 12 字，一句只说一个信息点**——TTS 长句会拖节奏、糊掉重拍；
2. **口语化**：把书面词换成说人话（「位于」→「就在」、「提供」→「给你」、「即刻」→「马上」）；
3. **钩子句式**：反差 / 悬念 / 数字（「这家店，本地人都在排队」「88 元吃垮火锅店」）。

像跟朋友聊天：福利句具体不空洞（「下午 3 点水果自由」优于「福利待遇优厚」）；投递 CTA 一句话讲清动作（「简历发到 xxx@xx.com」）。

**params.tts 写法与时间点计算**：
```json
"tts": [
  {"text": "原价158，团购88", "start": 12.4, "voice": "云希", "rate": "+0%", "volume": 1.0}
]
```
- `start` = 卡片**完全可见**的时刻（秒）≈ 前面各段 `dur` 累加 − 转场重叠累计；拿不准就比卡片出现早 0.2s，宁早勿晚；
- 人声永远 duck=False 盖过 BGM（引擎已内置，params 里不用管）；
- 全片旁白建议 ≤ 4 句：旁白是佐料不是主菜，大字卡才是主视觉。

## 音乐 / 音效关键环节

**BGM**（导演已内置默认，params 可覆盖）：
- 本场景默认：`lofi / volume 0.28`（松弛真诚，雇主品牌调性）
- 覆盖写法：`"bgm": {"style": "jazz", "volume": 0.28}`；可用风格：`lofi / ambient / electronic / cinematic / jazz / ambient_pad / upbeat`；
- 音量档位铁律：**0.2~0.35 之间**，探店/节日可到 0.34，知识/招聘类压到 0.26~0.28。

**EPIC 能量轨**（可选，重节奏段专用）：`"epic": {"start_seg": 第几段起, "bpm": 150, "volume": 0.85}`，接管后 BGM 自动压到 0.2；短平快探店片一般不用。

**音效节拍表（关键环节必配，导演自动落点，无需手写）**：
| 环节 | 音效 | 时机 | 音量 |
|---|---|---|---|
| 印章砸落（价格/信任/CTA 章） | thud | 印章出现 +0.05s | 0.6~0.65 |
| 情绪大字弹入 | pop | 弹入帧 +0.02s | 0.5~0.55 |
| 段落转场 | whoosh / click | 切换点 | 0.45 |
| 福利卡弹出 | pop | 弹入帧 +0.02s | 0.5 |

**混音三铁律**：
1. 同一秒内**最多 1 个重音效**（thud/riser 级），否则糊成一团；
2. riser 必须**提前 0.8~1.2s** 起蓄力，落点正好砸在印章/大字出现帧；
3. 音效音量 0.45~0.65 分档：爆点 0.6+、节奏点缀 0.45~0.55，永远低于人声。


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
