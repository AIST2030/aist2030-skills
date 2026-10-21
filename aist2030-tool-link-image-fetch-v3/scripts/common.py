#!/usr/bin/env python3
"""共享能力: URL 清洗 / 哈希提取 / 下载去重 / OpenCV 去水印兜底。

设计原则:
- 正常流程(raw 原图)不依赖任何第三方库;
- OpenCV 仅在使用 inpainting 兜底时按需 import, 缺失则跳过并提示安装。
"""
import os
import re
import urllib.request
import urllib.error


def clean_url(url):
    """清理 CDN URL 末尾的多余转义字符。"""
    if not url:
        return url
    return url.strip().rstrip('\\').strip('"').rstrip('\\')


def hash_from_url(url):
    """从图片 URL 提取 32 位 hash(兼容 rc_gen_image/<hash> 或 /<hash>.(ext))。"""
    if not url:
        return ''
    m = re.search(r'rc_gen_image/([a-f0-9]{32})', url)
    if m:
        return m.group(1)
    m = re.search(r'/([a-f0-9]{32})\.(?:jpeg|png|jpg)', url)
    if m:
        return m.group(1)
    return ''


def remove_watermark_cv(src_path, dst_path):
    """兜底去水印: 对简单角标水印(如右下角平台标识)做 OpenCV inpainting。

    仅当平台原图(raw)不可用时调用。需环境安装 opencv-python。
    返回 dst_path; 任何异常向上抛出由调用方处理。
    """
    try:
        import cv2
        import numpy as np
    except ImportError:
        raise RuntimeError("去水印兜底需要 opencv-python, 请先: pip install opencv-python")
    img = cv2.imread(src_path)
    if img is None:
        raise RuntimeError(f"无法读取图片: {src_path}")
    h, w = img.shape[:2]
    # 掩膜覆盖常见角标位置: 右下角 + 左下角
    mask = np.zeros((h, w), dtype=np.uint8)
    bw, bh = max(60, w // 4), max(60, h // 7)
    mask[h - bh:h, w - bw:w] = 255
    mask[h - bh:h, 0:bw] = 255
    res = cv2.inpaint(img, mask, 3, cv2.INPAINT_TELEA)
    cv2.imwrite(dst_path, res)
    return dst_path


def sniff_ext(data):
    """按文件头嗅探真实后缀, 避免一律存成 .png 导致看图软件误判。"""
    if data[:8] == b'\x89PNG\r\n\x1a\n':
        return 'png'
    if data[:3] == b'\xff\xd8\xff':
        return 'jpg'
    if data[:6] in (b'GIF87a', b'GIF89a'):
        return 'gif'
    if data[:4] == b'RIFF' and data[8:12] == b'WEBP':
        return 'webp'
    if data[:2] == b'BM':
        return 'bmp'
    return 'png'


def _fetch(url, referer):
    req = urllib.request.Request(url, headers={
        'User-Agent': 'Mozilla/5.0',
        'Referer': referer,
    })
    with urllib.request.urlopen(req, timeout=90) as r:
        return r.read()


def _save(url, fpath, referer):
    """下载并按真实格式落盘, 返回最终文件路径。"""
    base = fpath[:-4] if fpath.endswith('.png') else fpath
    data = _fetch(url, referer)
    final = base + '.' + sniff_ext(data)
    with open(final, 'wb') as f:
        f.write(data)
    return final


def download_images(entries, output_dir, referer, try_inpaint=True):
    """去重并下载所有图片。

    entries: list of {'hash','raw_url','wm_url'}
    - 优先 raw_url(平台原图, 无水印)
    - raw 失败则回退 wm_url(平台水印版), 并尝试 OpenCV 去水印
    """
    os.makedirs(output_dir, exist_ok=True)
    seen = set()
    ok = fail = wm_fb = inpainted = 0

    for i, e in enumerate(entries):
        raw_url = e.get('raw_url')
        wm_url = e.get('wm_url')

        if raw_url and raw_url not in seen:
            url, is_wm = raw_url, False
        elif wm_url and wm_url not in seen:
            url, is_wm = wm_url, True
        else:
            continue
        seen.add(url)

        h = (e.get('hash') or f'{i}')[:12]
        stem = f'{i:02d}_{h}'
        fpath = os.path.join(output_dir, stem + '.png')
        # 平台适配器可声明 'skip_inpaint': True (如微信: 文章图本身无角标水印,
        # 再做 inpainting 只会糊掉边角)
        do_inpaint = try_inpaint and not e.get('skip_inpaint')

        def _inpaint(path):
            if not do_inpaint:
                return False
            try:
                tmp = path.rsplit('.', 1)[0] + '_nowm.png'
                remove_watermark_cv(path, tmp)
                os.replace(tmp, path)
                return True
            except Exception as ex:
                print(f'     ↳ 去水印兜底跳过: {ex}')
                return False

        try:
            fpath = _save(url, fpath, referer)
            tag = '[WM]' if is_wm else '[OK]'
            print(f'{tag} {os.path.basename(fpath)} ({os.path.getsize(fpath) // 1024} KB)')
            ok += 1
            if is_wm:
                wm_fb += 1
                if _inpaint(fpath):
                    print('     ↳ OpenCV 去水印完成(角标已抹除)')
                    inpainted += 1
            continue
        except Exception as ex:
            print(f'[FAIL raw] {h}: {ex}')

        # raw 失败 -> wm 兜底
        if not is_wm and wm_url and wm_url not in seen:
            seen.add(wm_url)
            try:
                fpath = _save(wm_url, fpath, referer)
                print(f'[WM-FB] {os.path.basename(fpath)} '
                      f'({os.path.getsize(fpath) // 1024} KB, 平台水印版兜底)')
                ok += 1
                wm_fb += 1
                if _inpaint(fpath):
                    print('     ↳ OpenCV 去水印完成')
                    inpainted += 1
                continue
            except Exception as ex3:
                print(f'[FAIL wm] {h}: {ex3}')
        fail += 1

    print(f'\n完成! 成功: {ok} (含水印版兜底 {wm_fb}, OpenCV去水印 {inpainted}), '
          f'失败: {fail}, 总计引用: {len(entries)}')
    print(f'输出目录: {os.path.abspath(output_dir)}')
    return ok
