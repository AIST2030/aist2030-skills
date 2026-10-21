#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
ASR 抽象层：FunASR SenseVoice 优先。

★为什么首选 FunASR 而不是 faster-whisper（实测数据）：
   184 段中文音频 / CPU 8 线程，字符错误率 CER：
     FunASR SenseVoice   8.01%   449 MB   ~20× 实时
     FunASR Paraformer   9.85%   401 MB   ~22× 实时
     whisper.cpp small  22.12%   466 MB
   同体积下 SenseVoice 准 2.7 倍。本机无独显，whisper 大模型跑不动。

★★关键实现约束（2026-10-17 实测踩坑，两条都是硬事实）：

  1. SenseVoice 是**非自回归模型，不输出 sentence_info**。
     实测 `res[0].keys()` 只有 `['key','text']`，sentence_info 恒为空。
     → 不能指望「一次性转写直接带时间戳」。

  2. **必须开 vad_model**。
     关掉 VAD 直接整段转写，短剧素材上会识别成乱码
     （实测 172s 素材：带 VAD 识别完全正确，关 VAD 只出 24 字且内容错乱）。

  → 正解：**先 VAD 拿语音段 → 逐段送 ASR**。
     段边界本身就是时间戳，句级精度，且绕开 sentence_info 缺失问题。

环境隔离：
   torch+funasr 约 2-3GB，本机 C 盘仅 2GB → 必须装 E 盘独立 venv。
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ASR_VENV = os.environ.get("DRAMA_ASR_VENV", r"E:\WorkBuddy_ASR\asrvenv")
ASR_PY = str(Path(ASR_VENV) / "Scripts" / "python.exe")
CACHE_ROOT = os.environ.get("DRAMA_ASR_CACHE", r"E:\WorkBuddy_ASR\cache")

# 逐段识别的子进程执行体
CHILD = r'''
import os, sys, json, re, subprocess, tempfile
os.environ.setdefault("MODELSCOPE_CACHE", sys.argv[2])
os.environ.setdefault("HF_HOME", sys.argv[2])

audio, model_name, device = sys.argv[1], sys.argv[3], sys.argv[4]
ff = sys.argv[5]
MAX_SEGMENTS = int(sys.argv[6]) if len(sys.argv) > 6 else 400

from funasr import AutoModel
from funasr.utils.postprocess_utils import rich_transcription_postprocess

def clean_text(t):
    t = re.sub(r"<\|[^|]*\|>", "", t)
    t = re.sub(r"[\U0001F000-\U0001FAFF]", "", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t

tmpdir = tempfile.mkdtemp()
wav = os.path.join(tmpdir, "full.wav")
subprocess.run([ff, "-y", "-i", audio, "-vn", "-ac", "1", "-ar", "16000",
                "-c:a", "pcm_s16le", wav], check=True,
               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

vad = AutoModel(model="fsmn-vad", device="cpu", disable_update=True)
vad_res = vad.generate(input=wav)
segs = [[s[0] / 1000.0, s[1] / 1000.0] for s in vad_res[0].get("value", [])]
segs = [s for s in segs if (s[1] - s[0]) >= 0.25][:MAX_SEGMENTS]

model_dir = {
    "sensevoice": "iic/SenseVoiceSmall",
    "paraformer": "iic/speech_paraformer-large_asr_nat-zh-cn-16k-common-vocab8404-pytorch",
}.get(model_name, "iic/SenseVoiceSmall")

asr = AutoModel(model=model_dir, vad_model="fsmn-vad", device=device,
                disable_update=True)

sentences = []
for i, (a, b) in enumerate(segs):
    seg_wav = os.path.join(tmpdir, "seg%03d.wav" % i)
    subprocess.run([ff, "-y", "-ss", "%.3f" % max(0.0, a - 0.05), "-i", wav,
                    "-t", "%.3f" % (b - a + 0.10), "-c:a", "pcm_s16le", seg_wav],
                   check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        r = asr.generate(input=seg_wav)
    except Exception:
        continue
    if not r:
        continue
    si = r[0].get("sentence_info") or []
    if si:
        for s in si:
            t = clean_text(rich_transcription_postprocess(s.get("sentence", "")))
            if t:
                sentences.append({
                    "start": round(s.get("start", 0) / 1000.0 + a, 3),
                    "end":   round(s.get("end", 0) / 1000.0 + a, 3),
                    "text":  t, "spk": s.get("spk", 0), "src": "sentence_info",
                })
    else:
        t = clean_text(rich_transcription_postprocess(r[0].get("text", "")))
        if t:
            sentences.append({"start": round(a, 3), "end": round(b, 3),
                              "text": t, "spk": 0, "src": "vad_segment"})

print(json.dumps({"sentences": sentences}, ensure_ascii=False))
'''


def asr_available() -> tuple[bool, str]:
    """
    检查 ASR 环境。

    ⚠ 不能用 `import funasr` 当探针 —— 首次加载 torch+transformers+modelscope
    实测 >120 秒，会把「可用」误判成「不可用」。改为查包目录（快且准）。
    """
    if not Path(ASR_PY).exists():
        return False, f"ASR venv 不存在: {ASR_PY}"
    sp = Path(ASR_PY).parent.parent / "Lib" / "site-packages"
    missing = [n for n in ("funasr", "torch", "numpy", "torchaudio")
               if not (sp / n).exists() and not (sp / f"{n}.py").exists()]
    if missing:
        return False, f"缺少包: {', '.join(missing)}（装在 {sp}）"
    return True, "ok"


def transcribe(audio: str, model: str = "sensevoice", device: str = "cpu") -> dict:
    """转写单个音频，返回 {sentences:[{start,end,text}]}。"""
    ok, msg = asr_available()
    if not ok:
        raise RuntimeError(f"ASR 环境不可用：{msg}")

    sys.path.insert(0, str(Path(__file__).parent))
    import ffmpeg_env as fe

    cache = CACHE_ROOT
    Path(cache).mkdir(parents=True, exist_ok=True)
    child_file = Path(cache) / "_asr_child.py"
    # 始终覆写：CHILD 内容随代码演进出 bug 时，缓存旧版会一直复现问题
    child_file.write_text(CHILD, encoding="utf-8")

    # ⚠ 必须用 os.environ.copy()，不能 dict(os.environ)：
    #   Windows 上后者会让某些句柄变字符串，subprocess 报 "'str' has no fileno"
    env = os.environ.copy()
    env["MODELSCOPE_CACHE"] = cache
    env["HF_HOME"] = cache
    proc = subprocess.run(
        [ASR_PY, str(child_file), audio, cache, model, device, fe.ffmpeg_exe()],
        capture_output=True, timeout=7200, env=env,
    )
    out = proc.stdout.decode("utf-8", "ignore").strip()
    if proc.returncode != 0 or not out:
        err = proc.stderr.decode("utf-8", "ignore")
        raise RuntimeError(f"ASR 失败: {err[-800:]}")
    for line in reversed(out.splitlines()):
        line = line.strip()
        if line.startswith("{"):
            try:
                return json.loads(line)
            except json.JSONDecodeError:
                continue
    raise RuntimeError(f"ASR 输出无法解析: {out[-400:]}")


def run_batch(catalog: dict, work_dir: str, model: str = "sensevoice",
              only: str | None = None) -> dict:
    """对 catalog 中所有集做 ASR，合并写 asr.json。"""
    ok, msg = asr_available()
    if not ok:
        raise RuntimeError(f"ASR 环境不可用：{msg}")

    out_path = Path(work_dir) / "asr.json"
    if out_path.exists():
        existing = json.loads(out_path.read_text(encoding="utf-8"))
    else:
        existing = {"model": model, "method": "VAD 逐段识别", "episodes": {}}

    for ep in catalog["episodes"]:
        if only and ep["ep"] != only:
            continue
        cur = existing.get("episodes", {}).get(ep["ep"], {})
        if cur.get("sentences"):
            print(f"  {ep['ep']}: 已有 {len(cur['sentences'])} 条，跳过")
            continue
        if not ep["has_audio"]:
            continue
        print(f"  {ep['ep']} ASR 中（{ep['duration']:.0f}s 音频，逐 VAD 段识别）...")
        try:
            r = transcribe(ep["file"], model=model)
            existing.setdefault("episodes", {})[ep["ep"]] = {
                "sentences": r["sentences"],
                "count": len(r["sentences"]),
                "file": ep["file"],
            }
            out_path.write_text(json.dumps(existing, ensure_ascii=False, indent=2),
                                encoding="utf-8")
            print(f"      → {len(r['sentences'])} 条台词")
        except Exception as exc:
            print(f"      [!] 失败: {str(exc)[:300]}")

    total = sum(len(v.get("sentences", [])) for v in existing.get("episodes", {}).values())
    print(f"[ASR] 完成 → {out_path}（共 {total} 条台词）")
    return existing


if __name__ == "__main__":
    ok, msg = asr_available()
    print("ASR 可用" if ok else f"ASR 不可用：{msg}")
    if ok and len(sys.argv) > 1:
        r = transcribe(sys.argv[1])
        print(json.dumps(r, ensure_ascii=False, indent=2)[:2000])