---
id: aist2030-dev-windows-local-media-pipeline-v1
name: AIST2030 本地媒体处理流水线
displayName: AIST2030 本地媒体处理流水线
slug: aist2030-dev-windows-local-media-pipeline-v1
module: 开发类
version: 1.0.0
owner: AIST2030
source: 自建
author: 贵州省团之家智付科技有限公司
role: windows-local-media-pipeline 执行助手，擅长在 开发类 场景下按标准流程完成任务交付。
context: 用户输入与素材，经本技能流程处理后产出目标结果；已知约束见 constraint 与边界说明。
task: 将用户关于「windows-local-media-pipeline」的需求转化为标准化交付物，遵循 quality_gate 与 constraint。
format: 结构化结果 + 必要的过程说明，可直接被下游技能或用户消费。
constraint: 仅处理本技能职责范围内的任务；涉及外部密钥/支付/合规时须显式向用户确认；不越权调用其他系统。
quality_gate: 交付前自检：必填字段完整、产出可用、边界清晰、无越权行为。
anti_dup: 与同类 开发类 技能互斥，按语义匹配唯一触发，避免重复执行。
input_schema: 用户需求描述 / 必要素材（链接、文件、参数）。
output_schema: 标准化交付物 + 状态回显（成功 / 失败原因）。
capability: 提供「windows-local-media-pipeline」能力：所有结论均在 Windows + Python 3.13 + Pillow
  12 + numpy 2 环境实跑验证（2026-09）。，按既定流程交付结果，适用 开发类 场景。
description: 输入：所有结论均在 Windows + Python 3.13 + Pillow 12 + numpy 2 环境实跑验证（2026-09）。
  相关需求或素材。 输出：按本技能流程产出的结果与可交付物。 适用边界：仅当用户明确需要「windows-local-media-pipeline」能力、且属于
  开发类 场景时调用；不属于本技能职责的需求应交由其他技能处理。
tags:
- tts
- ffmpeg
- video
- pipeline
- windows
pricing:
  model: per_call
  amount_fen: 1
---

# Windows 本地音视频合成流水线（Python）

所有结论均在 Windows + Python 3.13 + Pillow 12 + numpy 2 环境实跑验证（2026-09）。
凡标「实测」的，都有对应复现脚本；标「推测」的不要当结论用。

---

## 0. 一句话选型（照抄即可）

| 环节 | 用什么 | 不要用什么 |
|---|---|---|
| PPT/Office → 页面图 | **WPS COM `KWPP.Application`**（本机已装，最稳）> LibreOffice CLI > PowerPoint COM | 不要试图纯 Python 还原 PPT 版式 |
| 文本 → 语音（在线） | **edge-tts**，`await comm.save(path)` | 不要 `await comm.save_sync()` |
| 文本 → 语音（离线） | **pyttsx3**，输出认命用 `.wav` | 不要把它的输出命名成 `.mp3` |
| 图+音 → 视频 | **直接 subprocess 调 ffmpeg** | **绝对不要 moviepy 1.0.3** |
| 随包 ffmpeg 二进制 | `imageio-ffmpeg` 的 `get_ffmpeg_exe()` | 不要让用户自己装 ffmpeg |
| 水印 | **Pillow 预渲染 RGBA 图层 + alpha_composite**（主）/ `drawtext`（备） | 不要固定白色半透明 |
| 多段拼接 | 逐页生成同参数分段 → `concat` 解复用器 `-c copy` | 不要用 moviepy 的 `concatenate_videoclips` |

---

## 1. 致命坑（每条都真的会挂）

### 1.1 `await communicate.save_sync()` → TypeError
`edge-tts` 的 `Communicate` 有两个相近方法：

- `save(audio_fname)` —— **协程**，必须 `await`
- `save_sync(audio_fname)` —— **同步方法，返回 None**

把它们写反（在网络教程里极其常见）会得到：
```
TypeError: object NoneType can't be used in 'await' expression
```
正确写法：
```python
async def synth(text, out):
    import edge_tts
    comm = edge_tts.Communicate(text, voice="zh-CN-YunyangNeural", rate="+20%")
    await comm.save(out)          # ← 不是 save_sync
```
自检：`inspect.iscoroutinefunction(edge_tts.Communicate.save)` 应为 `True`。

### 1.2 pyttsx3 输出**恒为 WAV**，扩展名说啥都没用
Windows 上 pyttsx3 走 SAPI5，`engine.save_to_file(text, "x.mp3")` 落盘的内容头部是 `b'RIFF'`
（即 WAV）。后续用任何按扩展名判定的解码器读它都会失败。

**规则：离线分支的文件名一律用 `.wav`**，让 ffmpeg 去兼容格式差异（ffmpeg 不靠扩展名）。

### 1.3 moviepy 1.0.3 已经死了（Pillow ≥ 10）
`moviepy/video/fx/resize.py` 里写死 `Image.ANTIALIAS`，而该常量在 **Pillow 10 被移除**：
```
AttributeError: module 'PIL.Image' has no attribute 'ANTIALIAS'
```
`.resize()` 直接挂，`concatenate_videoclips(method="compose")` 内部也走这条路，一起挂。
再加上 moviepy 1.0.3 与 numpy 2.x 的历史兼容问题——**别再挣扎，换掉**。

替代方案：直接调 ffmpeg 做「静帧图 + 音频 → 分段视频」，再 `concat -c copy` 拼接。
更快（几倍）、内存占用低得多、不受 Python 生态版本变化影响。

### 1.4 ffmpeg `drawtext` 的字体路径：Windows 盘符冒号**必须转义**
`fontfile='C:/Windows/Fonts/msyh.ttc'`（裸冒号）会报：
```
No option name near '\Windows\Fonts\msyh.ttc:text=...'
```
因为 `:` 是 ffmpeg 滤镜的参数分隔符，它把 `C` 当成了选项名。

实测通过的四种写法（任选）：
```python
# A. 转义冒号（推荐，路径可读）
"drawtext=fontfile='C\\:/Windows/Fonts/msyh.ttc':text='AIST2030':..."
# B. 反斜杠路径 + 转义冒号
"drawtext=fontfile='C\\:\\\\Windows\\\\Fonts\\\\msyh.ttc':..."
# C. 把字体拷到工作目录，用相对路径 + subprocess cwd=（最省事）
"drawtext=fontfile=msyh.ttc:text='AIST2030':..."
```
其他要点：
- `fontsize=h/8` 这类**表达式可用**（不必写死像素）
- 中文用 `msyh.ttc` 渲染正常，不会出豆腐块
- 走 `subprocess.run([...])` 传 list 参数，不要拼 shell 字符串

### 1.5 水印固定「白色 30% 透明」在白底内容上等于隐形
屏录视频背景颜色杂，白色半透明水印没问题；但 **PPT/文档页面大多是白底**，
白色 30% 水印肉眼几乎不可见 —— 等于免费版根本没加水印。

**正解：按底色自适应配色。**
```python
from PIL import ImageStat
def center_luma(img):                      # 取中心区域平均亮度
    w, h = img.size
    box = (int(w*.15), int(h*.25), int(w*.85), int(h*.75))
    return ImageStat.Stat(img.convert("L").crop(box)).mean[0]

on_light = center_luma(base) > 140         # True → 用深色水印
```
配色规则：亮底用深色填充 + **白色描边**；暗底用白色填充 + **深色描边**。
描边是保证「任何底图上都可辨」的关键，别省。

**加粗 + 淡显的配方（用户偏好的观感）**：字体用 **微软雅黑 Bold**（`msyhbd.ttc`，
找不到再退回 `msyh.ttc`），中心主水印 `opacity≈48/255`、描边像素宽度
`max(2, 高度*0.0035)` 四向偏移叠画；右下角小标 `opacity≈78+90`。
「加粗」让淡水印仍有形体感，「淡显」保证不抢主体 —— 只加透明度不加粗，
白底上会糊成一片看不见的灰。

---

### 1.6 TTS 读错多音字（「行业」读成 xíng yè）—— 用**同音字替换**，不要用 SSML

中文 TTS 默认读音对多音字错误率很高，听众第一耳就能听出来
（「行业/银行/重庆/长大/断更/同行」）。

#### ⛔ 先排除错误方案：SSML `<phoneme>` 在 edge-tts 上**根本走不通**

网上普遍推荐的写法是塞 `<phoneme alphabet="sapi" ph="hang 2">行</phoneme>` +
`<speak>` 包裹。**实测无效**，而且失效方式很隐蔽 —— 标签会被**逐字朗读出来**，
用户听到的是「Big version 等于 10 XMLNS 等于 HTTP 冒号斜杠斜杠 3W 点…」。

根因在库内部（2026-09 实测，edge-tts 7.x）：

```python
# edge_tts/communicate.py
self.texts = split_text_by_byte_length(
    escape(remove_incompatible_characters(text)), 4096)
```

`escape()` 会把输入里所有 `<` `>` `&` 转成实体，**你的标签必然变成普通文本**。
该库不接受自定义 SSML（`pyttsx3`/SAPI5 同样不透传 XML）。

**最坑的是它会伪装成成功**：合成不报错、有音频、日志显示「+多音字已生效」——
只有人耳听得出来。所以「加个注音标签」这种改法必须配一条能自动抓出它的断言（见下）。

#### ✅ 正确方案：同音字替换（只改字，不改声音）

把「上下文可确定、且与默认读音不同」的多音字，换成**同音同调**的常用单音字：

| 原文 | 替换 | 读音 |
|---|---|---|
| 行业 | 航业 | háng |
| 重新 | 虫新 | chóng |
| 断更 | 断耕 | gēng |
| 什么 | 神么 | shén |
| 下载 | 下再 | zài |
| 应用 | 硬用 | yìng |

- **在线 / 离线两个引擎通吃**（不依赖任何 SSML 能力）；
- **替换文本只喂给 TTS，不写进画面** —— 视频画面是 PPT 栅格化的位图，
  所以「断更→断耕」用户既看不见也听不出差别，纯粹用于纠音；
- 词表 `[{word, char, ph, alt}]` 随包放 `resources/heteronym.json`。

#### 词表卫生（每一条都是踩过的坑）

1. **替代字必须有「单一读音」白名单**：维护 `{替代字: 读音}` 表，
   `alt` 不在表里、或读音对不上 → **整条规则丢弃**。否则编辑词表时塞进一个
   多音字，反而改出新的错读。
2. **绝对禁止单字词条**（如 `("传","传","zhuan4","赚")`）：那会把文中**所有**
   「传」都改成「赚」，包括「传递/传统」。单字级的多音判断只能交给人工审校。
3. **长词优先 + 位置占位去重**：按词长降序遍历、命中位置打 `taken` 标记，
   否则「银行家」会被「银行」+「行家」重复处理。
4. **只收录「默认读音就是错的」条目**，默认读音本来就对的词不做任何改写 ——
   无收益的改写只会引入新风险。
5. **词表异常一律吞掉、原样返回**：不能因为一条烂词条让整段配音失败。

#### 词表再全也会漏 —— 第二道关：人工审校

行业词、新词、专有名词永远收不全。上线后必然收到「XX 又读错了」的反馈，
所以要把人接进流程：「读取文案 → 自动匹配多音字多读音 → 展示推荐读音 →
用户逐条确认 → 按锁定读音合成」。

设计要点（决定这功能会不会被当成负担）：

- **每行默认值就是推荐值，用户只改读错的**，其余不用碰 ——
  「确认」按钮在任何情况下都可直接点，等价于「全部采用推荐」。零成本通过。
- **按来源分级**，别把 200 个候选平铺给用户：
  `ambiguous`（两种读法都成立，如「同行」tóng háng/xíng，必须人选）
  > `default`（词表未收录，机器最易错）
  > `builtin`（已自动纠好，默认折叠）。
- **用户的选择用「位置级 overrides」传给合成层**，不要改原文：
  `{页号: {页内字符位置: 读音}}`，位置索引**必须与扫描时同一份文本口径**
  （同一取文本规则：有备注用备注、否则用正文），否则锁定会打偏。
- **「记住我的选择」只收词组级规则**（`同行者→xíng`），单字选择一律不写词表。
- 有的读音**找不到同音单音字**（如 `gèng` 只有「更/亘」），要显式标 `⚠` 并
  优雅降级为「保持原字」，不能假装改了。
- 改了用户词表要**立刻失效缓存**（按文件 mtime+size 做指纹），
  否则用户刚记住的读音这次不生效，得重启软件。

#### 🩸 铁律：界面上展示为「推荐值」的东西，必须真的能落地

真实事故（2026-09-21 用户反馈「标注了多音字还是没按标注读」）：
歧义词表（`{词: (多音字, [读音…])}`）**只被审校界面用来展示候选，从未参与改写**。
于是出现最尴尬的一幕 —— 界面把「同行」推荐成 háng（正确），
用户一看推荐没错就**没去动它**，而「未改动 = 不写入锁定表」的设计
又让锁定表为空，自动层里也没有「同行」这条规则（它只在歧义词表里）
→ 原文原样送进 TTS → 依旧读 tóng xíng。**用户看到的推荐和实际输出是两回事。**

修法与推广规则：

1. **凡是「推荐值」，都必须有一条代码路径真的执行它**；界面上呈现的默认行为
   必须等于后台的默认行为。做不到就别在界面上写成「推荐」。
2. **「未改动就不传」这个优化会放大上面这个 bug**：它默认「后台已经会这么做」。
   只要后台的默认 ≠ 界面显示的默认，用户不改就等于没生效。
   因此：**歧义词表的推荐值必须由合成层直接执行**（长词优先），
   人工锁定 > 人工词表 > 歧义推荐 > 读音包 的优先级顺序固定下来。
3. **改不了的要留痕**：用户选了一个找不到同音替代字的读音时，
   别静默 no-op，要记一条 `skipped=True` 并在日志/引擎标签里写明
   「N 处所选读音无同音字、无法强制改写」—— 无声失败正是这条 bug 的另一半。
4. 顺带教训：**两字词做歧义条目要极谨慎**。「一行」既进不了「一行人(yī xíng)」
   也切不开「一行字(yī háng)」，推荐值必然冤枉一半 —— 这类应该删掉，
   把确定的那半边（「一行人」）放进确定词表。

#### 兜底型功能：默认关闭，且**改默认值必须换设置键名**

逐条确认类界面（人工审校）**默认关闭**更合理：自动层已覆盖大多数情况，
默认弹出会让每个用户都付出确认成本；它的正确定位是
「出片后发现读错 → 打开它 → 改那一处 → 重出」。

⚠️ 改默认值时**必须换配置键名**（`heteronym_review` → `heteronym_review_on`）：
老用户配置文件里存着旧默认值 `true`，沿用老键名会让「改默认」对他们**完全无效**，
而且这类「我改了但没生效」极难排查。`load()` 里用一个 `_LEGACY_KEYS` 元组丢弃旧键。

#### 读音包（pypinyin）做「组词判定」—— 可行，但必须戴四道镣铐

用户会问「能否直接抓多音字读音包，靠前后字组词判定读音」。可以，就是
`pypinyin`（MIT / 纯 Python / 离线，`phrases_dict` 约 4.7 万条词组），
但**直接调用它的结论会大面积读错**，四条硬规则缺一不可：

1. **不要用 `pypinyin.pinyin()`，要自己按 `phrases_dict` 做最长匹配。**
   `pinyin()` 在没命中词组时会**退回它自己的单字默认音**，那不是「组词判定」，
   是噪声。实测代价：`弹窗→dàn chuāng`（错，应 tán，一篇文档 11 处）、
   `调参数→diào`、`恒为纯 ASCII→wèi`。自己匹配词典 = 没命中就一个字都不动。
   （顺带：`pinyin()` 的返回列表**不与原串等长**，数字/英文/标点会被合并成一段，
   拿列表下标当字符位置会整体错位，锁定读音就会打到别的字上。）
2. **前向 + 后向最大匹配，双向一致才采纳。**
   单向贪心会从真实词中间起算：`我们在行业中行走` → 词典里有生僻词「中行」
   （zhōng háng，银行缩写）→ 把「行走」的「行」抢判成 háng。
   反向再扫一遍时「行走」判 xíng，两向不一致 ⇒ 该位置处于词边界争议区 ⇒ 放弃。
   代价是漏掉少数有争议的词，换来「绝不把对的读错」。
3. **读数必须落在你自己人工核对过的候选读音表内**，且**与默认读音不同**，
   且**有可用的同音替代字**。三条件同时满足才改。
4. **同形异音词黑名单**（双向一致也挡不住，只能逐条封）：
   `都会`（词典 dū huì「大城市」↔ 文案 dōu huì「全都会」）、
   `外传`（wài zhuàn 人物外传 ↔ wài chuán 请勿外传）、
   `部分`（词典 fèn ↔ 口语 fēn）、`行都`（跨词误命中）、`在行`。
   **新增例外前必须跑审计脚本用真实语料确认，别凭感觉封。**

配套工作流（缺了它这层就是定时炸弹）：写一个
**语料驱动的审计脚本**，把项目里所有中文文档+源码注释切句跑一遍，
按「命中的词 + 多音字 + 读音 + 上下文」去重列出来，**逐条人工过目**。
分层设定能配上这个审计，才敢把「机器自动改文案读音」上线。

#### 验收方法（关键：要能自动抓出「标签被念出来」）

1. **时长自校准** —— 最省事的自动断言：同一段文本，分别用「纯文本」和
   「校正后文本」合成，比较时长比，**必须落在 0.7–1.3**。
   标签被念出来会让时长暴涨（实测 5.78s vs 5.76s = 0.997 才算正常）。
   这条不依赖人耳，能进 CI。
2. **词表卫生断言**：所有 `alt` 在白名单内 / 无单字词条 / `char in word` /
   读音格式已归一化。
3. **位置精确断言**：`text[hit.index] == hit.char` —— 位置错一位锁定就打偏。
4. **overrides 优先级断言** + **非法输入不崩**（越界、非数字键、非法读音）。
5. **冻结包实证**：跑真 exe 读 `--core-cli engines` 的 heteronym 段，
   确认 `rules` 数量和 `frozen=true`（避免打包漏掉词表导致静默失效）。
   若引入了第三方读音包，还要让 `engines` 输出一个 `xxx_ready` 布尔字段 ——
   **第三方包打包漏掉时的表现是「静默降级」（少一层纠音），没有这个字段根本发现不了**。
   该自检脚本要**接受可选 exe 路径参数**，这样才能在部署到 dist **之前**先验新构建。
6. **反例断言是这类功能的主体**：自动改写类的回归脚本里，
   「不该改的一个都不许动」的断言要比「该改的改对了」更多。
   （实例：`每行都已填好`（词典僻词「行都」）、`都会自动重启`、`请勿外传`、
   `部分内容`、`在行`、`总行/支行`、`一行字`、`调整参数` 全部必须保持原样。）
7. **生产语料审计**（见上文审计脚本）：输出给人看、逐条过目，
   新加的改写规则必须先过审计才能上线。

### 1.7 音频参数「一路传到底、最后一米被丢弃」（最隐蔽的一类 bug）

**症状**：界面上调音量/音调/语速，**试听有效、成片完全无效**。用户不会报「参数没生效」，
只会说「感觉不太好听」——因为听起来确实像"档位不够"。

**根因模式**：调用链每一层都"看起来通了"——参数被 CLI 接收 ✅、被写进日志 ✅、
被一路透传到最外层函数 ✅，但最外层函数**收到后从未用它**。
（实例：`compose(volume=2.0)` 签名里有 `volume`，函数体里却没传给单段合成函数
`_segment()`，参数被静默吞掉。整条链上没有任何一处报错。）

**排查铁律：不要靠「读代码确认参数被接收」，要靠「测量输出」。**

```bash
# 音量：跑两个相差很大的档位，比响度。相同 = 参数没生效
ffmpeg -i out.mp4 -af volumedetect -f null - 2>&1 | grep mean_volume
#   修复前：--volume 0.5 与 --volume 3.0 同为 -26.6 dB  ← 实锤
#   修复后：-32.8 / -21.6 / -19.3 dB（单调递增）
```
```bash
# 音调：比过零率/频谱重心（不用耳朵，能进 CI）
ffmpeg -i out.mp4 -af astats=metadata=1:reset=0 -f null - 2>&1 | grep "Zero crossings rate"
#   -30Hz → 0.0998 ｜ 0 → 0.1187 ｜ +30Hz → 0.1316（单调 = 音高真的变了）
```

**参数真正落到 ffmpeg 时的正确音频链顺序**（`-af`，用逗号连）：
`volume=<倍数>` →（倍数 >1 时）`alimiter=limit=0.98:level=0` → `apad=pad_dur=<秒>`
- 放大后峰值会越 0dB **削顶**，必须补前视限幅器；`level=0` 关掉自动增益，
  否则它会顺手把安静段抬起来、破坏原始动态（听感变"糊"）。
- `apad` 用来做**换气停顿**（页与页 / 句与句之间的静音留白）。
  与 `-loop 1` 的静帧图输入 + `-shortest` 配合：输出时长 = 音频（含 pad）时长。
  微验证（不依赖整条管线，最省事）：
  ```python
  _segment(img, audio_2s, out0, size, "mp4", pad_sec=0.0)   # → 2.02s
  _segment(img, audio_2s, out1, size, "mp4", pad_sec=0.5)   # → 2.52s  ✅
  ```

**顺带两个必须做的配套**（否则用户仍会踩坑）：
- **试听与成片必须走同一套参数**。试听走 `tts.synth()` + ffmpeg 音量，成片走
  `cli → compose → _segment`；漏掉任何一边，就会出现"试听是好的、出片不对"。
- **在线合成失败要重试再降级**。旧行为是第一次失败就直接降到离线系统音，
  整条视频音色突变而用户无从察觉；改成重试 3 次、退避 0.8/1.6s 后再降级。
- **改默认值时要防老配置覆盖**：新增的键（如 `pitch`）要在 DEFAULTS 里给默认值，
  老配置里没有该键时才能吃到新默认。

---

## 2. Office 页面栅格化（引擎门控）

PPT/Word 转图片**必须**借助本机办公软件，纯 Python 无法忠实还原版式。
采用「检测到才启用」策略，按优先级降级：

1. **WPS**（`KWPP.Application` / `KWSS.Application`）—— 实测最稳
2. **LibreOffice**（`soffice --headless --convert-to pdf` → pypdfium2 栅格化）
3. **Microsoft Office**（`PowerPoint.Application`）

WPS COM 关键调用（实测可用）：
```python
import win32com.client as wc
app = wc.Dispatch("KWPP.Application")          # 用标准 Dispatch，不要 dynamic.Dispatch
try:
    app.Visible = False                        # WPS 常对这个报错，用 try/except 吞掉
except Exception:
    pass
pres = app.Presentations.Open(path, WithWindow=False)
sw, sh = float(pres.PageSetup.SlideWidth), float(pres.PageSetup.SlideHeight)
# ★ 可以指定输出像素尺寸，做高清导出
pres.Slides(i).Export(out_png, "PNG", target_w, target_h)
# ...
finally:
    pres.Close(); app.Quit()                   # 必须 Quit，否则残留孤儿进程
```

**打包必备**：`hiddenimports` 里要显式加
`win32com`、`win32com.client`、`win32com.client.dynamic`、`pythoncom`、`pywintypes`，
否则冻结后 COM 导入失败直接闪退。

**内核子进程不要启用 faulthandler**：COM 收尾时 Windows 会抛一次性的
`0x800706BA` / `0x800706BE`（RPC 服务端已退出），默认由 Windows 静默处理、进程能继续跑，
但 faulthandler 会把它误记成致命异常写进崩溃日志，造成「没崩却写崩溃日志」的假象。

---

## 3. 分辨率「自适配内容比例」的正确算法

需求常写成「视频比例自动适配源文件比例」。若写死 `{'720P':(1280,720),'1080P':(1920,1080)}`，
4:3 的内容只会被加黑边居中 —— 那是 letterbox，不是自适配。

正解：**预设定义「短边」，长边按内容比例反推**。
```python
RESOLUTIONS = {"720P": 720, "1080P": 1080, "2K": 1440}

def compute_target(ratio, preset):
    short = RESOLUTIONS[preset]
    if ratio >= 1:                 # 横版：短边是高
        h, w = short, round(short * ratio)
    else:                          # 竖版：短边是宽
        w, h = short, round(short / ratio)
    return (w - w % 2, h - h % 2)  # ★ h264 要求偶数，必须取偶
```
效果：16:9 的 1080P → 1920×1080；4:3 的 1080P → 1440×1080；9:16 的 720P → 720×1280。
零拉伸、零黑边。

分段编码（静帧图 + 音频，时长以音频为准）：
```
ffmpeg -loop 1 -framerate 25 -i slide.png -i audio.wav
  -vf "scale=W:H:force_original_aspect_ratio=decrease,
       pad=W:H:(ow-iw)/2:(oh-ih)/2:color=black,setsar=1,format=yuv420p"
  -c:v libx264 -preset veryfast -crf 20 -pix_fmt yuv420p -r 25
  -c:a aac -b:a 160k -ar 44100 -ac 2 -shortest
  -movflags +faststart seg_001.mp4
```
拼接 = 写 `concat_list.txt`（`file '绝对路径'`，路径反斜杠换正斜杠）后
`-f concat -safe 0 -i list.txt -c copy -movflags +faststart out.mp4`。
同参数分段可**无损流拷贝**，几十页也很快。

---

## 4. ffmpeg 二进制的分发与许可证合规

`imageio-ffmpeg` 提供 `get_ffmpeg_exe()`，随 wheel 带一个 ffmpeg 二进制，免用户自行安装。
定位优先级建议写成：随包内置 → 环境变量 → 系统 PATH → imageio-ffmpeg。

⚠️ **它的默认构建是 GPLv3**（实测 `--enable-gpl --enable-version3`，含 libx264/libx265）。

| 场景 | 判断 |
|---|---|
| 免费/内部使用 | 独立进程 + 命令行调用属**聚合分发**，一般不传染自有代码。仍需随包保留许可证全文 + 提供对应源码获取途径声明 |
| 闭源商业售卖 | 换 **LGPL 构建**（如 BtbN 的 `...-lgpl` 系列） |

**务必把编码器降级链写进代码**，这样换构建不用改代码：
```python
_PREFERENCE = ["libx264", "h264_mf", "libopenh264", "libx265", "mpeg4"]
# 用 `ffmpeg -encoders` 解析可用列表，依次取第一个命中的
```
`h264_mf` 是 Windows Media Foundation 自带编码器 —— LGPL 构建下没有 libx264 时它是首选，
无额外授权费。注意参数差异：x264 用 `-preset/-crf`，`h264_mf` 用 `-b:v`。

另：H.264 本身涉及专利池授权，是行业普遍现实问题；小规模分发通常无实际影响，上量前建议法务确认。

---

## 5. 语速换算（产品上按「字/秒」说话，底层按百分比/词速说话）

用户心智是「2.8 字/秒」，但两个引擎都不吃这个单位。

```python
_BASE_CPS = 4.5                                  # edge-tts 默认语速 ≈4.5 字/秒
def cps_to_edge_rate(cps):                       # → "+20%"
    return f"{(cps / _BASE_CPS - 1) * 100:+.0f}%"

def cps_to_pyttsx_rate(cps):                     # → SAPI words-per-minute
    return max(80, min(320, round(cps * 60 / 1.68)))   # 中文≈1.68 字/词
```
`_BASE_CPS` 建议实测校准一次，不同音色略有差异。

**网络探测别用 ping 百度**，探测真实端点更准：
```python
socket.create_connection(("speech.platform.bing.com", 443), timeout=3)
```
并且降级逻辑做成「先试在线、捕获异常再走离线」，比「先探测再决定」更健壮
（探测成功但合成失败的情况真实存在）。

---

## 6. 本机环境坑（这台机器特有）

- **pip 不能用清华镜像**：`-i https://pypi.tuna.tsinghua.edu.cn/simple` 会返回
  `Could not find a version that satisfies the requirement X (from versions: none)`，
  而网络本身是通的（`pypi.org` / 镜像 HEAD 都 200）。**用默认 PyPI 源即可。**
- **PowerShell 重定向是 UTF-16**：`& cmd *> x.log` 写出的文件用 Read 会判成 binary。
  需要 UTF-8 文本证据时，**用 Python 脚本 `subprocess` 捕获后 `write_text(encoding="utf-8")`**。
- **Bash 工具的 shim 缺 `dirname`/`head`**，`ls`/`glob` 在大目录会超时。
  文件探查优先用 PowerShell（`Get-ChildItem -Depth`）。
- **Python 脚本 print 到 PowerShell 管道会因 GBK 抛 `UnicodeEncodeError`**：
  子进程 stdout 默认按控制台代码页 936(GBK) 编码，含 emoji 或非 GBK 字符的
  `print` 会直接崩掉整个验收脚本。**验收脚本开头务必加**
  ```python
  sys.stdout.reconfigure(encoding="utf-8", errors="replace")
  sys.stderr.reconfigure(encoding="utf-8", errors="replace")
  ```
- **内核子进程的中文输出必须强制 UTF-8**（GUI 以子进程调 CLI 时同理）：中文 Windows
  代码页 936，不设 `PYTHONIOENCODING=utf-8` 时中文日志/路径按 GBK 写出，主进程按
  UTF-8 解码就变 `ҳ�浼��` 这种乱码。双保险做法：① CLI 入口对 stdout/stderr
  `reconfigure("utf-8")`；② JSON 结果行用 `json.dumps(..., ensure_ascii=True)`，
  恒为纯 ASCII，任何解码方式都不会错。

---

## 7. 验收套路（别只靠肉眼）

1. **抽帧对比**：`ffmpeg -ss T -i out.mp4 -frames:v 1 frame.png`，对浅底/深底内容各抽一帧，
   确认水印/字幕在两种底色下都可辨。
2. **客观指标兜底**：`ImageStat` 算全图均值与中心带标准差，白底页中心带标准差明显 > 0
   才说明水印真的印上去了（避免「看起来加了其实看不见」）。
3. **媒体流核对**：`ffmpeg -i out.mp4` 读 Duration / 编码 / 分辨率，确认比例与预设一致。
4. **冷热启动分开计时**：首次调用 WPS COM 要 100 秒量级，第二次只要十几秒。
   别用首次耗时去评估性能，也别把冷启动慢当成 bug。
