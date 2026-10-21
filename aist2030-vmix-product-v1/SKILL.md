---
id: aist2030-vmix-product-v1
name: AIST2030 产品商品混剪
displayName: AIST2030 产品/商品发布混剪
slug: aist2030-vmix-product-v1
module: 创作类
version: 1.2.0
internal_version: v1.2
owner: AIST2030
author: 贵州省团之家智付科技有限公司
source: 自建
pricing:
  model: free
  amount_fen: 0
capability: 产品发布级混剪：hero 主视觉→功能特性大字逐条闪出→价格/权益盖章卡→行动号召收尾；electronic BGM + EPIC 能量轨 + pop 音效，硬切动效咬合重拍。零积分、素材不出本机。
description: 输入：产品实拍/渲染图 + 卖点清单 + 价格权益。输出：横版或竖版成片 MP4 + 可选封面。适用：产品发布会、新品上市、商品介绍、功能演示；不适用：到店服务（用 vmix-local）。
role: 产品发布导演：把卖点清单编排成节奏化特性卡序列，价格与权益用盖章强调。
context: |
  - 引擎根目录：${CHATCUT_HOME}（下称 $ENG），解释器 ${CHATCUT_PY}，依赖已装好，无需激活。
  - 统一入口：`"$PY" "$ENG\engine\cli.py" compose <scenario> <params.json> -o <输出目录>`；输出 JSON {"video": "...", "cover": "..."}。
  - 若本机已接入 chatcut-lite MCP（工具 chatcut_compose / chatcut_scenarios），优先用 MCP 等价调用，二者行为一致。
  - 零积分、零 API 费用、素材不出本机；ffmpeg 用引擎 vendor 完整版（自动选择，无需配置）。
  - 大字/印章/白闪是"综艺感"硬切动效，禁加缓动；文字排版位置由 params 指定，不要当底部字幕用。
  - 视频号封面为 1080×1260 竖版（params.cover 传入才生成）。
  - 文案合规：遵守 PRC 广告法，禁用「领先/最佳/革命性/唯一」等绝对化用词；探店/带货类内容建议 honest 标注合作关系。

  params.json 字段模板：
    {"name":"新品发布","hero":[{"src":"主视觉","dur":3.5}],
     "hook":[["重新定义", 120, [255,255,255,255]],["XX 体验", 80, [255,214,110,255]]],
     "features":[{"src":"特性镜头","cap":[["特性一句话", 64, [255,255,255,255]]],"dur":2.6}],
     "price":{"now":"首发价 ¥999","seal":[["限时", 56],["首发", 56]]},
     "cta":{"title":"立即预订","lines":["官网 / 旗舰店"]},
     "outro":[["所见即所得", 90, [255,214,110,255]]],
     "out":"成片.mp4"}
task: |
  1. 要素收集：向用户要齐素材路径（视频/图片均可）与文案要素（素材路径、产品名、3-5 条卖点、价格/权益、行动号召）。用户给不全时按合理默认补齐并说明，不要反复追问。
  2. 生成 params.json（写入临时目录，不要散落到工作区根目录），字段模板见下。
  3. 出片：`"$PY" "$ENG\engine\cli.py" compose product <params.json> -o <输出目录>`，读取返回 JSON 拿 video/cover 路径。
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
- 本场景推荐：**云希Pro**（男声·专业）或 **晓晓**（女声·亲和，消费品）｜语速 `+5%`

**口播文案写法（提示词三原则，写给用户的文案也按这个改）**：
1. **每句 ≤ 12 字，一句只说一个信息点**——TTS 长句会拖节奏、糊掉重拍；
2. **口语化**：把书面词换成说人话（「位于」→「就在」、「提供」→「给你」、「即刻」→「马上」）；
3. **钩子句式**：反差 / 悬念 / 数字（「这家店，本地人都在排队」「88 元吃垮火锅店」）。

特性句用「数字+对比」：不是「很快」，是「3 秒出结果」；价格句与探店同款锚点法。

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
- 本场景默认：`electronic / volume 0.30`（脉冲推进，科技感）
- 覆盖写法：`"bgm": {"style": "jazz", "volume": 0.28}`；可用风格：`lofi / ambient / electronic / cinematic / jazz / ambient_pad / upbeat`；
- 音量档位铁律：**0.2~0.35 之间**，探店/节日可到 0.34，知识/招聘类压到 0.26~0.28。

**EPIC 能量轨**（可选，重节奏段专用）：`"epic": {"start_seg": 第几段起, "bpm": 150, "volume": 0.85}`，接管后 BGM 自动压到 0.2；短平快探店片一般不用。

**音效节拍表（关键环节必配，导演自动落点，无需手写）**：
| 环节 | 音效 | 时机 | 音量 |
|---|---|---|---|
| 印章砸落（价格/信任/CTA 章） | thud | 印章出现 +0.05s | 0.6~0.65 |
| 情绪大字弹入 | pop | 弹入帧 +0.02s | 0.5~0.55 |
| 段落转场 | whoosh / click | 切换点 | 0.45 |
| 特性卡切换 | click | 每张卡出现帧 | 0.45 |

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
