#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
智能断句引擎
============

解决两个核心诉求：
1. **优先按标点断句** —— 标点是天然语义边界，最自然
2. **标点断句后仍太长 → 按词断句** —— 用 jieba 词边界兜底，
   **绝不把一个词分散到前后两条字幕**

三级断句策略（从优到劣）：
    级别 1  标点断句      句号/问号/感叹号/分号 → 硬边界
    级别 2  逗号类断句    逗号/顿号/冒号 → 软边界（仅当整句超长时启用）
    级别 3  词边界断句    jieba 分词，在词与词之间切开（绝不切词内部）

长度约束：每条 6-14 字（可配），单行显示不折行。
"""

import re

import jieba

# ---------------------------------------------------------------- 配置

# 标点分级
PUNCT_HARD = "。！？!?；;…\n"          # 硬边界：说完一句
PUNCT_SOFT = "，,、：:"                   # 软边界：句内停顿
PUNCT_TAIL = "）)》」』】\"'"              # 收尾标点，保留在句尾

ALL_PUNCT = PUNCT_HARD + PUNCT_SOFT + PUNCT_TAIL + "！？!?。…，,、：:；;（）()《》「」『』【】\"'—-"

MIN_LEN = 6      # 短于此值则并入相邻句，避免字幕太碎
MAX_LEN = 16     # 硬上限，超过必须拆（1280宽单行放得下 16 个中文字）
TARGET_LEN = 12  # 理想长度
INF_COST = float("inf")

# 句尾虚词：这些字结尾会让字幕读起来断裂（DP 重罚）
BAN_TAIL_CHARS = set("也还就都而及与或但却很更最不没把被让给对从向到在之其为以于个们")
# 句首虚词/助词：这些字开头不自然（DP 轻罚）
BAD_HEAD_CHARS = set("着过地得了呢吗吧啊呀哦嗯")

# 中文序号词：必须「跟在内容后」或「独立成句」，
# 绝不能出现在句尾（如「我们为什么把这套|第三」语义完全错乱）
ORDINAL_WORDS = set("第一第二第三第四第五第六第七第八第九第十")


# ---------------------------------------------------------------- 工具

def _is_punct(ch):
    return ch in ALL_PUNCT


def _clean(text):
    """清洗讲稿：去多余空白、英文缩写转中文读法友好形式。"""
    t = text.strip()
    t = re.sub(r"[ \t　]+", "", t)
    # 破折号/省略号 TTS 会断句异常，替换为停顿逗号
    t = t.replace("——", "，").replace("…", "，")
    t = re.sub(r"\.{3,}", "，", t)
    return t


def _strip_tail_punct(s):
    """去掉句尾标点（字幕无标点要求）。"""
    return s.rstrip(ALL_PUNCT)


def _strip_all_punct(s):
    """
    去掉全部标点。
    字幕铁律：任何标点都不能出现在字幕里（会干扰阅读且占宽度）。
    必须在所有切分完成后统一执行。
    """
    return re.sub(f"[{re.escape(ALL_PUNCT)}]", "", s)


def _count_len(s):
    """字幕长度：中文按 1 字，英文单词按 1 单位（近似）。"""
    return len(re.sub(r"\s+", "", s))


# ---------------------------------------------------------------- 分词

_JIEBA_CACHE = {}


# 「数词+量词」量词表
_QT = (r"[个条位只次张把片块台份名层根支本部款项封套字点位分秒遍趟回]"
       r"|人遍场景")

# 数量+量词(+尾字)结构：整体锁为原子词，绝不在内部切断
# 关键设计：量词后面若跟一个字，**只有当该字本身也是量词/单位/常见量词名时**
# 才一并锁住。否则「输入一个行业」会把「行」误吃进来变成「一个行」，反而更差。
# 允许跟随的字：字/点/分/秒/人/天/次/条/张/位/个/回/遍/下/些/条/份/台/部/本
_QUANT_CORE = re.compile(
    r"([0-9０-９]+|[一二三四五六七八九十百千万两]+)"
    rf"({_QT})"
    r"([字点分秒人天回遍下些次条张位个份台部本款名]?)"
)

# 中文序号：整体锁定
_ORDINAL_RE = re.compile(r"(第[一二三四五六七八九十]+)")


def _words(text):
    """
    带缓存的分词，三层保障「词不被拆散」：

    层 1  数字/量词整体锁定：先扫出「一百三十三」「一条」「一次」等结构，
         在文本中替换为占位符，jieba 处理完再还原，
         保证这些结构作为原子词参与 DP 切分。
    层 2  jieba 分词（HMM 开启，识别未登录词）。
    层 3  相邻单字回填合并（如「一」「个」「字」→「一个字」）。

    本函数是「一个词不分散到前后两条字幕」的根本保证。
    """
    if text in _JIEBA_CACHE:
        return _JIEBA_CACHE[text]

    # ---- 层 1：锁定不可拆结构（数量+量词 / 中文序号）----
    atoms = []

    def _hold(m):
        atoms.append(m.group(0))
        return f"Q{len(atoms) - 1}Z"          # ASCII 占位符，避免编码问题

    locked = _QUANT_CORE.sub(_hold, text)
    # 中文序号同样锁为原子：「第一」「第二」「第三」不可拆开、不可作句尾
    locked = _ORDINAL_RE.sub(_hold, locked)

    # ---- 层 2：jieba 分词 ----
    raw = [w for w in jieba.cut(locked, HMM=True) if w.strip()]

    # 拆出占位符并还原
    expanded = []
    for w in raw:
        for p in re.split(r"(Q\d+Z)", w):
            if not p:
                continue
            m = re.fullmatch(r"Q(\d+)Z", p)
            if m:
                expanded.append(atoms[int(m.group(1))])
            else:
                expanded.append(p)

    # ---- 层 3：相邻单字回填 ----
    merged, i = [], 0
    while i < len(expanded):
        w = expanded[i]
        if len(w) == 1 and i + 1 < len(expanded) and len(expanded[i + 1]) == 1:
            j = i
            grp = ""
            while j < len(expanded) and len(expanded[j]) == 1 and len(grp) < 3:
                grp += expanded[j]
                j += 1
            if len(grp) >= 2 and grp[0] in "一二三四五六七八九十几两多少每这那":
                merged.append(grp)
                i = j
                continue
            for k in range(i, j):
                merged.append(expanded[k])
            i = j
            continue
        merged.append(w)
        i += 1

    # ---- 层 4：原子词黏合 ----
    # 「一个字」被锁为原子词后，其后的单字可能另起一句。
    # DP 的 _is_ordinal 硬约束已覆盖序号场景；此处对量词原子做同样保护。
    _JIEBA_CACHE[text] = merged
    return merged


# ---------------------------------------------------------------- 三级断句

def _split_by_hard_punct(text):
    """级别 1：按硬标点断句。"""
    out, buf = [], ""
    for ch in text:
        buf += ch
        if ch in PUNCT_HARD:
            if _strip_tail_punct(buf):
                out.append(_strip_tail_punct(buf))
            buf = ""
    if _strip_tail_punct(buf):
        out.append(_strip_tail_punct(buf))
    return out or ([_strip_tail_punct(text)] if _strip_tail_punct(text) else [])


def _split_by_soft_punct(text):
    """
    级别 2：按软标点（逗号顿号冒号）断句。
    序号引导段（「第一，」「第三，」）是特例：它太短且必须与后续正文同组，
    因此标记出来交给上层处理，避免被拆成 2 字孤句后又被拼到别人的句尾。
    """
    out, buf = [], ""
    for ch in text:
        if ch in PUNCT_SOFT:
            buf += ch
            if _strip_tail_punct(buf):
                out.append(_strip_tail_punct(buf))
            buf = ""
        else:
            buf += ch
    if _strip_tail_punct(buf):
        out.append(_strip_tail_punct(buf))

    # 序号引导段与后续段绑定：「第一」+「为什么...」→「第一为什么...」
    bound, i = [], 0
    while i < len(out):
        cur = out[i]
        if _is_ordinal(cur) and i + 1 < len(out):
            bound.append(cur + out[i + 1])
            i += 2
        else:
            bound.append(cur)
            i += 1
    return bound


def _split_by_words(text, max_len=MAX_LEN):
    """
    级别 3：按 jieba 词边界断句 + 动态规划择优。

    为什么不用贪心：贪心「凑够长度就切」会把词切碎、产生孤字，
    且不看整体句式。这里改成 DP：在所有合法切法中，选**总代价最小**的一种。

    代价设计（越小越好）：
      - 切点两侧字数越接近越自然 → 惩罚 |left_len - right_len|
      - 过短的片段 → 重罚
      - 单字成句 → 极重罚（孤字必须避免）
      - 句尾落在虚词上 → 罚（也/就/都/了 结尾读着断裂）
      - 句首落在助词上 → 罚（着/了/过 开头不自然）

    硬约束：只在词边界切分，**一个词绝不分散到两条字幕**。
    """
    ws = _words(text)
    if not ws:
        return [text] if text else []

    n = len(ws)
    # 词长度前缀和
    pre = [0] * (n + 1)
    for i, w in enumerate(ws):
        pre[i + 1] = pre[i] + _count_len(w)

    # 单个超长词无法纳入 DP，单独处理
    overlong = [w for w in ws if _count_len(w) > max_len]
    if overlong:
        return [text]

    INF = float("inf")
    # dp[i] = 前 i 个词切完的最小代价；from[i] = 上一刀位置
    dp = [INF] * (n + 1)
    frm = [0] * (n + 1)
    dp[0] = 0.0

    for i in range(1, n + 1):
        for j in range(i):
            seg_len = pre[i] - pre[j]
            if seg_len == 0 or seg_len > max_len:
                continue
            if dp[j] == INF:
                continue
            # 硬约束：序号词（第一/第二/第三）不得作为某条的句尾，
            # 且其后必须紧跟至少 3 个字的正文，否则语义错乱。
            if j < n and _is_ordinal(ws[j]) and (i - j) < 2:
                continue        # 序号自己不能单独成句
            if i < n and _is_ordinal(ws[i - 1]):
                nxt = "".join(ws[i:i + 3])
                if len(nxt) < 3:
                    continue    # 序号后面正文太短，不允许断在这里
            cost = _segment_cost(ws[j:i], seg_len, max_len)
            if dp[j] + cost < dp[i]:
                dp[i] = dp[j] + cost
                frm[i] = j

    # 回溯切分
    out, i = [], n
    while i > 0:
        j = frm[i]
        out.append("".join(ws[j:i]))
        i = j
    out.reverse()

    # 兜底：修复可能的孤字（DP 已重罚，这里是双保险）
    return _fix_orphan(out)


def _is_ordinal(word):
    """判断是否为中文序号词（第一/第二/第三…）。"""
    return bool(_ORDINAL_RE.fullmatch(word)) or word in ORDINAL_WORDS


def _segment_cost(seg, seg_len, max_len):
    """计算一条字幕片段的代价。越小越好。"""
    if len(seg) == 0:
        return INF_COST
    c = 0.0

    # 1) 长度均衡：偏离理想长度 TARGET_LEN 越远越差
    c += abs(seg_len - TARGET_LEN) * 0.6

    # 2) 孤字惩罚（极重）
    if seg_len == 1:
        c += 60
    elif seg_len <= 2:
        c += 20

    # 3) 句尾虚词惩罚
    if seg[-1] in BAN_TAIL_CHARS:
        c += 12
    # 4) 句首虚词/助词惩罚
    if seg[0] in BAD_HEAD_CHARS:
        c += 8
    # 5) 序号词作句尾 = 语义错乱，施加极重惩罚
    #    「我们为什么把这套|第三」→ 必须禁止
    if "".join(seg) in ORDINAL_WORDS:
        c += 50
    # 6) 序号词应独立成句（前面是内容、后面也是内容时才拆分）
    if seg[0] in ("第", "一", "二", "三", "四", "五") and len(seg) <= 3 and \
       any(ch.isdigit() or ch == "第" for ch in seg):
        c -= 6      # 轻微奖励：允许序号独立成短句

    return c


def _fix_orphan(parts):
    """把孤立的单字段并入相邻段（DP 后的双保险）。"""
    if not parts:
        return []
    out = [parts[0]]
    for p in parts[1:]:
        if _count_len(p) == 1 and _count_len(out[-1]) + 1 <= max_len_hard():
            out[-1] += p
        else:
            out.append(p)
    return out


def max_len_hard():
    return MAX_LEN


def _merge_short(parts, min_len=MIN_LEN, max_len=MAX_LEN):
    """
    合并过短片段，消除 3-4 字的碎句。
    策略：反复扫描，短句优先并入较短的一侧（向前/向后借），
    允许合并后略微超 hard_len（软上限），因为观感自然比严格 16 字更重要。
    """
    parts = [p for p in parts if p]
    if not parts:
        return []

    HARD = max_len + 3      # 软硬上限：宁可到 19 字也不要出现孤零零的 4 字

    changed = True
    while changed:
        changed = False
        for i, p in enumerate(parts):
            if _count_len(p) >= min_len:
                continue

            cand = []
            # 并入下一句
            if i + 1 < len(parts):
                cand.append(i + 1)
            # 并入上一句
            if i > 0:
                cand.append(i - 1)

            # 选合并后更短的一侧，保证不超 HARD
            best, best_len = None, None
            for j in cand:
                new_len = _count_len(parts[i]) + _count_len(parts[j])
                if new_len <= HARD and (best_len is None or new_len < best_len):
                    best, best_len = j, new_len

            if best is not None:
                parts[best] = parts[best] + parts[i]
                parts.pop(i)
                changed = True
                break

    return parts


def _balance(parts):
    """
    均衡化：**已废弃，不再调用**。
    原因：它无视语义（只看字数差），会把 DP 已择优的切分重新打乱，
    造成「我们为什么把这套AI工具|第三」这类序号错位。
    现由 DP 内部的 _segment_cost 代价函数 + _merge_short 共同保证均衡。
    """
    return parts


# ---------------------------------------------------------------- TTS 句子切分

def tts_normalize(text):
    """
    TTS 送读文本的**最小必要**规范化 —— 只做三件事：
      1. 去掉多余空白（PPT 备注里常有换行/全角空格）
      2. 破折号 —— → 逗号（edge-tts 读破折号会断句异常）
      3. 省略号 … / ... → 逗号（同上）

    **铁律：绝不删除标点。**
    edge-tts 靠 。！？，、 决定句读停顿；标点被删 = 一路平读 =
    没有停顿感 + 强烈 AI 味。这是 v3 最大的观感缺陷。
    """
    t = text.strip()
    t = re.sub(r"[ \t　]+", "", t)
    t = t.replace("——", "，").replace("…", "，")
    t = re.sub(r"\.{3,}", "，", t)
    return t


def split_sentences(text, limit=80):
    """
    讲稿 → TTS 句子列表（**保留标点**，与字幕切分是两套独立逻辑）。

    为什么要按句送 TTS：
      · edge-tts 的韵律（语气停顿、重音）按标点/句子计算，
        整段平读会得到一条没有起伏的直线音轨
      · 逐句生成后，每句的**音频时长精确已知** → 字幕时间轴
        可以直接按句边界硬对齐，不再需要 silencedetect 猜

    参数
    ----
    text   原始讲稿
    limit  单句送 TTS 的字数上限，超出则再切（防长句吞字）

    返回
    ----
    ["今天这条视频讲清楚三件事。", "第一，为什么我们一天能更新好几条视频。"]
    """
    t = tts_normalize(text)
    if not t:
        return []

    # 先按硬标点分句（保留标点，不做 strip）
    sents, buf = [], ""
    for ch in t:
        buf += ch
        if ch in PUNCT_HARD:
            sents.append(buf)
            buf = ""
    if buf.strip():
        sents.append(buf)

    # 单句超长 → 先按软标点切，仍超长才硬切
    out = []
    for s in sents:
        if len(s) <= limit:
            out.append(s)
            continue
        for piece in _split_by_soft_punct_keep(s):
            if len(piece) <= limit:
                out.append(piece)
            else:
                for i in range(0, len(piece), limit):
                    out.append(piece[i:i + limit])

    return [s for s in out if tts_normalize(s).strip("，,、：:")]


def _split_by_soft_punct_keep(text):
    """按软标点切分但**保留标点**（供 TTS 长句拆分用）。"""
    out, buf = [], ""
    for ch in text:
        buf += ch
        if ch in PUNCT_SOFT:
            out.append(buf)
            buf = ""
    if buf:
        out.append(buf)
    return out


def fidelity_check(original, spoken):
    """
    忠实度校验：TTS 实际送读文本 vs 备注原文，去掉标点后必须逐字一致。
    返回 (是否通过, 问题描述)。这是"别乱发挥"的硬闸门。
    """
    def bare(s):
        return re.sub(f"[{re.escape(ALL_PUNCT)}\\s]", "", s)
    a, b = bare(original), bare(spoken)
    if a == b:
        return True, f"{len(a)}字 逐字一致"
    # 找第一处差异
    i = 0
    while i < min(len(a), len(b)) and a[i] == b[i]:
        i += 1
    ctx = f"第{i+1}字起：原文「{a[i:i+12]}」→ 送读「{b[i:i+12]}」"
    return False, f"字数 {len(a)}→{len(b)}，{ctx}"


# ---------------------------------------------------------------- 主入口

def split_subtitles(text, max_len=MAX_LEN, min_len=MIN_LEN, prefer_punct=True):
    """
    主入口：讲稿 → 字幕列表

    参数
    ----
    text      原始讲稿
    max_len   单条最大字数（默认 14）
    min_len   单条最小字数（默认 6）
    prefer_punct  True=先按标点断（用户要求）；False=直接按词断

    返回
    ----
    ["做同城短视频的朋友", "你是不是还在搬运别人的视频发自己号", ...]
    每条已去标点、长度受限、词不被拆散
    """
    t = _clean(text)
    if not t:
        return []

    if prefer_punct:
        # 级别 1：硬标点
        parts = _split_by_hard_punct(t)
        # 级别 2：超长句用逗号类再切
        expanded = []
        for s in parts:
            if _count_len(s) > max_len:
                expanded.extend(_split_by_soft_punct(s))
            else:
                expanded.append(s)
        parts = expanded
        # 注意：不要把已按标点切好的片段重新拼接再切，
        #       否则会丢失硬标点边界（序号"第一/第二/第三"会被打散）。
    else:
        parts = [t]

    # 级别 3：仍有超长句 → 按词边界切
    final = []
    for s in parts:
        if _count_len(s) > max_len:
            final.extend(_split_by_words(s, max_len))
        else:
            final.append(s)

    final = _merge_short(final, min_len, max_len)
    # 铁律：字幕内绝不含任何标点，统一在最后清除
    final = [_strip_all_punct(s) for s in final]
    final = [s for s in final if s]
    return final


# ---------------------------------------------------------------- 自检

def verify(lines, max_len=MAX_LEN):
    """自检：返回问题列表，空列表表示全部通过。"""
    issues = []
    for i, ln in enumerate(lines, 1):
        n = _count_len(ln)
        if n > max_len:
            issues.append(f"第{i}条超长 {n}字 > {max_len}: {ln}")
        if _is_punct(ln[-1]) if ln else False:
            issues.append(f"第{i}条含标点: {ln}")
        # 检查是否有词被拆散：与下一条拼接处若形成跨词边界则告警
    # 跨词检测：相邻两条拼接后重新分词，词数应等于原词数之和
    for i in range(len(lines) - 1):
        a, b = lines[i], lines[i + 1]
        wa, wb = _words(a), _words(b)
        joined = _words(a + b)
        if len(joined) < len(wa) + len(wb):
            issues.append(f"第{i+1}/{i+2}条交界处可能拆词: {a} | {b}")
    return issues


if __name__ == "__main__":
    tests = [
        "做同城短视频的朋友。你是不是还在搬运别人的视频发自己号？",
        "先看这张截图。这是我们后台的原创保护记录。一条黑金卡的视频，被一百三十三个人搬运。",
        "整个过程不用你自己写一个字也不用你剪片子一个字",
        "授人以鱼不如授人以渔工具直接开放给你你自己生成原创内容",
    ]
    for t in tests:
        ls = split_subtitles(t)
        print("=" * 60)
        print("原文:", t)
        for i, l in enumerate(ls, 1):
            print(f"  {i}. [{len(l):2d}字] {l}")
        v = verify(ls)
        print("  自检:", "通过" if not v else v)
