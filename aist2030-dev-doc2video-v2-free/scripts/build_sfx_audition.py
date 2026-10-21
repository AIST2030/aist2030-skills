#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_sfx_audition.py —— 生成「音效试听 + 勾选」HTML。
把 public/sfx 下每个 mp3 裁成 1.5s 低码率预览，base64 内嵌，
页面列出播放器 + 勾选框；点「导出选择」得到 {"enabled":[...]} JSON，
用户回贴给 AI 即可锁定最终音效集。

用法：
  python build_sfx_audition.py
"""
import argparse
import base64
import json
import os
import subprocess
import sys

import imageio_ffmpeg

FF = imageio_ffmpeg.get_ffmpeg_exe()
HERE = os.path.dirname(os.path.abspath(__file__))
SFX = os.path.abspath(os.path.join(HERE, "..", "remotion", "public", "sfx"))
OUT = os.path.abspath(os.path.join(HERE, "..", "output", "sfx_audition.html"))
os.makedirs(os.path.dirname(OUT), exist_ok=True)

# 默认勾选的「轻量/安全」子集（用户在页面可改）
DEFAULT_ON = {
    "whoosh.mp3", "whoosh_1.mp3", "pop.mp3", "click_1.mp3", "sparkle.mp3",
    "magic_1.mp3", "alert.mp3", "notification_1.mp3", "interface_1.mp3",
    "sci-tech_1.mp3",
}

# 分类中文标签（用于分组展示）
GROUP_LABEL = {
    "whoosh": "Whoosh 扫风/转场", "pop": "Pop 轻点", "sparkle": "Sparkle 闪光",
    "alert": "Alert 提示", "sci-tech": "Sci-Tech 科技", "click": "Click 点击",
    "impact": "Impact 重击", "glitch": "Glitch 故障", "magic": "Magic 魔法",
    "keyboard": "Keyboard 键盘", "news": "News 新闻", "machine": "Machine 机械",
    "notification": "Notification 通知", "interface": "Interface 界面",
}


def group_of(fn):
    for k in GROUP_LABEL:
        if fn.startswith(k):
            return k
    return "other"


def preview(fn, sfx_dir=None):
    d = sfx_dir or SFX
    src = os.path.join(d, fn)
    tmp = os.path.join(d, f"_preview_{fn}")
    # 裁 1.5s + 单声道 + 64k，保证内嵌体积小
    r = subprocess.run(
        [FF, "-y", "-loglevel", "error", "-i", src, "-t", "1.5", "-ac", "1",
         "-b:a", "64k", tmp],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if r.returncode != 0 or not os.path.exists(tmp):
        # 兜底：直接读原文件（极小文件无需裁）
        if os.path.exists(src) and os.path.getsize(src) < 60_000:
            with open(src, "rb") as f:
                data = f.read()
        else:
            return ""
    else:
        with open(tmp, "rb") as f:
            data = f.read()
        os.remove(tmp)
    return base64.b64encode(data).decode("ascii")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sfx-dir", default=None,
                    help="音效目录，缺省 <脚本上级>/remotion/public/sfx")
    ap.add_argument("--out", default=None,
                    help="试听页输出路径，缺省 <脚本上级>/output/sfx_audition.html")
    a = ap.parse_args()

    global SFX, OUT
    if a.sfx_dir:
        SFX = os.path.abspath(a.sfx_dir)
    if a.out:
        OUT = os.path.abspath(a.out)
    if not os.path.isdir(SFX):
        print(f"[FATAL] 音效目录不存在: {SFX}")
        return 2
    os.makedirs(os.path.dirname(OUT), exist_ok=True)

    files = sorted(f for f in os.listdir(SFX) if f.lower().endswith(".mp3")
                   and not f.startswith("_"))
    if not files:
        print(f"[FATAL] 目录内没有 mp3: {SFX}（先跑 fetch_sfx.py 抓音效）")
        return 2
    groups = {}
    for fn in files:
        g = group_of(fn)
        groups.setdefault(g, []).append(fn)

    cards = []
    for g in sorted(groups, key=lambda x: (x == "other", x)):
        label = GROUP_LABEL.get(g, "其它")
        cards.append(f'<div class="group"><h2>{label}</h2><div class="row">')
        for fn in sorted(groups[g]):
            b64 = preview(fn)
            checked = "checked" if fn in DEFAULT_ON else ""
            cls = "on" if fn in DEFAULT_ON else "off"
            cards.append(f'''
      <div class="item {cls}">
        <label class="chk"><input type="checkbox" value="{fn}" {checked}/> {fn}</label>
        {'<audio controls preload="none" src="data:audio/mp3;base64,'+b64+'"></audio>' if b64 else '<span class="warn">预览不可用</span>'}
      </div>''')
        cards.append("</div></div>")

    html = """<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>音效试听 · 勾选</title><style>
body{background:#0b1018;color:#e8f4f8;font-family:-apple-system,"Microsoft YaHei",sans-serif;margin:0;padding:24px}
h1{color:#6ECFD8}h2{color:#A8F0F7;font-size:16px;margin:18px 0 8px;border-left:3px solid #6ECFD8;padding-left:8px}
.row{display:flex;flex-wrap:wrap;gap:12px}
.item{background:#0f1c2c;border:1px solid #1c3346;border-radius:10px;padding:10px 12px;width:240px}
.item.off{border-color:#33424f;opacity:.6}
.chk{display:block;font-size:13px;margin-bottom:6px;word-break:break-all}
audio{width:100%;height:32px}
.warn{color:#e8a;font-size:12px}
.bar{position:sticky;top:0;background:#0b1018;padding:12px 0;border-bottom:1px solid #1c3346;margin-bottom:8px;z-index:9}
button{background:#6ECFD8;color:#04121c;border:0;border-radius:8px;padding:10px 18px;font-weight:700;cursor:pointer}
textarea{width:100%;height:120px;background:#06101a;color:#9fe;border:1px solid #1c3346;border-radius:8px;font-family:monospace;padding:10px;margin-top:8px}
</style></head><body>
<h1>音效试听 &amp; 勾选</h1>
<p style="color:#8aa">勾选你要保留的音效（默认预选了一组轻量安全的）。点每项右侧播放试听；完成后点「导出选择」复制 JSON 回贴给 AI。</p>
<div class="bar"><button id="exp">导出选择</button><button id="selAll" style="background:#33424f;color:#cfe">全选</button><button id="selNone" style="background:#33424f;color:#cfe">全不选</button>
<textarea id="out" placeholder="导出的 JSON 会显示在这里"></textarea></div>
__CARDS__
<script>
const boxes=document.querySelectorAll('input[type=checkbox]');
document.getElementById('exp').onclick=()=>{
  const on=[...boxes].filter(b=>b.checked).map(b=>b.value);
  document.getElementById('out').value=JSON.stringify({enabled:on},null,0);
  document.getElementById('out').select();
};
document.getElementById('selAll').onclick=()=>boxes.forEach(b=>b.checked=true);
document.getElementById('selNone').onclick=()=>boxes.forEach(b=>b.checked=false);
</script></body></html>"""
    html = html.replace("__CARDS__", "\n".join(cards))
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"[done] {len(files)} 个音效 → {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
