# 渲染与质检细则（Remotion + 本地 Chrome）

## 一、环境要求

| 组件 | 要求 | 说明 |
|---|---|---|
| Node | ≥ 18（推荐 22） | 跑 Remotion CLI |
| Chrome | 本机已安装 | headless 渲染，用 `--browser-executable` 指过去 |
| Python | ≥ 3.10 | 跑 TTS 与质检脚本 |
| ffmpeg | 可用即可 | 没有系统 ffmpeg 时用 `imageio-ffmpeg` 自带包 |

依赖安装（隔离环境，不要污染全局）：
```bash
pip install edge-tts imageio-ffmpeg numpy python-pptx
```

---

## 二、渲染命令

```bash
node node_modules/@remotion/cli/remotion-cli.js render src/index.ts <CompositionId> \
  "D:\path\to\output.mp4" \
  --browser-executable="C:\Users\<user>\AppData\Local\Google\Chrome\Application\chrome.exe" \
  --concurrency=3 \
  --crf=20 \
  --audio-bitrate=192k \
  --codec=h264
```

### 参数经验

| 参数 | 建议 | 理由 |
|---|---|---|
| `--concurrency` | **3~4** | 8 核 16G 机器上的甜点；开高会因内容器内存不足反而变慢甚至崩 |
| `--crf` | 18~22 | 20 是清晰度/体积平衡点 |
| `--audio-bitrate` | 192k | 人声足够；128k 也够用 |
| `--codec` | h264 | 兼容性最好 |

### ⚠️ 三个必踩的坑

1. **`--out` / 输出路径必须绝对路径**
   相对路径会被静默忽略，产物落到 `remotion/out/CompositionId.png|mp4`。
   单帧渲染后的补救：`mv -f out/CompositionId.png "$QCDIR/xxx.png"`。

2. **必须先渲单帧（still）再渲全片**
   全片以小时计（3 万帧 ≈ 1 小时）。先用 `still --frame=N` 渲 6~10 个关键帧检查排版，改完再全量渲染。

3. **`wmic` 被安全策略拦截时的"假失败"**
   某些环境（含企业安全策略）会拦截 `wmic.exe`，导致渲染进程退出码异常、任务被标记为 failed，**但成片已经成功写出**。
   **判成功要以产物为准**：文件存在 + `ffmpeg -i` 读到的时长正确 + 质检通过。

---

## 三、五道质检闸门

```python
# scripts/qc_video.py 的判据
1. 输出存在          # 文件存在且体积合理
2. 规格正确          # 分辨率/帧率 与 timeline 声明一致，且有音轨
3. 时长一致          # |成片时长 - timeline.totalSeconds| < 0.2s
4. 响度达标          # 目标 LUFS ±1.0
5. 抽帧非黑屏        # 按页均匀抽帧，检查非全黑
```

### 闸门 3 的判读
- 差 < 0.2s：正常（编码器首尾帧的微差）。
- 差 1s 以上：说明有音频没被投放（shot 的 `durationFrames` 算错）或末页被截断。

### 闸门 4 的判读（**必挂项**）
Remotion 直出响度恒为约 **-24 LUFS**，这是已知特征，**不是 bug**。
必须后处理归一化，见下一节。

---

## 四、响度归一化（双遍 linear loudnorm）

```bash
# 第 1 遍：测量
ffmpeg -i in.mp4 -af loudnorm=I=-16:TP=-1.5:LRA=11:print_format=json -f null -

# 第 2 遍：按测量值校正（视频流 copy，零画质损失）
ffmpeg -i in.mp4 -c:v copy \
  -af loudnorm=I=-16:TP=-1.5:LRA=11:measured_I=..:measured_TP=..:measured_LRA=..:measured_thresh=..:offset=.. \
  -c:a aac -b:a 192k out.mp4
```

**要做迭代收敛**：单遍 loudnorm 常有 0.3~0.7 LUFS 偏差，跑第 2 轮即可收敛到 ±0.05。

`scripts/normalize.py` 已封装：读输入响度 → 迭代归一化 → 写回并复测 → 目标 ±0.3 才通过。

> 关键：`-c:v copy`，**只重编码音频**。否则整片要重压一遍，画质二损失且耗时翻倍。

---

## 五、抽帧质检方法

```bash
# 单帧
ffmpeg -y -ss <秒> -i final.mp4 -frames:v 1 out.png
```

**抽帧点位怎么选**
1. 每个场景模板至少一帧（确认排版没崩）；
2. **最宽字幕块**所在帧（用脚本按视觉宽度排序取 top）；
3. 页面刚切换后 0.5s（确认入场动画起点不是空白）；
4. 片尾（确认 CTA/关注信息完整）。

**逐帧要看的**
- 标题是否单行完整（有没有被画布裁掉）；
- 横幅文字有没有压住页码；
- 字幕是否严格单行；
- 卡片/列表是否有内容溢出或重叠；
- 骨架占位是否正常（未讲到的项）。

---

## 六、性能参考（8 核 / 16G 实测）

| 规模 | 帧数 | 耗时 | 备注 |
|---|---|---|---|
| 6 页短片 | 3,701 | ~11 分钟 | 并发 3 |
| 27 页长片 | 30,642 | ~80 分钟 | 并发 3，内存是瓶颈 |

估算公式：`耗时 ≈ 帧数 / 6.5 秒`（并发 3）。

**长片建议**：后台跑，勿用前台超时；渲染期间不要同时跑其他重任务（内存竞争会让渲染变慢数倍）。

---

## 七、成片交付前的最后三问

1. **比例与 PPT 一致吗？**（等比放大，不是拉伸——PPT 720×960 → 成片 1080×1440，都是 3:4）
2. **内容与 PPT 逐字一致吗？**（忠实度断言过了吗？）
3. **音画同步吗？**（随机抽 3 帧，看画面高亮元素是不是正在被念到的内容）
