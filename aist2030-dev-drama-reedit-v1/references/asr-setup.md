# E 盘 ASR 环境搭建（含 C 盘空间坑）

## 为什么要单独建 E 盘环境

本机 **C 盘仅剩 2GB**，而 `torch + funasr` 需要 2-3GB。
直接装进主 venv 或系统 Python 会立刻爆盘。

**所有 ASR 相关的东西（venv / 模型缓存 / pip 缓存 / 临时目录）都必须放 E 盘。**

## 目录规划

| 内容 | 路径 | 体积 |
|---|---|---|
| ASR venv | `E:\WorkBuddy_ASR\asrvenv` | ~3GB |
| 模型缓存 | `E:\WorkBuddy_ASR\cache` | ~1GB |
| pip 缓存 | `E:\pipcache` | 可随时清 |
| pip 临时目录 | `E:\piptmp` | 安装时峰值几百 MB |

## 搭建步骤

```bash
# 1. 建 venv（用托管版 python）
C:\Users\Administrator\.workbuddy\binaries\python\versions\3.13.12\python.exe -m venv E:\WorkBuddy_ASR\asrvenv

# 2. 装 torch（CPU 版，从官方源）
E:\WorkBuddy_ASR\asrvenv\Scripts\python.exe -m pip install torch \
  --index-url https://download.pytorch.org/whl/cpu --trusted-host download.pytorch.org

# 3. 装 funasr（★临时目录和缓存必须指到 E 盘，否则报 No space left on device）
set TMPDIR=E:\piptmp
set TEMP=E:\piptmp
set TMP=E:\piptmp
E:\WorkBuddy_ASR\asrvenv\Scripts\python.exe -m pip install --cache-dir E:\pipcache \
  numpy funasr modelscope --index-url https://mirrors.aliyun.com/pypi/simple/ \
  --trusted-host mirrors.aliyun.com
```

## 三个必踩的坑

### 坑 1：`+cpu` 后缀在阿里云镜像上不存在

```
ERROR: Could not find a version that satisfies the requirement torch==2.9.1+cpu
(from versions: 2.6.0, 2.7.0, ... 2.14.1)     ← 没有 +cpu 后缀
```

阿里云 PyPI 镜像是**上游同步版**，不带 `+cpu` 本地版本标记。
要么去掉 `+cpu` 后缀（会装 CUDA 版，几个 GB），要么从官方 CPU 源装：

```bash
--index-url https://download.pytorch.org/whl/cpu
```

**本项目用官方 CPU 源**，装出来是 `torch-2.14.1+cpu`。

### 坑 2：pip 临时目录在 C 盘 → `OSError(28, No space left on device)`

即使 `--cache-dir` 指到 E 盘，pip 解压 wheel 用的 `TEMP`/`TMP` 仍在 C 盘。
torch 的 wheel 很大，解压过程会瞬间吃满 C 盘那 2GB。

**必须同时设 `TMPDIR` / `TEMP` / `TMP`。**

### 坑 3：模型缓存默认落 `~/.cache`（C 盘）

modelscope 和 huggingface_hub 默认把模型下载到 `C:\Users\xxx\.cache\`。
模型本身几百 MB，C 盘放不下。

**必须在跑 ASR 前设环境变量**，`asr_sensevoice.py` 里的子进程已经处理了：

```python
os.environ.setdefault("MODELSCOPE_CACHE", r"E:\WorkBuddy_ASR\cache")
os.environ.setdefault("HF_HOME", r"E:\WorkBuddy_ASR\cache")
```

## 为什么选 FunASR 而不是 faster-whisper

实测数据（184 段中文音频 / CPU 8 线程 / 字符错误率 CER 越低越好）：

| 系统 | CER | 体积 | CPU 速度 | 本机可用 |
|---|---|---|---|---|
| **FunASR SenseVoice** | **8.01%** | 449 MB | ~20× 实时 | ✅ |
| FunASR Paraformer | 9.85% | 401 MB | ~22× 实时 | ✅ |
| whisper.cpp small | 22.12% | 466 MB | — | ⚠ |
| whisper.cpp large-v3-turbo | 23.15% | 1.6 GB | — | ❌ 无独显跑不动 |

**同体积下 SenseVoice 比 whisper small 准 2.7 倍。**
本机无独显，whisper 的大模型根本跑不动。

字幕对齐是这个流水线的质量命门（吸附切点、ASS 硬字幕、同步核验全靠它），
所以这一环不能用次优解。

## ⚠ SenseVoice 的两个硬约束（实测确认，不是文档说的）

### 1. 不输出 `sentence_info`

官方文档常写「FunASR 能返回带时间戳的句子」，但 SenseVoice 是**非自回归模型**，
实测输出只有：

```python
res[0].keys()  →  ['key', 'text']
res[0].get("sentence_info")  →  []      # 恒为空
```

所以**不能**指望「一次性转写直接带时间戳」。本项目的解法见下。

### 2. 关掉 VAD 会识别成乱码

| 配置 | 172s 素材的识别结果 |
|---|---|
| `AutoModel(model=..., vad_model="fsmn-vad")` | ✅ 完全正确（「这颗万年神树是我们苗疆的守护神…」） |
| `AutoModel(model=...)` （关掉 VAD） | ❌ 只出 24 字且内容全错 |

VAD 不是可选项 —— SenseVoice 需要 VAD 提供的语义切分上下文。

## 正确用法：先 VAD 拿段 → 逐段送 ASR

段边界本身就是时间戳，句级精度，且绕开 `sentence_info` 缺失问题。

```python
# 1) VAD 拿语音段
vad = AutoModel(model="fsmn-vad", device="cpu")
segs = [[s[0]/1000, s[1]/1000] for s in vad.generate(input=wav)[0]["value"]]
segs = [s for s in segs if s[1]-s[0] >= 0.25]     # 丢掉过短的音节段

# 2) 逐段送 ASR（必须带 vad_model）
asr = AutoModel(model="iic/SenseVoiceSmall", vad_model="fsmn-vad", device="cpu")
for a, b in segs:
    # 切出该段音频，两侧各留 0.05s 余量（VAD 边界偏保守）
    subprocess.run([ff, "-ss", str(a-0.05), "-i", wav, "-t", str(b-a+0.10),
                    "-c:a", "pcm_s16le", seg_wav])
    r = asr.generate(input=seg_wav)[0]
    text = clean(r.get("text", ""))     # 剥掉 <|zh|><|BGM|> 等标签与 emoji
    if text:
        sentences.append({"start": a, "end": b, "text": text})
```

**注意**：段级结果可能仍有 `sentence_info`（Paraformer 系有），有就用它（时间更准），
没有就退回段边界。`asr_sensevoice.py` 里两种都处理了。

### 文本清洗

SenseVoice 输出混着控制标签：

```
<|nospeech|><|EMO_UNKNOWN|><|Event_UNK|><|woitn|> <|zh|><|NEUTRAL|><|BGM|><|woitn|>这颗万年神树...
```

必须剥掉：

```python
t = re.sub(r"<\|[^|]*\|>", "", t)
t = re.sub(r"[\U0001F000-\U0001FAFF]", "", t)   # emoji
t = re.sub(r"\s+", " ", t).strip()
```

漏了这步，字幕会显示 `<|zh|>` 这种乱码。

### 耗时参考

本机 8 核 CPU、无独显：

| 素材 | 语音段数 | 耗时 |
|---|---|---|
| 172s (ep01) | 44 段 | ~3 分钟 |
| 128s (ep05) | 22 段 | ~2 分钟 |

约 **音频时长的 1-1.2 倍**（比宣传的 20× 实时慢，因为逐段调用有固定开销）。
批量处理要有心理预期。

## 验证

```bash
E:\WorkBuddy_ASR\asrvenv\Scripts\python.exe -c "import funasr, torch, numpy; print('OK', torch.__version__)"
```

再跑一次完整自检（会下模型）：

```bash
python scripts/asr_sensevoice.py "任意一个视频文件"
```

首次运行会下载 fsmn-vad（约 1.7MB）和 SenseVoice（约 449MB）到 E 盘缓存。

### ⚠ 探针不要用 `import funasr`

`import funasr` 首次要加载 torch + transformers + modelscope 全量依赖，
**实测 >120 秒**。拿它当可用性探针会把「可用」误判成「不可用」。

`asr_sensevoice.py` 改为**查包目录**：

```python
sp = Path(ASR_PY).parent.parent / "Lib" / "site-packages"
missing = [n for n in ("funasr","torch","numpy","torchaudio") if not (sp/n).exists()]
```

## 环境变量覆盖

```bash
export DRAMA_ASR_VENV=E:\其他路径\asrvenv
export DRAMA_ASR_CACHE=E:\其他路径\cache
```

## 空间体检

```bash
du -sh E:\WorkBuddy_ASR        # ASR 环境总占用
df -h C:                       # 确认 C 盘没被吃掉
```

装完 C 盘可用空间应该基本不变。如果掉了很多，
说明有东西写到 C 盘了，检查 `MODELSCOPE_CACHE` 是否生效。

### ⚠ `os.devnull` 与 `dict(os.environ)` 的 Windows 陷阱

**现象**：子进程里调 ffmpeg 报 `AttributeError: 'str' object has no attribute 'fileno'`。

**两个原因叠加**：
1. funasr 的某些模块会给 `os.devnull` 打 monkey patch 变成**字符串**，
   传给 `subprocess` 的 `stdout=` 就炸 → 必须用 `subprocess.DEVNULL` 常量。
2. `env=dict(os.environ)` 在 Windows 上会让某些句柄变字符串 → 必须用 `os.environ.copy()`。

两条都要避开。
