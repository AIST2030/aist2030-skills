#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PPT 备注转讲解视频 —— 本地离线版
=====================================
功能：读取 PPTX 每页备注 → 本地 TTS 生成旁白 → PPT 逐页截图 → 按旁白时长合成视频

完全离线，不依赖任何云端 API：
  - PPT 解析：python-pptx
  - PPT 截图：LibreOffice headless（转 PDF → 转 PNG）
  - 语音合成：pyttsx3（调用系统自带语音引擎，Windows/macOS/Linux 均支持）
  - 视频合成：ffmpeg

依赖安装：
  pip install python-pptx pyttsx3 pdf2image
  # 系统需安装：LibreOffice、ffmpeg、poppler（pdf2image 依赖）

用法：
  python ppt_narration_video.py input.pptx -o output.mp4
  python ppt_narration_video.py input.pptx -o output.mp4 --voice "zh-CN-YunxiNeural" --rate 180
  python ppt_narration_video.py input.pptx --tts edge --voice "zh-CN-YunxiNeural"  # 需网络，音质更好
"""

import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

# ---------------------------------------------------------------------------
# 1. PPT 备注提取
# ---------------------------------------------------------------------------

def extract_notes(pptx_path: str) -> list[str]:
    """用 python-pptx 提取每页备注，返回备注文本列表（按页序）。"""
    from pptx import Presentation
    prs = Presentation(pptx_path)
    notes_list = []
    for i, slide in enumerate(prs.slides, 1):
        text = ""
        if slide.has_notes_slide:
            notes_slide = slide.notes_slide
            text = notes_slide.notes_text_frame.text.strip()
        if not text:
            print(f"[警告] 第 {i} 页没有备注，将使用静音占位")
            text = " "  # 静音占位
        notes_list.append(text)
    return notes_list


# ---------------------------------------------------------------------------
# 2. PPT 逐页截图（LibreOffice headless）
# ---------------------------------------------------------------------------

def pptx_to_images(pptx_path: str, out_dir: str, dpi: int = 150) -> list[str]:
    """
    用 LibreOffice headless 把 PPTX 转成 PDF，再用 pdf2image 转成逐页 PNG。
    返回图片路径列表（按页序）。
    """
    # 检查 LibreOffice
    soffice = shutil.which("soffice") or shutil.which("libreoffice")
    if not soffice:
        raise RuntimeError("未找到 LibreOffice，请先安装：https://www.libreoffice.org/")

    # 转 PDF
    with tempfile.TemporaryDirectory() as tmpdir:
        print("[1/3] LibreOffice 转换 PPTX → PDF ...")
        result = subprocess.run(
            [soffice, "--headless", "--convert-to", "pdf", "--outdir", tmpdir, pptx_path],
            capture_output=True, text=True, timeout=300
        )
        if result.returncode != 0:
            raise RuntimeError(f"LibreOffice 转换失败: {result.stderr}")

        pdf_files = list(Path(tmpdir).glob("*.pdf"))
        if not pdf_files:
            raise RuntimeError("LibreOffice 未生成 PDF 文件")
        pdf_path = str(pdf_files[0])

        # PDF → PNG
        print("[2/3] PDF → 逐页 PNG ...")
        from pdf2image import convert_from_path
        images = convert_from_path(pdf_path, dpi=dpi, fmt="png", output_folder=out_dir,
                                    output_file="slide_", paths_only=True)
        # 按页码排序（pdf2image 输出文件名 slide_0001-01.png 格式）
        images.sort(key=lambda p: int(re.search(r'_(\d+)-', Path(p).stem).group(1))
                      if re.search(r'_(\d+)-', Path(p).stem) else 0)
        return images


# ---------------------------------------------------------------------------
# 3. 本地 TTS 语音合成
# ---------------------------------------------------------------------------

def tts_pyttsx3(text: str, out_path: str, voice_id: str = None, rate: int = 180):
    """用 pyttsx3（系统语音引擎）生成音频，完全离线。"""
    import pyttsx3
    engine = pyttsx3.init()
    if voice_id:
        engine.setProperty("voice", voice_id)
    engine.setProperty("rate", rate)  # 每分钟字数
    engine.save_to_file(text, out_path)
    engine.runAndWait()


def tts_edge(text: str, out_path: str, voice: str = "zh-CN-YunxiNeural", rate: str = "+0%"):
    """
    用 edge-tts 生成音频（需网络，但音质接近真人）。
    安装：pip install edge-tts
    """
    import asyncio
    import edge_tts
    async def _generate():
        communicate = edge_tts.Communicate(text, voice, rate=rate)
        await communicate.save(out_path)
    asyncio.run(_generate())


def get_available_voices(tts_backend: str) -> list[str]:
    """列出可用语音，帮助用户选择。"""
    if tts_backend == "pyttsx3":
        import pyttsx3
        engine = pyttsx3.init()
        return [f"{v.id}  ({v.name})" for v in engine.getProperty("voices")]
    elif tts_backend == "edge":
        return ["zh-CN-YunxiNeural (男声, 沉稳)", "zh-CN-YunyangNeural (男声, 新闻)",
                "zh-CN-XiaoxiaoNeural (女声, 活泼)", "zh-CN-XiaoyiNeural (女声, 温柔)"]
    return []


# ---------------------------------------------------------------------------
# 4. 视频合成（ffmpeg）
# ---------------------------------------------------------------------------

def get_audio_duration(audio_path: str) -> float:
    """用 ffprobe 获取音频时长（秒）。"""
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", audio_path],
        capture_output=True, text=True
    )
    return float(result.stdout.strip())


def make_clip(image_path: str, audio_path: str, out_path: str,
               width: int = 1280, height: int = 720, fps: int = 24):
    """用单张图片 + 音频生成一段视频，图片持续时间 = 音频时长。"""
    cmd = [
        "ffmpeg", "-y", "-loop", "1", "-i", image_path,
        "-i", audio_path,
        "-c:v", "libx264", "-tune", "stillimage", "-preset", "medium", "-crf", "20",
        "-c:a", "aac", "-b:a", "192k",
        "-pix_fmt", "yuv420p", "-r", str(fps),
        "-vf", f"scale={width}:{height}:flags=lanczos",
        "-shortest", out_path
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg 生成片段失败: {result.stderr[-500:]}")


def concat_clips(clip_paths: list[str], out_path: str):
    """用 ffmpeg concat 无损拼接多段视频。"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        for cp in clip_paths:
            f.write(f"file '{os.path.abspath(cp)}'\n")
        list_path = f.name
    try:
        cmd = ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", list_path,
               "-c", "copy", out_path]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"ffmpeg 拼接失败: {result.stderr[-500:]}")
    finally:
        os.unlink(list_path)


# ---------------------------------------------------------------------------
# 5. 主流程
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="PPT 备注转讲解视频（本地离线版）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    parser.add_argument("pptx", help="输入 PPTX 文件路径")
    parser.add_argument("-o", "--output", default="output.mp4", help="输出视频路径（默认 output.mp4）")
    parser.add_argument("--tts", choices=["pyttsx3", "edge"], default="pyttsx3",
                        help="TTS 引擎：pyttsx3（离线）/ edge（需网络，音质更好）")
    parser.add_argument("--voice", default=None, help="语音 ID（不填用默认）")
    parser.add_argument("--rate", type=int, default=180, help="pyttsx3 语速：每分钟字数（默认180，正常150-200）")
    parser.add_argument("--edge-rate", default="+0%", help="edge-tts 语速调整，如 +20%% / -10%%")
    parser.add_argument("--width", type=int, default=1280, help="视频宽度（默认1280）")
    parser.add_argument("--height", type=int, default=720, help="视频高度（默认720）")
    parser.add_argument("--fps", type=int, default=24, help="帧率（默认24）")
    parser.add_argument("--dpi", type=int, default=150, help="PPT 截图 DPI（默认150）")
    parser.add_argument("--list-voices", action="store_true", help="列出可用语音后退出")
    parser.add_argument("--keep-temp", action="store_true", help="保留中间文件（音频/截图/片段）")

    args = parser.parse_args()

    # 列出语音
    if args.list_voices:
        print("可用语音：")
        for v in get_available_voices(args.tts):
            print(f"  - {v}")
        return

    # 检查输入
    if not os.path.isfile(args.pptx):
        print(f"错误：文件不存在 {args.pptx}", file=sys.stderr)
        sys.exit(1)

    # 检查 ffmpeg
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        print("错误：未找到 ffmpeg/ffprobe，请先安装 ffmpeg", file=sys.stderr)
        sys.exit(1)

    # 工作目录
    work_dir = tempfile.mkdtemp(prefix="ppt_narration_")
    audio_dir = os.path.join(work_dir, "audio")
    clip_dir = os.path.join(work_dir, "clips")
    img_dir = os.path.join(work_dir, "images")
    os.makedirs(audio_dir)
    os.makedirs(clip_dir)
    os.makedirs(img_dir)

    try:
        # Step 1: 提取备注
        print("=" * 60)
        print("Step 1/4  提取 PPT 备注")
        print("=" * 60)
        notes = extract_notes(args.pptx)
        print(f"共 {len(notes)} 页，已提取备注")

        # Step 2: PPT 截图
        print("\n" + "=" * 60)
        print("Step 2/4  PPT 逐页截图")
        print("=" * 60)
        images = pptx_to_images(args.pptx, img_dir, dpi=args.dpi)
        print(f"已生成 {len(images)} 页截图")
        if len(images) != len(notes):
            print(f"[警告] 截图页数({len(images)})与备注页数({len(notes)})不一致，以较少者为准")

        page_count = min(len(images), len(notes))

        # Step 3: TTS 生成音频
        print("\n" + "=" * 60)
        print(f"Step 3/4  语音合成（引擎: {args.tts}）")
        print("=" * 60)
        audio_paths = []
        for i in range(page_count):
            idx = i + 1
            audio_path = os.path.join(audio_dir, f"page{idx:02d}.wav")
            text = notes[i]
            print(f"  [{idx}/{page_count}] 生成旁白 ...", end=" ")
            if args.tts == "pyttsx3":
                tts_pyttsx3(text, audio_path, voice_id=args.voice, rate=args.rate)
            else:
                voice = args.voice or "zh-CN-YunxiNeural"
                tts_edge(text, audio_path, voice=voice, rate=args.edge_rate)
            dur = get_audio_duration(audio_path)
            print(f"{dur:.1f}s")
            audio_paths.append(audio_path)

        # Step 4: 合成视频
        print("\n" + "=" * 60)
        print("Step 4/4  合成视频")
        print("=" * 60)
        clip_paths = []
        for i in range(page_count):
            idx = i + 1
            clip_path = os.path.join(clip_dir, f"clip{idx:02d}.mp4")
            print(f"  [{idx}/{page_count}] 生成片段 ...", end=" ")
            make_clip(images[i], audio_paths[i], clip_path,
                      width=args.width, height=args.height, fps=args.fps)
            print("OK")
            clip_paths.append(clip_path)

        print("  拼接所有片段 ...")
        concat_clips(clip_paths, args.output)

        total_dur = get_audio_duration(args.output) if os.path.isfile(args.output) else 0
        print(f"\n{'=' * 60}")
        print(f"完成！输出: {os.path.abspath(args.output)}")
        print(f"总时长: {total_dur:.1f}s ({int(total_dur // 60)}分{int(total_dur % 60)}秒)")
        print(f"{'=' * 60}")

    finally:
        if args.keep_temp:
            print(f"\n中间文件保留在: {work_dir}")
        else:
            shutil.rmtree(work_dir, ignore_errors=True)


if __name__ == "__main__":
    main()
