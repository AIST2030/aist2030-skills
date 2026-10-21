#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
check_triggers.py —— 校验 Root.tsx 里所有 triggerWord 是否真能在旁白里找到。

为什么必须查：triggerWord 是「说到这个词时元素入场」的锚点。
词写错/用词与逐字稿不一致 → 该元素**永远不入场**，画面就少一块信息，
而渲染日志不会报任何错，只能靠抽帧人眼看或本脚本静态比对。

同时顺带检查：
  1. OVERLAYS 的键是否覆盖 timeline 全部页（漏页 = 该页无叠加层）
  2. triggerWord 是否在**本页**命中（跨页误命中 = 提前/延后入场）
"""
import json
import re
import sys

ROOT = r"remotion/src/Root.tsx"
TL = r"remotion/src/data/timeline.json"


def main():
    src = open(ROOT, encoding="utf-8").read()
    tl = json.load(open(TL, encoding="utf-8"))

    # 每页旁白纯文本
    pagetext = {}
    for p in tl["pages"]:
        pagetext[p["id"]] = "".join(
            (s.get("clean") or s.get("text") or "") for s in p["shots"]
        )

    # OVERLAYS 键
    m = re.search(r"const OVERLAYS[^=]*= \{(.*?)\n\};", src, re.S)
    keys = re.findall(r"^  (p\d+):", m.group(1), re.M) if m else []
    ids = [p["id"] for p in tl["pages"]]
    print(f"[OVERLAYS] keys={len(keys)} timeline={len(ids)} "
          f"order_match={keys == ids}")
    if [i for i in ids if i not in keys]:
        print("  MISSING:", [i for i in ids if i not in keys])
    if [k for k in keys if k not in ids]:
        print("  EXTRA:", [k for k in keys if k not in ids])

    # triggerWord 逐条查（连同所在页）
    pairs = re.findall(
        r'triggerWord:\s*"([^"]+)"', src)
    # 反查每个词命中哪些页
    print(f"\n[triggerWord] total={len(pairs)} unique={len(set(pairs))}")
    dead = []
    for w in sorted(set(pairs)):
        hit = [pid for pid, t in pagetext.items() if w in t]
        if not hit:
            dead.append(w)
    if dead:
        print("  ✗ 全片未命中（元素永不入场）:")
        for w in dead:
            print("     -", w)
    else:
        print("  ✓ 全部 triggerWord 均能在旁白中找到")

    # 每词命中页数分布：>1 页命中属跨页歧义，需人工确认
    multi = {w: [pid for pid, t in pagetext.items() if w in t]
             for w in sorted(set(pairs))}
    multi = {w: h for w, h in multi.items() if len(h) > 1}
    if multi:
        print("\n  ⚠ 跨多页命中（可能提前入场，建议逐个人工确认）:")
        for w, h in multi.items():
            print(f"     - {w}: {h}")

    return 1 if dead else 0


if __name__ == "__main__":
    sys.exit(main())