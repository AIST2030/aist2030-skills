#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
fetch_media.py —— 文案直出视频产线的「素材通道 A」实现。

职责：按 shotplan.json 里每个镜头的检索词，到白名单站点抓免费可商用**视频**素材，
下载、静音、烘调色（饱和度/对比度 + 背景柔化模糊）、裁切到目标比例，
落盘到 public/media/ 并回报清单。

★ 2026-10-17 起**只采集视频，不采集图片**（用户明令）：
  静态图做垫片既无信息量又拖节奏；且曾因"疑似图片导致卡顿"被排查过
  （结论：卡顿真因是渲染层 CSS filter，图片通道整体移除以防再混入）。
  实拍层全部由本脚本的视频路径负责。

白名单（本机实测）：
  - Mixkit 视频  ✅  https://mixkit.co/free-stock-video/<category>/
      ⚠ 搜索页不可用（`?q=` 与 `/search/?s=` 都返回首页推荐，换词 id 不变），
      只能用**分类页**与精选详情页（slug）。
      直链规律 assets.mixkit.co/videos/<id>/<id>-{360|720|1080}.mp4
      支持 Range（206）。
  - Pixabay / aigei ❌ 403（带 UA 也拦），Pexels 需 API key —— 本脚本不碰。

用法：
  python fetch_media.py --plan shotplan.json --out <项目>/remotion/public/media
                        [--ffmpeg <path>] [--only p2,p3] [--force]
输出：
  media_manifest.json  —— 每镜拿到/没拿到什么，供下游 Remotion 与 QC 使用
"""
import argparse
import json
import os
import random
import re
import subprocess
import sys
import time
import urllib.parse
import urllib.request

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")


def _http(url, data=None, timeout=25, referer=None, binary=False):
    """统一出口：带 UA / Referer，可选 POST。返回 (bytes, err)。"""
    headers = {
        "User-Agent": UA,
        "Accept-Language": "zh-CN,zh;q=0.9",
    }
    if referer:
        headers["Referer"] = referer
    if data is not None:
        headers["Content-Type"] = "application/x-www-form-urlencoded"
        data = urllib.parse.urlencode(data).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers)
    try:
        raw = urllib.request.urlopen(req, timeout=timeout).read()
        return (raw if binary else raw.decode("utf-8", "ignore")), None
    except Exception as e:
        return None, str(e)


def human_pause(lo=1.0, hi=3.0):
    """模拟真人节流，禁止机器连续请求。"""
    time.sleep(random.uniform(lo, hi))


# ---------------------------------------------------------------- Mixkit 视频
#
# ⚠ 重要实测结论（2026-10-17，别再走弯路）：
#
#   Mixkit 的**搜索是 SPA + JS 渲染的，静态抓取拿不到真结果**。
#   以下两种"看起来对"的搜法返回的都是**首页推荐列表**（换关键词 ID 完全不变）：
#       /free-stock-video/?q=<kw>            ← 常见误解，无效
#       /free-stock-video/search/?s=<kw>     ← 表单字段名确实是 s，但 SEO 页面也不含结果
#   即使用 Chrome --headless --dump-dom 渲染，搜索页拿到的仍是推荐位。
#
#   真正静态可靠的两条通道：
#     A) 主题分类页  /free-stock-video/<category>/      ← 各分类返回不同视频，主题相关
#     B) 精选视频页  /free-stock-video/<slug>/          ← 如 hands-of-a-person-typing-on-a-cell-phone-4915
#        首页导航里挂着约 30 个具体视频 slug，**这类 slug 直接可读且能换分辨率档**。
#        这是语义匹配度最高的来源，优先用。
#
#   已知可用分类（实测 200 + 内容各异）：
MIXKIT_CATEGORIES = [
    "abstract", "aerial", "airplane", "animal", "baby", "background", "beach",
    "bicycle", "bird", "business", "car", "cat", "christmas", "city", "cloud",
    "coffee", "countdown", "couple", "dance", "dog", "double-exposure", "drink",
    "drive", "earth", "eating", "family", "fashion", "fast-food", "fire", "fish",
    "flower", "food", "forest", "funny", "girl", "green-screen", "house", "intro",
    "kiss", "kitten", "lifestyle", "light", "love", "man", "monkey", "motorcycle",
    "music", "nature", "night", "party", "people", "pet", "rain", "restaurant",
    "road", "romance", "safari", "sea", "sky", "smoke", "snow", "space", "spark",
    "sport", "street", "sun", "sunset", "taxi", "tea", "technology", "traffic",
    "trains", "transport", "water", "wildlife", "woman",
]

# ★ 实拍白名单（2026-10-17 抽帧实测）：这些分类下是真人/真实场景素材，
#   与「深蓝黑+暖金」品牌基调兼容。分镜优先从这里选。
REAL_FOOTAGE_CATS = {
    "business": "办公/会议/团队", "people": "人群/社交", "man": "男性人物",
    "woman": "女性人物", "girl": "年轻女性", "family": "家庭场景",
    "couple": "情侣", "baby": "亲子", "lifestyle": "日常生活",
    "street": "街道人流", "city": "城市", "night": "夜景", "traffic": "车流",
    "road": "道路延伸", "drive": "驾驶", "car": "汽车", "transport": "交通",
    "taxi": "出租车", "trains": "火车", "coffee": "咖啡/休闲",
    "restaurant": "餐厅", "food": "食物", "eating": "进食",
    "house": "居家室内", "music": "音乐", "dance": "舞蹈", "party": "聚会",
    "sport": "运动", "fire": "火焰", "smoke": "烟雾", "spark": "火花",
    "rain": "雨", "water": "水", "sea": "海", "sky": "天空", "cloud": "云",
    "sun": "太阳", "sunset": "落日", "beach": "海滩", "forest": "森林",
    "nature": "自然", "snow": "雪", "animal": "动物", "dog": "狗", "cat": "猫",
    "pet": "宠物", "wildlife": "野生动物", "fashion": "时尚",
}

# ★ 3D 渲染/合成素材黑名单（实测踩坑）：这些分类下大量是 CG 渲染
#   （粉色/紫色块、粒子特效），与品牌蓝金基调冲突，观感廉价。
#   p3_s1 曾用 technology 拿到粉色 3D 渲染，抽帧发现后整组换掉。
RENDER_3D_CATS = {
    "technology", "abstract", "light", "ai-generated", "double-exposure",
    "background", "intro", "countdown", "green-screen", "earth", "space",
}


def mixkit_items(page_url, want=6):
    """
    抓 Mixkit 任意页面（分类页 / 精选视频页 / 首页）里的视频条目。
    返回 [(video_id, ...)]，按页面出现顺序去重。
    """
    html, err = _http(page_url)
    if err or not html:
        return [], err or "empty"
    ids = re.findall(r'data-item-grid--video-player-item-id-value="(\d+)"', html)
    if not ids:
        # 退回资源直链形态（部分页面只有 assets.mixkit.co/videos/<id>/...）
        ids = re.findall(r"assets\.mixkit\.co/videos/(\d+)/", html)
    out, seen = [], set()
    for vid in ids:
        if vid in seen:
            continue
        seen.add(vid)
        out.append(vid)
        if len(out) >= want:
            break
    return out, None


def mixkit_url_map(page_url):
    """
    从页面提取 {vid: {分辨率: 直链}}，**两种直链格式都覆盖**：

      A) assets.mixkit.co/videos/<id>/<id>-<res>.mp4                （多为 5 位 id）
      B) assets.mixkit.co/active_storage/video_items/<id>/<ts>/<id>-video-<res>.mp4
                                                                    （多为 6 位 id，如 100417）
    ⚠ 实测坑：只按 A 格式拼 URL，6 位 id 会全部 404（p3_s0/p3_s2 就这样失败过）。
      所以**不要在分配阶段靠猜格式**，直接从页面 HTML 里把真实直链读出来。
    """
    html, err = _http(page_url)
    if not html:
        return {}, err or "empty"
    m = {}
    for vid, res in re.findall(
            r"assets\.mixkit\.co/videos/(\d+)/\1-(\d+)\.mp4", html):
        m.setdefault(vid, {})[int(res)] = \
            f"https://assets.mixkit.co/videos/{vid}/{vid}-{res}.mp4"
    for vid, ts, res in re.findall(
            r"assets\.mixkit\.co/active_storage/video_items/(\d+)/(\d+)/\1-video-(\d+)\.mp4",
            html):
        m.setdefault(vid, {})[int(res)] = (
            f"https://assets.mixkit.co/active_storage/video_items/"
            f"{vid}/{ts}/{vid}-video-{res}.mp4")
    return m, None


def pick_best_res(res_map):
    """从 {res: url} 里挑最合适的一档：优先 720（体积/速度平衡）。"""
    for r in (720, 1080, 360, 540, 240):
        if r in res_map:
            return res_map[r], r
    if res_map:
        r = max(res_map)
        return res_map[r], r
    return None, None


def mixkit_by_category(category, want=6):
    """按主题分类取视频条目。"""
    if category not in MIXKIT_CATEGORIES:
        # 容忍拼写/未知词：仍尝试直接访问，失败由调用方回退
        pass
    return mixkit_items(
        f"https://mixkit.co/free-stock-video/{category}/?ref=wb", want)


def mixkit_by_slug(slug, want=6):
    """按精选视频页 slug 取条目（语义最准的一条通道）。"""
    return mixkit_items(f"https://mixkit.co/free-stock-video/{slug}/", want)


# 关键词 → 分类 的兜底映射：让 shotplan 写自然语言也能落到分类上
KEYWORD_TO_CATEGORY = {
    "office": "business", "desk": "business", "meeting": "business",
    "team": "business", "work": "business", "business": "business",
    "formal": "business", "suit": "business", "handshake": "business",
    "phone": "technology", "smartphone": "technology", "mobile": "technology",
    "laptop": "technology", "computer": "technology", "screen": "technology",
    "typing": "technology", "keyboard": "technology", "server": "technology",
    "data": "technology", "tech": "technology", "digital": "technology",
    "app": "technology", "code": "technology", "abstract": "abstract",
    "particle": "abstract", "light": "light", "glow": "light",
    "city": "city", "urban": "city", "skyline": "city", "downtown": "city",
    "night": "night", "neon": "night", "people": "people", "person": "people",
    "crowd": "people", "crowds": "people", "walking": "street", "street": "street",
    "lifestyle": "lifestyle", "home": "house", "space": "space",
    "star": "space", "earth": "earth", "network": "spark", "connection": "spark",
}


def mixkit_resolve(query):
    """
    把 shotplan 里的一条 query 解析成 (mode, value)：
      - 若形如 'cat:business'  → ('category', 'business')
      - 若形如 'slug:hands-of-a-person...'  → ('slug', '...')
      - 否则先精确匹配分类名；再按词命中性映射到分类；最后回落 technology。
    """
    q = (query or "").strip().lower()
    if q.startswith("cat:"):
        return "category", q[4:].strip()
    if q.startswith("slug:"):
        return "slug", q[5:].strip()
    if q in MIXKIT_CATEGORIES:
        return "category", q
    # 多词 query：逐个词查映射表
    for token in re.split(r"[\s,/]+", q):
        if token in KEYWORD_TO_CATEGORY:
            return "category", KEYWORD_TO_CATEGORY[token]
    for token in re.split(r"[\s,/]+", q):
        if token in MIXKIT_CATEGORIES:
            return "category", token
    return "category", "technology"


def category_warning(cat):
    """3D 渲染黑名单分类警告（分镜选错时的显式提示）。"""
    if cat in RENDER_3D_CATS:
        return (f"⚠ 「{cat}」是 3D 渲染/合成素材向，与实拍基调冲突；"
                f"建议换实拍分类，如 " +
                " / ".join(list(REAL_FOOTAGE_CATS)[:6]) + " …")
    return None


def mixkit_best_url(vid, res_hint=360, prefer=(720, 1080, 360)):
    """按 prefer 顺序试探可用分辨率档。

    ⚠ 默认先试 720 而不是 1080：实测 1080 单条下载+转码约 2 分钟，
    22 个镜头串行要 40+ 分钟；720 体积小一半、速度翻倍，
    1080x1440 成片里放大也看不出明显损失。
    """
    """按 prefer 顺序试探可用分辨率档，返回 (url, res) 或 (None, None)。"""
    for r in prefer:
        u = f"https://assets.mixkit.co/videos/{vid}/{vid}-{r}.mp4"
        req = urllib.request.Request(u, headers={"User-Agent": UA}, method="HEAD")
        try:
            resp = urllib.request.urlopen(req, timeout=15)
            if resp.status in (200, 206):
                return u, r
        except Exception:
            continue
    return None, None


def download(url, dst, timeout=90):
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=timeout) as r, open(dst, "wb") as f:
                while True:
                    chunk = r.read(262144)
                    if not chunk:
                        break
                    f.write(chunk)
            if os.path.getsize(dst) > 1024:
                return True
        except Exception:
            if os.path.exists(dst):
                try:
                    os.remove(dst)
                except OSError:
                    pass
            time.sleep(1.5 * (attempt + 1))
    return False


def ffmpeg_run(ffmpeg, args, quiet=True):
    cmd = [ffmpeg, "-y"] + args
    if quiet:
        cmd += ["-loglevel", "error"]
    try:
        p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=600)
        return p.returncode == 0, p.stderr.decode("utf-8", "ignore")[-800:]
    except Exception as e:
        return False, str(e)


def prep_video(ffmpeg, src, dst, w, h, fps, dur=None, soft=True):
    """裁切填充到目标画幅 + 静音 + 统一 30fps + **烘调色** + 背景柔化。

    ★ 为什么把调色烘进 ffmpeg 而不是渲染层 CSS filter（2026-10-17 踩坑）：
      早期在 Remotion 里给视频容器加 `filter: saturate(.62) contrast(1.06)`，
      外加一层 `mixBlendMode: screen` 全屏染色 —— Chrome 渲染时视频层
      每帧被迫重新光栅化，1080×1440 下成片出现明显卡顿。
      烘进转码后渲染层只剩廉价渐变叠加，零成本。
    ★ soft：轻高斯模糊（sigma≈2.5）。2026-10-17 用户反馈"背景看不到视频"——
      早期 sigma=6 + 饱和度 0.62 把实拍糊成一片色块，视频失去观赏性。
      现改为轻柔化（保留质感）+ 降饱和（0.82）+ 微提对比（1.10）。

    ★★ 血泪坑（2026-10-17 二次事故）：ffmpeg `eq` 的 **brightness 是加法偏移，
      取值范围 -1.0~1.0，不是乘法系数**。曾写 `brightness=1.08` → 整幅 +275，
      21 个素材全被冲成纯白（亮度均值 255/255），成片背景变成一片灰白雾。
      要提亮/压影调一律用 `gamma`（<1 压暗中间调）或 `contrast`，**不要再碰 brightness**。
    """
    vf = (f"scale={w}:{h}:force_original_aspect_ratio=increase,"
          f"crop={w}:{h},fps={fps}")
    if soft:
        vf += ",gblur=sigma=2.5"
    vf += (",eq=saturation=0.82:contrast=1.10:gamma=0.96"
           ",format=yuv420p")
    args = ["-i", src, "-an", "-vf", vf]
    if dur:
        args += ["-t", str(dur)]
    args += ["-c:v", "libx264", "-preset", "veryfast", "-crf", "23", dst]
    return ffmpeg_run(ffmpeg, args)


# ---------------------------------------------------------------- 主流程
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--plan", required=True, help="shotplan.json 路径")
    ap.add_argument("--out", required=True, help="素材落盘目录（通常 remotion/public/media）")
    ap.add_argument("--ffmpeg", default=None)
    ap.add_argument("--w", type=int, default=1080)
    ap.add_argument("--h", type=int, default=1440)
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--only", default="", help="只处理这些页，逗号分隔，如 p2,p3")
    ap.add_argument("--force", action="store_true", help="忽略已有文件，强制重下")
    ap.add_argument("--custom", default="",
                    help="用户自定义素材目录：放 p{page}.mp4 或 {shot}.mp4，"
                         "命中则优先于 Mixkit 使用（不联网下载）")
    ap.add_argument("--assign-only", action="store_true",
                    help="只做素材预分配（解析分类→锁定 video id），不下载。"
                         "多进程并行前必须先跑一次，避免各进程重复选到同一视频。")
    args = ap.parse_args()

    if not args.ffmpeg:
        try:
            import imageio_ffmpeg
            args.ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
        except Exception:
            print("[FATAL] 未指定 --ffmpeg 且 imageio_ffmpeg 不可用")
            sys.exit(2)

    with open(args.plan, "r", encoding="utf-8") as f:
        plan = json.load(f)

    os.makedirs(args.out, exist_ok=True)
    raw_dir = os.path.join(args.out, "_raw")
    os.makedirs(raw_dir, exist_ok=True)

    only = [s.strip() for s in args.only.split(",") if s.strip()]
    shots = plan.get("shots", [])
    if only:
        # ★ 兼容两种 shot 结构：
        #   ① {"id":"p24","media":{...}}            —— 本项目一页一镜的写法
        #   ② {"page":"p24","shots":[...]}            —— 多镜头分镜写法
        #   早期只按 s.get("page") 过滤，遇到①这种没有 page 字段的会全被滤掉，
        #   表现为「待处理镜头 0 个」——静默失败，很容易被误判成没活干。
        only_set = set(only)
        shots = [s for s in shots
                 if s.get("id") in only_set or s.get("page") in only_set]

    # ---- 素材预分配表（多进程并行的前提）----
    asg_path = os.path.join(args.out, "_assignment.json")
    assignment = {}
    if os.path.exists(asg_path):
        try:
            with open(asg_path, "r", encoding="utf-8") as f:
                assignment = json.load(f)
        except Exception:
            assignment = {}

    if args.assign_only:
        used = set()
        for v in assignment.values():
            used.add(v["vid"] if isinstance(v, dict) else v)
        # 同一分类只抓一次页面，按需在多个镜头间顺延取不同视频
        page_cache = {}
        for s in plan.get("shots", []):
            sid = s.get("id")
            mm = s.get("media", {})
            if mm.get("type") != "video" or not mm.get("query") or sid in assignment:
                continue
            mode, val = mixkit_resolve(mm["query"])
            page_url = (f"https://mixkit.co/free-stock-video/{val}/"
                        if mode != "slug"
                        else f"https://mixkit.co/free-stock-video/{val}/")
            if page_url not in page_cache:
                umap, err = mixkit_url_map(page_url)
                page_cache[page_url] = umap
                print(f"  [cache] {val:12s} 页内视频 {len(umap)} 个 {err or ''}")
                human_pause()
            umap = page_cache[page_url]
            for vid, res_map in umap.items():
                if vid in used:
                    continue
                url, res = pick_best_res(res_map)
                if not url:
                    continue
                assignment[sid] = {"vid": vid, "url": url, "res": res,
                                   "cat": val}
                used.add(vid)
                print(f"  {sid:8s} {val:12s} → vid={vid} ({res}p)")
                break
        with open(asg_path, "w", encoding="utf-8") as f:
            json.dump(assignment, f, ensure_ascii=False, indent=2)
        miss = [s["id"] for s in plan.get("shots", [])
                if s.get("media", {}).get("type") == "video"
                and s["id"] not in assignment]
        print(f"[assign] 已分配 {len(assignment)} 个镜头 → {asg_path}")
        if miss:
            print(f"[assign] ⚠ 未分配: {miss}")
        return

    manifest = {"generated": time.strftime("%Y-%m-%d %H:%M:%S"),
                "size": [args.w, args.h], "fps": args.fps, "items": []}

    # ★ 全片素材去重：同一分类下多个镜头必须拿到**不同**视频，
    #   否则 21 个镜头会出现大量重复画面（观感立刻崩）。
    used_vids = set()
    # 跨进程去重：读已存在的 manifest，把已用过的 video id 也记进来
    prev_mp = os.path.join(args.out, "media_manifest.json")
    if os.path.exists(prev_mp):
        try:
            with open(prev_mp, "r", encoding="utf-8") as f:
                for it in json.load(f).get("items", []):
                    if it.get("vid"):
                        used_vids.add(str(it["vid"]))
        except Exception:
            pass

    total = len(shots)
    print(f"[plan] 待处理镜头 {total} 个 / 输出 {args.out}")
    for i, s in enumerate(shots, 1):
        sid = s.get("id")
        mtype = s.get("media", {}).get("type", "none")
        query = s.get("media", {}).get("query")
        if mtype == "none" or not query:
            manifest["items"].append({"id": sid, "type": mtype, "ok": False,
                                      "note": "pure-graphic shot"})
            continue

        dst = os.path.join(args.out, f"{sid}.mp4" if mtype == "video" else f"{sid}.jpg")
        rel = f"media/{os.path.basename(dst)}"
        if os.path.exists(dst) and not args.force:
            manifest["items"].append({"id": sid, "type": mtype, "ok": True,
                                      "file": rel, "query": query, "note": "cached"})
            print(f"  [{i}/{total}] {sid} 已存在，跳过")
            continue

        # ---- 用户自定义素材通道（优先于 Mixkit，命中即跳过联网）----
        if args.custom:
            page_id = sid.split("_")[0]
            cands = [os.path.join(args.custom, f"{sid}.mp4"),
                     os.path.join(args.custom, f"{page_id}.mp4")]
            csrc = next((c for c in cands if os.path.exists(c)), None)
            if csrc:
                _base, _ext = os.path.splitext(dst)
                _dp = f"{_base}.part{_ext}"
                ok, msg = prep_video(args.ffmpeg, csrc, _dp,
                                     args.w, args.h, args.fps)
                if ok:
                    os.replace(_dp, dst)
                    manifest["items"].append({
                        "id": sid, "type": mtype, "query": query,
                        "ok": True, "file": rel, "source": f"custom:{csrc}",
                        "vid": "custom"})
                    used_vids.add("custom")
                    print(f"      ✔ 自定义素材 {csrc}")
                    continue
                print(f"      ✘ 自定义转码失败 {msg[:120]}")

        print(f"  [{i}/{total}] {sid} ({mtype}) 检索「{query}」")
        human_pause()
        got = False
        src_url = None
        if mtype != "video":
            # 2026-10-17 起只采集视频；图片通道已移除，这里显式跳过并告知
            print("      ⚠ 本产线只采集视频素材，image 类型已废弃，跳过")
            manifest["items"].append({"id": sid, "type": mtype, "query": query,
                                      "ok": False, "file": None,
                                      "source": None, "vid": None})
            continue
        _warn = category_warning(query.strip().lower())
        if _warn:
            print(f"      {_warn}")
        # ⚠ 原子落盘：先写临时名，成功后再 rename。
        # 否则并发渲染时 Remotion 会加载到"半成品 mp4"，Video 组件卡死
        # → 整帧渲染 timeout（实测踩过：1600 帧挂在这一条）。
        # ⚠⚠ 临时名必须**保留原扩展名**：写成 p1_s0.mp4.part 会让 ffmpeg
        #     报 "Unable to choose an output format"（实测踩过，全片 0/21 失败）。
        _base, _ext = os.path.splitext(dst)
        dst_part = f"{_base}.part{_ext}"

        preset_url = None
        if sid in assignment:
            a = assignment[sid]
            if isinstance(a, dict):
                vids, preset_url = [a["vid"]], a.get("url")
                print(f"      → 预分配 vid={a['vid']} ({a.get('res')}p)")
            else:
                vids = [a]
                print(f"      → 预分配 vid={a}")
        else:
            mode, val = mixkit_resolve(query)
            print(f"      → {mode}={val}")
            vids, err = (mixkit_by_slug(val) if mode == "slug"
                         else mixkit_by_category(val))
            if err:
                print(f"      mixkit 检索失败: {err}")
        for vid in vids:
            if vid in used_vids:
                continue  # 已被别的镜头占了，换下一个，避免画面重复
            if preset_url:
                # 分配阶段已从页面读到真实直链，直接下，不用猜格式
                u, r = preset_url, None
            else:
                u, r = mixkit_best_url(vid)
            if not u:
                continue
            tmp = os.path.join(raw_dir, f"{sid}_{vid}_{r or 'hd'}.mp4")
            # raw 缓存复用：曾下过的原片直接拿来转码，不重复下载
            # （换转码参数——如本次烘调色——时全量重转但不重下）
            if not os.path.exists(tmp):
                cached = [f for f in os.listdir(raw_dir)
                          if f.startswith(f"{sid}_{vid}_") and f.endswith(".mp4")]
                if cached:
                    tmp = os.path.join(raw_dir, cached[0])
                    print(f"      ↺ raw 缓存复用 {cached[0]}")
            if not os.path.exists(tmp) and not download(u, tmp):
                continue
            ok, msg = prep_video(args.ffmpeg, tmp, dst_part, args.w, args.h, args.fps)
            if ok:
                os.replace(dst_part, dst)
                got, src_url = True, u
                used_vids.add(vid)
                print(f"      ✔ {u}")
                break
            print(f"      ✘ 转码失败 {msg[:120]}")

        vid_used = None
        if src_url:
            m = re.search(r"/videos/(\d+)/", src_url)
            if m:
                vid_used = m.group(1)
        manifest["items"].append({
            "id": sid, "type": mtype, "query": query,
            "ok": got, "file": rel if got else None, "source": src_url,
            "vid": vid_used,
        })
        if not got:
            print(f"      ⚠ {sid} 未拿到素材，下游将回退到纯图形层")

    mp = os.path.join(args.out, "media_manifest.json")
    with open(mp, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    ok_n = sum(1 for it in manifest["items"] if it["ok"])
    print(f"[done] 成功 {ok_n}/{len(manifest['items'])} → {mp}")


if __name__ == "__main__":
    main()
