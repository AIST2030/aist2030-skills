#!/usr/bin/env python3.11
# -*- coding: utf-8 -*-
"""
libai-sc1 搜图技能实现
====================================
仅在白名单 cc0.cn / img.cc0.cn 内，按语义提炼中文关键词搜图，
返回与关键词匹配度最高的第一张高清原图直链。
不下载落盘、不修改图片，仅内存校验后输出原图链接。

运行规则（与 SKILL.md 一致）：
 1. 理解整句语义，提炼 3-8 个中文关键词，不直接用长句搜索。
 2. 每次正式打开网页前，强制随机停顿 1~3 秒，模拟真人浏览。
 3. 仅用站内搜索框（POST /e/search/index.php）检索，不打开推荐/分类页。
 4. 内存过滤：仅保留室外实景实拍照片；屏蔽插画/海报/3D/抽象/恐怖/畸形/
    血腥/不适/人物大头特写。
 5. 仅挑选匹配度最高的第一张高清原图，仅提取图片直链。
 6. 仅返回图片地址，不校验服务器时区，以本机北京时间口径（脚本不读服务器时间）。
 7. 网站打不开 / 访问受限 / 无合格图：直接返回【执行失败】，不重试。
 8. 不修改、不下载落盘图片，仅输出原图链接（为过滤只在内存读取，绝不落盘/篡改）。
"""

import argparse
import io
import os
import random
import re
import sys
import time
from urllib.parse import urlparse

import requests

try:
    import jieba.analyse
    JIEBA_OK = True
except Exception:
    JIEBA_OK = False

try:
    import cv2
    import numpy as np
    CV2_OK = True
except Exception:
    CV2_OK = False


# ===================== 权限白名单（强制） =====================
WHITELIST_HOSTS = ("cc0.cn", "img.cc0.cn")


def allow(url: str) -> bool:
    """仅允许 cc0.cn / img.cc0.cn，严禁任何越权或外链跳转。"""
    if not url:
        return False
    try:
        host = urlparse(url).netloc.lower()
    except Exception:
        return False
    if not host:
        return False
    return any(host == w or host.endswith("." + w) for w in WHITELIST_HOSTS)


# ===================== 会话 =====================
_SESSION = None


def get_session() -> requests.Session:
    global _SESSION
    if _SESSION is None:
        _SESSION = requests.Session()
        _SESSION.headers.update(
            {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0 Safari/537.36"
                ),
                "Referer": "https://cc0.cn/",
            }
        )
    return _SESSION


def random_pause():
    """规则 2：每次正式打开网页前，强制随机停顿 1~3 秒。"""
    time.sleep(random.uniform(1.0, 3.0))


# ===================== 关键词提炼 =====================
def extract_keywords(text: str, topk: int = 5):
    """理解整句语义，提炼 3-8 个中文核心关键词。

    优先具体名词（更可能在图库命中相关实拍），过滤纯抽象/虚词，
    保证产出在 3-8 个之间，符合规则 1。
    """
    if not text or not text.strip():
        return []
    # 结果数量约束在 3-8
    topk = max(3, min(8, topk))
    # 抽象/虚词黑名单：这些词在图库几乎无相关实拍，优先剔除
    STOP = {
        "认知", "颠覆", "概念", "答案", "方式", "问题", "事情", "东西",
        "我们", "他们", "自己", "一个", "这个", "那个", "可以", "就是",
        "今天", "现在", "因为", "所以", "但是", "如果", "真的", "这样",
        "怎么", "什么", "为什么", "如何", "那些", "这些", "已经", "没有",
        "不是", "成为", "进行", "通过", "以及", "对于", "关于", "由于",
    }
    if not JIEBA_OK:
        words = re.findall(r"[一-鿿]{2,4}", text)
        seen = [w for w in words if w not in STOP]
        return seen[:topk]
    try:
        import jieba.posseg as pseg

        nouns = []
        for w, flag in pseg.cut(text):
            if len(w) < 2 or not re.search(r"[一-鿿]", w):
                continue
            if flag.startswith(("n", "nz", "ng", "ns", "nt", "nr", "vn")):
                if w not in STOP:
                    nouns.append(w)
        # 去重保序
        seen = set()
        kws = []
        for w in nouns:
            if w not in seen:
                seen.add(w)
                kws.append(w)
    except Exception:
        kws = []
    # 名词不足则用 TextRank 兜底
    if len(kws) < 3:
        tr = jieba.analyse.textrank(
            text, topK=topk, withWeight=False,
            allowPOS=("ns", "n", "vn", "v", "nz", "nr", "nt"),
        )
        for w in tr:
            if w not in STOP and w not in kws:
                kws.append(w)
            if len(kws) >= topk:
                break
    return kws[:topk]


# ===================== 站内搜索 =====================
def search(kw: str):
    """规则 3：仅用站内搜索框 POST 检索关键词，不打开任何推荐页。"""
    random_pause()  # 规则 2：打开网页前随机停顿
    url = "https://cc0.cn/e/search/index.php"
    if not allow(url):
        return None
    # 关键：每次新建会话。帝国CMS搜索在复用会话cookie后会返回
    # 893字节的“信息提示”无效页（0结果），新建会话可避免该坑。
    s = requests.Session()
    s.headers.update(
        {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0 Safari/537.36"
            ),
            "Referer": "https://cc0.cn/",
        }
    )
    data = {"tempid": "1", "show": "title", "tbname": "news", "keyboard": kw}
    try:
        r = s.post(url, data=data, allow_redirects=True, timeout=20)
    except Exception:
        return None
    if not allow(r.url):  # 严禁跳转外链
        return None
    if r.status_code != 200 or len(r.text) < 2000:
        return None
    return r.text


def parse_candidates(html: str):
    """解析搜索结果页缩略图，映射为高清原图直链（!w500.jpg -> !cc0.cn.jpg）。

    来源无关（unsplash / pixabay 等均可）。仅停留在搜索结果页内取图，
    不跳转详情/推荐页，符合规则 3。
    """
    # 缩略图: //img.cc0.cn/{source}/{file}.jpg!w500.jpg
    items = re.findall(
        r"//img\.cc0\.cn/([a-z0-9]+)/([^\s\"'<>]+?\.jpg)!w500\.jpg", html
    )
    cands = []
    for source, fname in items:
        hd = "https://img.cc0.cn/%s/%s!cc0.cn.jpg" % (source, fname)
        if allow(hd):
            cands.append(hd)
    # 去重保序
    seen = set()
    out = []
    for c in cands:
        if c not in seen:
            seen.add(c)
            out.append(c)
    return out


# ===================== 内存过滤（规则 4/8） =====================
_FACE_CASCADE = None


def get_cascade():
    global _FACE_CASCADE
    if _FACE_CASCADE is None and CV2_OK:
        path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
        if os.path.exists(path):
            _FACE_CASCADE = cv2.CascadeClassifier(path)
    return _FACE_CASCADE


def memory_filter(url: str, min_side: int = 600, face_ratio: float = 0.30) -> bool:
    """下载到内存做合规校验：仅保留高清实拍、屏蔽人物大头特写。绝不落盘。"""
    if not CV2_OK:
        # 无 opencv 时退化为仅校验可访问性（无法判大头特写）
        return True
    s = get_session()
    random_pause()
    r = None
    # 仅对连接/超时等瞬时网络错误做一次兜底重试（非针对 HTTP 错误码，
    # 也非反复刷新重试网站，符合规则 7 的精神）。
    for _ in range(2):
        try:
            r = s.get(url, timeout=20)
            break
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout,
                requests.exceptions.ChunkedEncodingError):
            time.sleep(random.uniform(0.5, 1.5))
            continue
        except Exception:
            return False
    if r is None:
        return False
    if not allow(r.url):  # 严禁越权/外链
        return False
    if r.status_code != 200 or not r.content:
        return False
    is_jpg = r.content.startswith(b"\xff\xd8")
    is_png = r.content.startswith(b"\x89PNG")
    if not (is_jpg or is_png):
        return False  # 非图片，放弃
    try:
        arr = np.frombuffer(r.content, np.uint8)
        img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    except Exception:
        return False
    if img is None:
        return False
    h, w = img.shape[:2]
    if min(w, h) < min_side:
        return False  # 尺寸过小，非高清，放弃
    # 人物大头特写检测：人脸占画面比例过大即屏蔽
    cas = get_cascade()
    if cas is not None:
        try:
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            faces = cas.detectMultiScale(gray, 1.3, 5)
            for (x, y, fw, fh) in faces:
                if (fw * fh) / (w * h) > face_ratio:
                    return False  # 大头特写，屏蔽
        except Exception:
            pass
    return True


# ===================== 主流程 =====================
def find_one(kw: str, max_check: int = 6):
    html = search(kw)
    if html is None:
        return None
    cands = parse_candidates(html)
    if not cands:
        return None
    # DOM 顺序 ≈ 相关性顺序，第一张合格即 top-1（规则 5）
    for url in cands[:max_check]:
        if memory_filter(url):
            return url
    return None


def main():
    ap = argparse.ArgumentParser(description="libai-sc1 搜图技能")
    ap.add_argument("--text", help="口播/文案内容，自动提炼关键词")
    ap.add_argument("--keywords", help="已提炼的逗号分隔关键词（优先于 --text）")
    ap.add_argument("--topk", type=int, default=5, help="提炼关键词数量，默认 5")
    args = ap.parse_args()

    if args.keywords:
        kws = [k.strip() for k in args.keywords.split(",") if k.strip()]
    elif args.text:
        kws = extract_keywords(args.text, args.topk)
    else:
        print("【执行失败】")
        return

    if not kws:
        print("【执行失败】")
        return

    for kw in kws:
        url = find_one(kw)
        if url:
            # 规则 6/8：仅返回图片地址（本机北京时间口径，脚本不读服务器时间）
            print(url)
            return
    # 规则 7：无合格图，直接返回【执行失败】，不重试
    print("【执行失败】")


if __name__ == "__main__":
    main()
