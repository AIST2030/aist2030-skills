---
id: aist2030-dev-drama-reedit-v1
name: AIST2030 短剧二创剪辑流水线
displayName: AIST2030 短剧二创剪辑流水线
slug: aist2030-dev-drama-reedit-v1
module: 创作类
version: 1.1.1
owner: AIST2030
source: 自建
author: 贵州省团之家智付科技有限公司
role: 把影视原片切成竖屏高光混剪成片，执行方负责帧级切点吸附、精确拼接、ASS 硬字幕与同步核验。
context: 输入本地短剧素材目录 + 高光时间码清单，输出 1080×1920 竖屏成片（含硬字幕、混音、响度归一化）。所有中间产物落盘可断点续跑。
task: 七阶段流水线（探测→切点图谱→EDL→拼接→画幅→字幕混音→核验），把「按秒硬切」升级为「帧级 + 语音边界吸附」，杜绝剪切吞台词与字幕音画不同步。
format: 成片 MP4 + edl.csv 剪辑清单 + qc_report.json 质检报告 + contact_sheet 抽帧联系表。
constraint: 仅处理本地已有素材；不下载、不代取网盘内容；不判断素材授权状态（著作权判断是使用者责任）；BGM 默认程序化生成以规避版权风险。
quality_gate: ①字幕无重叠 ②字幕-语音对齐 ③首尾不吞字 ④台词完整 ⑤抽帧无黑场 ⑥响度 -16±1.5 LUFS ⑦人工目视字幕压脸。
anti_dup: 与 aist2030-dev-doc2video-v1（文案直出视频）、aist2030-dev-ppt-motion-video-v1（PPT转视频）互斥，本技能只做「已有影视素材的重剪」。
input_schema: --raw 素材目录（mp4/mkv/mov）；--highlights 高光清单 JSON；--plan 成片配置。
output_schema: out/final.mp4（1080×1920@30, H.264+AAC, -16 LUFS）+ work/edl.csv + work/qc_report.json。
capability: 帧级切点吸附（VAD 语音边界，解决 BGM 素材无静音可切的问题）、all-intra + concat demuxer 零重编码拼接、FunASR 词级时间戳 ASS 硬字幕、五项同步核验闸门。
description: 输入：本地短剧/影视素材目录 + 高光时间码清单。输出：竖屏高光混剪成片，含帧级切点吸附、精确拼接、硬字幕、程序化 BGM、字幕-语音同步核验。适用边界：仅处理本地已有素材；二创授权判断由使用者负责。
tags:
  - video
  - ffmpeg
  - short-drama
  - subtitle
  - vertical
  - edl
  - asr
pricing:
  model: per_call
  amount_fen: 20
pay:
  protocol: skillpay-alipay-v1
  gateway: https://skillpay.alipay.com/api
  endpoints: [order/pre, pay, pay/complete, pay/complete/ack]
  insufficient_status: 402
  insufficient_header: Payment-Needed
  proof_header: Payment-Proof
  autopay: wallet
  idempotent: true
---

# 短剧二创剪辑流水线

把原片切成竖屏高光混剪成片（抖音 / 快手 / 视频号 9:16）。

核心能力：**剪切点不会拦腰截断台词，字幕不会与声音错位**。

---

## 0. 一句话选型

| 环节 | 用什么 | 不要用什么 |
|---|---|---|
| ffmpeg 定位 | `scripts/ffmpeg_env.py` 自动解析 | 不要让用户自己装 |
| 探测元数据 | 本项目 mini-probe（解析 `ffmpeg -i` stderr） | 本机**没有 ffprobe** |
| 台词识别 | **FunASR SenseVoice**（CPU 8.01% CER） | 不要用 faster-whisper（同体积差 2.7 倍） |
| 切点图谱 | **VAD 语音边界** ★ | 短剧有 BGM，`silencedetect` 会返回 0 条 |
| 剪切 | `-ss` 放 `-i` **之前** + 重编码 | 不要 `-c copy` 切原片（关键帧回退） |
| 拼接 | 同源 all-intra → **concat demuxer 零重编码** | 不要逐段重编码再拼（二次掉画质） |
| 字幕 | **ASS**（多位置/描边/逐词）+ `fontsdir` | 不要用 SRT；不要漏 fontsdir（中文变方块） |
| 响度 | 双遍 `loudnorm`，视频流 copy | 不要单遍（不准） |

---

## 1. 环境约束（本机实测 2026-10-17，务必遵守）

| 约束 | 事实 | 应对 |
|---|---|---|
| **C 盘仅剩 2GB** | torch+funasr 约 2-3GB | ASR 必须装 **E 盘独立 venv**，pip 也要 `--cache-dir` 指到 E 盘 |
| **无 ffprobe** | 只有 imageio 自带 ffmpeg 7.1 | 用 `ffmpeg_env.probe()` |
| **无独显** | `nvidia-smi` 无输出 | ASR 只走 CPU，别下 large 模型 |
| 模型缓存默认落 C 盘 | modelscope/HF 默认 `~/.cache` | 必须设 `MODELSCOPE_CACHE` / `HF_HOME` 指到 E 盘 |
| 无系统级 ffmpeg | — | `FFMPEG_BIN` 环境变量可覆盖 |

**ASR 环境自检**：

```bash
python scripts/asr_sensevoice.py     # 打印 "ASR 可用" 即可
```

---

## 2. 七阶段流程

### S1 素材探测 → `catalog.json` + `contact_sheet_ep*.jpg`

```bash
python scripts/stage1_probe.py --raw <素材目录> --work <工作目录> --shot-every 8
```

产出每集元数据 + **联系表**（每 8 秒一格带时间码标签）。
**联系表是人工挑高光的唯一依据** —— 看图报「第 X 集 第 Y 秒」。

### S2 静音图谱 → `silences.json`（辅助通道）

```bash
python scripts/stage2_silence.py --work <work> --noise -28 --min-dur 0.3 --sweep
```

`--sweep` 会对比多档阈值，帮你选参数。**别跳过它**：默认 -60dB 对真实素材必然返回 0 条。

### S2b 语音边界切点 → `cut_points.json` ★主通道

```bash
python scripts/stage2b_vad.py --work <work>
```

**为什么必须有这一步**：短剧原片自带持续 BGM，**全片几乎没有绝对静音**。
实测 ep01 在 -40/-35/-32dB 下静音段均为 **0 个**（-22dB 也只有 1 个）。
纯静音吸附在这种素材上会退化成强制硬切，台词必被腰斩。

VAD 判的是「**这一段有没有人在说话**」，BGM 铺底不影响判定。
台词段之间的换气间隙就是天然安全切点 —— **没人说话的地方切，不会吞字**。

### S3 高光定位 + 吸附 → `edl.csv`

```bash
python scripts/stage3_edl.py --work <work> --highlights highlights.json
```

```json
[
  {"ep": "ep01", "start": 96.0, "dur": 5.5, "note": "打脸"},
  {"ep": "ep03", "start": 42.0, "dur": 6.0, "note": "反转"}
]
```

三步走：
1. **秒 → 帧量化**（`round(t × fps)`），消灭浮点误差
2. 每个切点在切点图谱里找**最近的语音间隙**吸附
3. 吸附不到 → 标记 `FORCED` 并**显式告警**，绝不静默通过

`edl.csv` 含帧号与 HH:MM:SS:FF 时间码，**可直接人工编辑**，下游全读它。

### S4 切条 + concat → `rough.mp4`

```bash
python scripts/stage4_cut.py --work <work>
```

同源素材先转 all-intra（每帧 IDR）→ 任意点可 stream copy → concat 零重编码。
输出时长与 EDL 预期比对，差 >0.5s 报错。

### S5 画幅 + 调色去重 → `canvas.mp4`

```bash
python scripts/stage5_canvas.py --work <work> --level standard
```

统一输出 1080×1920。横屏源按人物重心裁切**不留黑边**；竖屏源直接归一。
去重三件套：分段色温微扰 + 关键帧微位移 + 镜像（详见 `references/dedup-compliance.md`）。

### S6 ASS 字幕 + BGM + 响度 → `final.mp4`

```bash
python scripts/stage6_subs.py --work <work> --out out/final.mp4 --bgm-style tense
```

★**最容易出错的环节：时间码重映射。**
多段来自不同集、顺序重排后，原 ASR 时间码**全部作废**。
公式：`成片时间 = 该段成片起点 + (台词原时间 − 该段原片入点)`
漏掉这步 → 字幕与声音完全错位，且「看起来字幕挺对」很难一眼发现。

竖屏字幕 `margin_v=320` 避开底部文案区与右侧点赞区。
BGM 默认程序化生成（零版权风险），音量 ≤ -22dB 不盖过人声。

### S7 核验闸门 → `qc_report.json`

```bash
python scripts/stage7_verify.py --work <work> --video out/final.mp4
```

| 检查 | 判据 |
|---|---|
| 字幕无重叠 | 区间重叠 >0.3s 报错 |
| 字幕-语音对齐 | 双向偏差 >150ms 告警 |
| 首尾不吞字 | 首条字幕 ≥ 音轨起点 |
| 台词完整 | EDL 覆盖台词数 vs 字幕条数 |
| 抽帧无黑场 | 灰度均值 <12 判黑场 |
| 响度 | -16±1.5 LUFS |

⚠ **模型判不了「字幕压不压脸」，必须人眼看抽帧联系表**。

---

## 3. 编排器

```bash
# 全流程（--highlights 必填）
python scripts/pipeline.py all --raw <素材> --work <work> --highlights hl.json

# 单阶段重跑（改了字幕样式只跑 subs，不用重切）
python scripts/pipeline.py subs --work <work>
```

中间产物全落盘 → 断点续跑，失败不丢进度。

### 平台合规参数（抖音/快手 2026 规则，下一部剧默认带）

```bash
python scripts/pipeline.py all --raw <素材> --work <work> --highlights hl.json \
  --width 1080 --height 1920 \
  --min-bitrate 12 \
  --source-sub-mode auto
```

- `--min-bitrate 12`：成片最低码率 Mbps（平台建议 12-18），S6 字幕烧录切码率模式。
- `--endcard-text` 默认「点底部看全集」，**禁写"合集"二字**（平台禁建合集）。
- **AI 生成内容标注口径**：只落在**封面右下角**（rule_cover.py 自带）+ **简介尾缀**
  （发布文案模板自带）两处；**片头不加标注卡**（用户 2026-10-18 明令：不影响开头观感）。

### 封面与文案（规则版）

- **封面**：`scripts/rule_cover.py`（1080×1920 规范版：冲突特写裁切、顶部 1/3 留白、
  粗体白字黑边钩子 ≤2/3 宽、左上集数章、底部金楷剧名、右下 AI 标注、底图 AI 水印抹除）：
  ```bash
  python scripts/rule_cover.py --base <底图> --out 封面.jpg --ep "第1集" \
      --name "剧名" --l1 "钩子上句" --l2 "钩子下句？"
  ```
- **发布文案/标签**：禁"热播/爆款/强推/免费"及广告法绝对化词；快手必带 `#快来看短剧`；
  抖音 5-6 个 / 快手 6-7 个标签；简介尾缀必含「本作品含AI生成内容」（与封面标注构成两处标注，
  片头不加）。

### 付费调用协议（支付宝 SkillPay 支付改造 · per_call 0.20 元/次）

本技能按 `pricing.model=per_call` 计费：每次**产出型调用**（`all` / `canvas` / `subs` / `endcard`）
计 1 次，查询/重跑质检不计费。调用链路遵循 SkillPay 支付改造规范
（网关 `https://skillpay.alipay.com/api`，alipay SkillPay API），五个环节缺一不可：

1. **402 单笔下发**：调用方本地无有效支付凭证时，网关返回 `HTTP 402` +
   响应头 `Payment-Needed: true`，响应体为单笔订单：
   `{"order_id":"...","amount_fen":20,"currency":"CNY",
     "pay_url":"https://skillpay.alipay.com/pay/<order_id>","expire_in":300}`。
   调用方先走 `POST /v1/order/pre` 预下单锁定价格，再引导支付。
2. **支付凭证重试**：用户完成支付后，调用方携带 `Payment-Proof: <proof_token>` 请求头
   **重试原调用**；网关校验 proof_token 与 order_id 的绑定关系及有效期，通过后放行执行。
   凭证失效/被消费 → 再次返回 402 重走下发流程。
3. **暗付调用**（免确认自动扣款）：首次支付时一并完成支付宝钱包绑定；后续调用预附
   `X-SkillPay-AutoPay: wallet`，网关直接从绑定钱包划扣 0.20 元并放行，无需用户手动确认；
   钱包余额不足或划扣失败 → 自动回落 402 单笔下发流程。
4. **履约确认**：成片产出并通过 S7 质检闸门后，调用方必须回调
   `POST /v1/pay/complete/ack`（携带 `order_id` + `proof_token` + 产出物 sha256 指纹）
   完成履约确认；超过 10 分钟未 ack 或质检不通过 → 平台自动退款/解冻。
   状态机单向迁移：`pending → paid → fulfilled`。
5. **订阅持久化与幂等**：
   - **持久化**：订阅模式（可选 `model: subscription`）的权益凭证持久化在
     `~/.workbuddy/skillpay/<skill_id>.json`（`sub_id` / `expire_at` / `token`），
     有效期内调用免 402 直通；到期前 72h 输出续费引导，到期即失效。
   - **幂等**：每次调用生成 `Idempotency-Key: <skill_id>:<order_id|proof_token>:<时间片>`，
     网关按 key 去重——支付回调重复投递、凭证重试、ack 重复提交均**不重复计费、不重复扣款**，
     幂等返回首次结果。

> 交付口径：本技能为按次买断式调用，支付成功即交付当次完整成片产物（无云端保护扣留）；
> 已集成支付能力，压缩包可下载做离线备份。

---

## 4. 致命坑（每条都真的会挂）

1. **`silencedetect` 默认值等于废** —— `noise=-60dB / d=2` 对真实素材返回 0 条，
   网上因此误传「这滤镜坏了」。实际要用**比底噪高 5-10dB** 的值，先 `--sweep` 实测。
2. **★BGM 素材没有静音** —— 本项目实测 5 集短剧，silencedetect 全阈值合计只出 **6 个**切点，
   吸附白名单基本是空的。**必须用 VAD**（`stage2b_vad.py`），实测出 **76 个**（58 个 SAFE）。
   这是本项目最核心的技术选型，不是可选项。
3. **S3 必须读 `cut_points.json` 不是 `silences.json`** —— 接错文件会导致
   100% 切点退化 FORCED，但功能测试全绿（不报错、CSV 正常生成），
   **只能靠看 `in_snap` 列的 SILENCE 比例发现**。
4. **吸附搜索窗口不能太小** —— 短剧台词密集，±3s 内常找不到间隙。
   必须**渐进扩大**（×1.5 → ×2 → ×3），否则大量切点退化成硬切，等于白做 VAD。
5. **出点吸附必须维持原定片段时长** —— 否则一段被吸成 3.5s 而用户要 5s，节奏就乱了。
   正解：出点目标 = 吸附后入点 + 原定时长，再在该位置附近找间隙；
   找不到就以「入点+原定时长」收尾（仍远离入点，不会吞字）。
6. **`-ss` 放 `-i` 之后才准** 是 ffmpeg 2.1 前的过时说法。现代版本**放前面**，
   已是帧精确；放后面只是白解码一遍。
7. **`-c copy` 切原片会回退到关键帧** —— 关键帧间隔通常 2-10 秒，
   表现为开头黑屏/卡住或音画错位，正好破坏 S3 的吸附成果。必须重编码或用 all-intra。
8. **ASS 烧录漏 `fontsdir`** → 中文字体找不到，渲染成方块。
   `-vf "ass='路径':fontsdir='C\\:/Windows/Fonts'"`（注意 `C:` 要转义成 `C\:`）。
9. **拼接后时间码不重映射** → 字幕全错。见 S6。
10. **`brightness` 是加法偏移不是乘法系数** —— `brightness=1.08` 会让每像素 +275，全片冲成纯白。
    调色用 `gamma` / `contrast` / `saturation`。
11. **FunASR 缺 `torchaudio` 会报 ImportError** —— 它需要 torchaudio 或 kaldi-native-fbank
    做特征提取，装 funasr 时一并装：
    `pip install torchaudio --index-url https://download.pytorch.org/whl/cpu`
12. **pip 装大包时临时目录在 C 盘** → 本机 C 盘仅 2GB 会报
    `OSError(28, 'No space left on device')`。
    必须 `--cache-dir <E盘>` + `TMPDIR=<E盘>`。
13. **modelscope/HF 缓存默认落 `~/.cache`（C 盘）** → 必须设 `MODELSCOPE_CACHE` / `HF_HOME`。
14. **临时帧文件用 `os.remove` 会被宿主 safe-delete 守卫拦截** —— 同名前缀覆盖即可，别删。
    另：`extract_frames` 的 prefix 要**按源文件区分**，否则多集串行写会互相覆盖。
15. **★SenseVoice 不输出 `sentence_info`** —— 实测 `res[0].keys()` 只有 `['key','text']`。
    「一次性转写直接带时间戳」这条路走不通，**必须先 VAD 拿段再逐段送 ASR**。
16. **★关掉 VAD 会识别成乱码** —— 实测同一段 172s 素材，
    带 `vad_model="fsmn-vad"` 识别完全正确，关掉只出 24 字且内容全错。
    VAD 不是可选项。
17. **字幕 `max_units` 不能硬编码** —— 15 单位在 62px 字号下 = 930px > 900px 可用宽度，
    字幕会横向溢出画面。必须**按字号动态算**：
    `max_units = (画布宽 − 左右边距 − 描边余量) / 字号`。
18. **长台词不能堆成多行 `\N` 拼接** —— 28 字台词被堆成 7 行会盖住画面中下部，观感极差。
    正解：`build_subtitle_segments()` 按屏分段播放，每屏最多 2 行、最短 0.9s。

---

## 5. 空间控制（本机 C 盘仅 2GB）

| 内容 | 放哪 |
|---|---|
| ASR venv（torch+funasr，约 2-3GB） | `E:\WorkBuddy_ASR\asrvenv` |
| 模型缓存 | `E:\WorkBuddy_ASR\cache` |
| pip 缓存与临时目录 | `E:\pipcache` / `E:\piptmp` |
| 素材与中间产物 | `E:\duanju_work\` |

**不要把中间产物写到 C 盘或工作区根目录。**

---

## 6. 合规红线

- 著作权法保护复制权与信息网络传播权，**二创不等于免责**。
- 抖音已与优酷/爱奇艺/芒果/搜狐开通**官方二创白名单片库**，优先从那里取材。
- 平台查重是**画面指纹 + 音频频谱 + 文本**三重核验。
  2026 年抽帧已升级为「关键帧 + 运动轨迹分析」，**单纯抽帧已失效**。
- 有效去重：打散镜头来源（单段 ≤8s，一条 ≥5 段）+ 音频轨重制。
  **改 MD5 / 只加滤镜 / 只换封面全部无效。**
- **本流水线是技术工具箱，不替你判断授权状态。**

---

## 7. 参考文档

| 文件 | 内容 |
|---|---|
| `references/silence-snap.md` | 吸附算法、VAD vs 静音阈值调参手册 |
| `references/ass-typography.md` | 竖屏字幕排版规范、断句算法、安全区 |
| `references/dedup-compliance.md` | 去重手段有效性排序 + 查重原理 + 合规边界 |
| `references/asr-setup.md` | E 盘 ASR 环境搭建（含 C 盘空间坑） |
| `assets/plan.example.json` | 成片配置模板（改这个调风格） |
