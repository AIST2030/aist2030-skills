# 四道闸门：可复制的完整代码

> 用途：每次改文案 / 换素材后跑一遍，把"渲染完才发现错"变成"渲染前就拦下"。
> v1 靠人工过目发现问题，v2 把能自动化的都自动化——**这是省算力、少返工的关键**。

---

## 闸门 ① 素材亮度体检（防夜景黑屏）

**为什么**：tech/cinematic 深底上，夜景素材（少量高光 + 大面积黑）会让整页发死。
实测 p15 抓到 city 夜景灰度均值仅 7（max 223 / p99 82），叠深底几乎全黑。

**怎么判**：抽 3 帧（0.5s / 3s / 6s）算灰度均值，`<12` 判黑场。
用 `max` + `p99` 区分「真黑」与「夜景高光」（夜景是 max 高但 mean 极低）。

```python
import glob, os, subprocess, numpy as np
FF = r"C:\Users\Administrator\.workbuddy\binaries\python\envs\default\Lib\site-packages\imageio_ffmpeg\binaries\ffmpeg-win-x86_64-v7.1.exe"

bad = []
for f in sorted(glob.glob("remotion/public/media/p*.mp4")):
    lum = []
    for ss in ["0.5", "3", "6"]:
        p = subprocess.run(
            [FF, "-ss", ss, "-i", f, "-frames:v", "1",
             "-f", "rawvideo", "-pix_fmt", "gray", "-"],
            capture_output=True)
        if len(p.stdout) > 0:
            lum.append(round(float(np.frombuffer(p.stdout, np.uint8).mean()), 1))
    if not lum or min(lum) < 12:
        bad.append((os.path.basename(f), lum))
    print(os.path.basename(f), lum)

print("BLACK/TOO-DARK:", bad if bad else "none")
```

**处理**：换检索词重抓（`--only p15 --force`）。
⚠ 换词时同时考虑**页面语义**——讲办公场景别用 city，用 lifestyle/business。

---

## 闸门 ② triggerWord 校验（防元素永不入场）

**为什么**：triggerWord 是「说到这个词时元素入场」的锚点。
词与逐字稿不一致 → 元素**永远不入场**，画面静默少一块，**渲染日志不报错**。
实测抓到 `"Hidden Decoding"`（实为 `HiddenDecoding` 无空格）、`"全新流量入口"`（实为 `全新的流量入口`）。

```bash
python scripts/check_triggers.py --project <项目根>
```

输出解读：
- `全片未命中` = 元素永不入场 → **必须改成旁白里真实存在的词**。
- `MISSING: [p3, p7]` = 这几页没写 OVERLAYS → 该页只有实拍+字幕。
- `跨多页命中` = 提示项。运行时按**页内**匹配，通常无害，但值得扫一眼。

---

## 闸门 ③ 抽帧 QC（先抽帧后整片）

**为什么**：整片 20+ 分钟，盲渲返工代价极高。

```bash
python scripts/render.py --project <项目根> --mode qc                    # 自动挑每页代表帧
python scripts/render.py --project <项目根> --mode qc --frames 4706,5000 # 指定帧
```

人工过目后拼一张总览图（可选）：

```python
from PIL import Image, ImageDraw
import glob, os, json
fs = sorted(glob.glob("output/qc/f*.png"),
            key=lambda x: int("".join(c for c in os.path.basename(x) if c.isdigit())))
cols, tw, th = 6, 180, 240
rows = (len(fs) + cols - 1) // cols
sheet = Image.new("RGB", (cols*tw, rows*(th+18)), (10, 17, 32))
d = ImageDraw.Draw(sheet)
tl = json.load(open("remotion/src/data/timeline.json", encoding="utf-8"))
for i, f in enumerate(fs):
    n = int("".join(c for c in os.path.basename(f) if c.isdigit()))
    pg = next((p["id"] for p in tl["pages"]
               if p["startFrame"] <= n < p["startFrame"]+p["durationFrames"]), "?")
    im = Image.open(f).convert("RGB").resize((tw, th), Image.LANCZOS)
    x, y = (i % cols)*tw, (i//cols)*(th+18)
    sheet.paste(im, (x, y))
    d.text((x+4, y+th+3), f"{pg}  {n/30:.0f}s", fill=(190, 215, 232))
sheet.save("output/qc/_contact_sheet.png", quality=92)
```

⚠ **改过 Root.tsx 后，之前抽的帧已过期**，受影响页要重渲（`--frames` 指定）。

---

## 闸门 ④ 成片五道质检 + 渲染

```bash
# 整片 + 双遍 loudnorm -16 LUFS（render.py 内置，务必带 --loudnorm）
python scripts/render.py --project <项目根> --mode full --loudnorm --out "output/成片.mp4"

# 五道闸门质检：时长/分辨率/音轨/响度/黑帧
python scripts/qc_video.py "output/成片.mp4"
```

### ★★ 不要按退出码判成败（重要）

本机 `wmic.exe` 被沙箱 Program Blacklist 拉黑，Remotion 渲染收尾会调它探测 CPU/内存，
命中黑名单 → **整条命令被判 failed**，但渲染其实完全成功。

实测：QC 抽帧日志写「成功 29/29」、每帧 `OK`，任务通知却是 `status=failed`。

**判定铁律**：以日志「成功 N/N」+ 产物文件存在且 >100KB 为准。
**不要因为 failed 就重跑**（只会再撞一次，浪费几分钟）。

`render.py` 已内置该判定（`if not (os.path.exists(out) and size > 100KB)` 才算真失败）。

---

## 闸门 ⑤ 音效片段验证（★ 静帧 QC 抓不到的坑）

**为什么单独设闸门**：`render.py --mode qc` 走的是 `still` 静帧，**不播音频**。
所以音效类问题（解码失败、组件复用导致 src 漂移）在静帧阶段 **100% 全绿**，
一进整片就可能中途报废。实测踩过：整片跑到第 8354 帧（4.6 分钟处）抛
`Could not play audio with src /public/sfx%2Finterface_1.mp3`，
**前面十几分钟的工作量全部作废**。

**根因**：同页内 `section` 与 `banner` 映射到同一个音频文件时，
两个无 `key` 的相邻 `<Sfx>` 被 React 复用同一实例 → `<Audio>` 的 `src` 在渲染中途被替换
→ Chrome 解码失败 → Remotion 在 `Audio.js:31` 硬编码 `cancelRender()`。
**Error Boundary 完全拦不住**（onError 不接受外部覆盖），别在那条路上浪费时间。

**修法**：每个 `<Sfx>` 带「类型前缀 + 触发时刻」的稳定 key
（模板 `MediaScene.tsx` 已内置：`sfx-cover` / `sfx-section` / `sfx-bignum` / `sfx-banner`，
多次触发用 `` `sfx-kw-${i}-${Math.round(kEnter[i]*100)}` ``）。

**怎么验**（改完音效立刻跑，100 帧只要几秒）：

```bash
cd <项目>/remotion
node node_modules/@remotion/cli/remotion-cli.js render WeiXinXiaoWei \
  "<项目>/output/_test.mp4" --frames=8300-8400 --concurrency=2 --codec=h264 \
  --browser-executable "C:/Users/Administrator/AppData/Local/Google/Chrome/Application/chrome.exe"
```

- 出现 `+ .../_test.mp4` = 通过，可开整片。
- 出现 `Could not play audio` = 还没修好，**别开整片**。

> Windows 下要用完整 node 路径：
> `C:\Users\Administrator\.workbuddy\binaries\node\versions\22.22.2-6\node.exe`

**附带加固**：Mixkit 的 mp3 是 VBR，浏览器兼容性参差，落盘后统一重转标准 CBR：

```bash
cd <项目>/remotion/public/sfx
for f in *.mp3; do ffmpeg -y -v error -i "$f" -ac 1 -ar 44100 -b:a 128k \
  -write_xing 0 -id3v2_version 0 tmp.mp3 && mv tmp.mp3 "$f"; done
```

---

## 闸门 ⑥ tsc 类型检查（改完 .tsx 必跑）

```bash
cd <项目根>/remotion
"C:\Users\Administrator\.workbuddy\binaries\node\versions\22.22.2-6\node.exe" \
  ./node_modules/typescript/bin/tsc --noEmit
echo "TSC_EXIT=$?"   # 0 = 通过
```

⚠ 本机 `npx` 不能直接用（node 会把它当模块路径），要用 `./node_modules/typescript/bin/tsc`。