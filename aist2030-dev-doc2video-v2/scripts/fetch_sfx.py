#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fetch_sfx.py —— 扩充免版权音效库（Mixkit 免费可商用）。
从 Mixkit 音效分类页抓取 preview 直链，下载到 remotion/public/sfx/。

Mixkit 音效实测（2026-10-17）：
  搜索页 ?q= 被服务端忽略（所有关键词返回同一列表），必须走分类页：
    https://mixkit.co/free-sound-effects/<category>/
  页内预览直链在属性 data-audio-player-preview-url-value：
    https://assets.mixkit.co/active_storage/sfx/{id}/{id}-preview.mp3

用法：
  python fetch_sfx.py [--cats sci-tech,whoosh,...] [--per 2]
"""
import argparse
import json
import os
import re
import sys
import time
import urllib.request

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

# 已知可用分类（实测 200 + 内容各异，且为实拍/合成音效，非人声）
KNOWN_CATS = [
    "sci-tech", "whoosh", "click", "impact", "glitch", "magic",
    "keyboard", "news", "machine", "notification", "interface",
]


def _http(url, binary=False, timeout=25):
    req = urllib.request.Request(
        url, headers={"User-Agent": UA, "Accept-Language": "zh-CN,zh;q=0.9"})
    try:
        raw = urllib.request.urlopen(req, timeout=timeout).read()
        return (raw if binary else raw.decode("utf-8", "ignore")), None
    except Exception as e:
        return None, str(e)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cats", default=",".join(KNOWN_CATS))
    ap.add_argument("--per", type=int, default=2)
    ap.add_argument("--out", default=None,
                    help="音效落盘目录，缺省 <脚本上级>/remotion/public/sfx；"
                         "在真实项目里跑时应传 <项目根>/remotion/public/sfx")
    a = ap.parse_args()

    here = os.path.dirname(os.path.abspath(__file__))
    if a.out:
        out = os.path.abspath(a.out)
    else:
        out = os.path.abspath(os.path.join(here, "..", "remotion", "public", "sfx"))
    os.makedirs(out, exist_ok=True)

    cats = [c.strip() for c in a.cats.split(",") if c.strip()]
    total = 0
    for c in cats:
        html, err = _http(f"https://mixkit.co/free-sound-effects/{c}/")
        if not html:
            print(f"[skip] {c}: {err}")
            continue
        urls = re.findall(
            r'data-audio-player-preview-url-value="'
            r'(https://assets\.mixkit\.co/active_storage/sfx/\d+/\d+-preview\.mp3)"',
            html)
        if not urls:
            print(f"[skip] {c}: 0 直链（分类可能不存在）")
            continue
        print(f"[cat] {c}: {len(urls)} 个")
        for i, u in enumerate(urls[:a.per]):
            fn = f"{c}_{i+1}.mp3"
            dst = os.path.join(out, fn)
            if os.path.exists(dst):
                print(f"  [cache] {fn}")
                total += 1
                continue
            data, e = _http(u, binary=True)
            if not data or len(data) < 500:
                print(f"  [fail] {fn}: {e or '空'}")
                continue
            with open(dst, "wb") as f:
                f.write(data)
            print(f"  [ok] {fn} ({len(data)} B)")
            total += 1
            time.sleep(0.6)
    print(f"[done] 共 {total} 个音效文件 → {out}")


if __name__ == "__main__":
    main()
