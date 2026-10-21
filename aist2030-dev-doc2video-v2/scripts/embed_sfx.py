# embed_sfx.py —— 把音效文件内联成 data URI 写入 remotion/src/data/sfxData.ts
#
# 为什么需要这一步：
#   Remotion 渲染时 <Audio src={staticFile("sfx/x.mp3")}> 会走 HTTP 取文件。
#   长片渲染中该加载偶发 MediaError（实测两次都精确崩在第 8355 帧），
#   而 Remotion 在 Audio.js 里把音频 onError **硬编码成 cancelRender()**，
#   Error Boundary 拦不住 → 整片直接报废，且无法容错。
#   唯一可靠解法：从源头消除文件 I/O —— 内联成 data:audio/mpeg;base64,...。
#   （同样的做法已在音效试听页 build_sfx_audition.py 里验证可行。）
#
# 用法：
#   python embed_sfx.py --project<项目根> --files click_1.mp3,pop.mp3
#   不传 --files 则内联 remotion/public/sfx/ 下全部 mp3
#
# 体积参考：Mixkit 音效约 5~35KB/个，base64 后约 1.37倍，20 个也就 1MB 出头，可接受。

import argparse
import base64
import os
import sys

HEADER = """// ★ 自动生成，请勿手改。
// 由 scripts/embed_sfx.py 从 remotion/public/sfx/*.mp3 生成。
//
// 为什么内联：Remotion 渲染时 <Audio src={staticFile(...)}> 走 HTTP 取文件，
// 长片中偶发 MediaError（实测两次都精确崩在第 8355 帧）。而 Remotion 把音频
// onError 硬编码为 cancelRender()，Error Boundary 拦不住 → 整片报废且无法容错。
// 内联 data URI 后不经过任何文件 I/O，从源头消除该故障。
//
// 改音效的正确做法：替换 remotion/public/sfx/ 下的 mp3，然后重跑 embed_sfx.py。
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", required=True, help="项目根（含 remotion/）")
    ap.add_argument("--files", default="", help="逗号分隔文件名，缺省内联全部")
    a = ap.parse_args()

    sfx_dir = os.path.join(a.project, "remotion", "public", "sfx")
    if not os.path.isdir(sfx_dir):
        print(f"[x] 音效目录不存在: {sfx_dir}")
        return 1

    if a.files:
        names = [f.strip() for f in a.files.split(",") if f.strip()]
    else:
        names = sorted(f for f in os.listdir(sfx_dir)
                       if f.lower().endswith(".mp3") and not f.startswith("_"))

    lines = [HEADER, "", "export const SFX_DATA: Record<string, string> = {"]
    total = 0
    missing = []
    for n in names:
        p = os.path.join(sfx_dir, n)
        if not os.path.exists(p):
            missing.append(n)
            continue
        b = base64.b64encode(open(p, "rb").read()).decode("ascii")
        total += len(b)
        lines.append(f'  "{n}": "data:audio/mpeg;base64,{b}",')
    lines += ["};", ""]

    if missing:
        print(f"[!] 跳过不存在的文件: {missing}")
    if not total:
        print("[x] 没有任何音效被内联（检查文件名/目录）")
        return 1

    out = os.path.join(a.project, "remotion", "src", "data", "sfxData.ts")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"[ok] 内联 {len(names) - len(missing)} 个音效 -> {out}")
    print(f"     base64 总量 {total/1024:.0f} KB")
    return 0


if __name__ == "__main__":
    sys.exit(main())