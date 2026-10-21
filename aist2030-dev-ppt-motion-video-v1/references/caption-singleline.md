# 严格单行词级卡拉OK字幕 · 完整实现

> 目标：字幕**永远单行**、**永不跳位**、**永不叠字**，同时当前念到的词实时高亮。

## 为什么不能靠 CSS 自动换行

朴素的 `white-space: nowrap` 会导致长句溢出画布；而允许换行（`flex-wrap: wrap`）则会让**行数随语音变化**——同一句话前半段占 1 行、后半段变 2 行，容器高度随之变化，整块字幕上下跳动，观感极差。

正解：**把长句切成若干"单行块"，逐块显示**。

---

## 一、视觉宽度单位

中文全角字宽 ≈ 1.0em，英文数字 ≈ 0.56~0.58em。用这个比例估算文字宽度，比"数字符个数"准确得多（`AIST2030` 8 个字符但只有约 4.5 个中文宽度）。

```ts
/** 估算文字视觉宽度单位 */
const unitsOf = (s: string): number => {
  let n = 0;
  for (const ch of s) n += /[\x00-\xff]/.test(ch) ? 0.58 : 1;
  return n;
};
```

容器容量：`MAX_UNITS ≈ 净宽 / 字号 × 0.7`

> 例：1080 宽画布、左右边距各 84px → 净宽 912px；字幕字号 40px → 912/40 = 22.8 单位；留 30% 余量 → `MAX_UNITS = 15`。

---

## 二、分块：宽度上限 + 停顿断句 + 孤字合并

### 2.1 为什么用"停顿"而不是"标点"断句

`edge-tts` 的 `WordBoundary` 返回的词**不含标点**（标点在 `clean` 文本里被剥离了），所以无法按标点断句。

但有个更好的信号：**词间停顿**。实测 TTS 在语义边界处的停顿明显更大：

| 位置 | 停顿 |
|---|---|
| "灰度\|九月" | 0.39s |
| "阶段\|但" | 0.38s |
| "第三\|转账" | 0.32s |
| 词内（如"十\|月"） | 0.01~0.03s |

所以：**溢出时从当前位置向前回溯若干词，找最近的大停顿点作为断点**。

### 2.2 完整实现

```ts
const GAP_PREFERRED = 0.16; // 秒：达到此停顿即认为是好的断点
const LOOKAHEAD = 5;        // 最多回溯几个词
const MIN_UNITS = 6;        // 块宽下限，低于此视为"孤字块"

const chunkShot = (shot: Shot): Chunk[] => {
  const ws = shot.words;
  const gapAfter = (i: number): number =>
    i + 1 < ws.length ? ws[i + 1].t - (ws[i].t + ws[i].d) : Infinity;
  const widthOf = (from: number, to: number): number => {
    let n = 0;
    for (let k = from; k < to; k++) n += unitsOf(ws[k].w);
    return n;
  };

  // ---- 第一遍：宽度上限 + 自然停顿贪心切分 ----
  const raw: Array<[number, number]> = [];
  let from = 0, u = 0;
  for (let i = 0; i < ws.length; i++) {
    const wu = unitsOf(ws[i].w);
    if (i > from && u + wu > MAX_UNITS) {
      let cut = i;                                  // 默认硬切在 i 之前
      for (let k = 0; k < LOOKAHEAD; k++) {         // 向前找自然停顿
        const idx = i - 1 - k;
        if (idx <= from) break;
        if (gapAfter(idx) >= GAP_PREFERRED) { cut = idx + 1; break; }
      }
      raw.push([from, cut]);
      from = cut;
      u = widthOf(from, i + 1);
    } else {
      u += wu;
    }
  }
  if (from < ws.length) raw.push([from, ws.length]);

  // ---- 第二遍：消除孤字尾块 ----
  const merged: Array<[number, number]> = [];
  for (const r of raw) {
    const prev = merged[merged.length - 1];
    const isTail = r[1] === ws.length;
    if (prev &&
        (widthOf(r[0], r[1]) < MIN_UNITS ||
         (isTail && widthOf(r[0], r[1]) < MIN_UNITS * 1.35))) {
      if (widthOf(prev[0], r[1]) <= MAX_UNITS * 1.25) {   // 合并后不得过宽
        prev[1] = r[1];
        continue;
      }
    }
    merged.push([r[0], r[1]]);
  }

  return merged.map(([a, b]) => ({
    words: ws.slice(a, b),
    start: shot.start + ws[a].t,
    end: shot.start + ws[b - 1].t + ws[b - 1].d,
  }));
};
```

**效果**：某真实项目 21 句切成 50 块，孤字块从 13 处降到 4 处（剩余的都是"视频号两个""问AI入口"这种语义完整的短语），最宽块 18 单位 < 容器 22.8。

> ⚠️ **写代码时的坑**：第一版用变量手工跟踪"当前块起点"，改来改去越改越脆。**用纯索引区间 `[from, to)` 表示块**，一次就能写对。

---

## 三、渲染：互斥，而不是交叉淡变

### 3.1 交叉淡变会叠字

直觉做法是"所有块都渲染，各自算 opacity 做交叉淡变"。但相邻块之间**没有时间间隙**（词是连续的），于是前后两块会**同时可见、叠在同一行**——看起来像"还有电/脑端"这样糊在一起。

### 3.2 正解：任一时刻只渲染一块

```tsx
export const Caption: React.FC<{ page: PageData }> = ({ page }) => {
  const t = usePageT();
  const si = shotIndexAt(page, t);
  const shot = page.shots[si];
  if (!shot || !shot.words.length) return null;

  const chunks = chunkShot(shot);
  const lineH = TYPE.caption * 1.5;

  // 当前活跃块 = 最后一个 start <= t 的块
  let idx = 0;
  for (let i = 0; i < chunks.length; i++) if (t >= chunks[i].start) idx = i;
  const c = chunks[idx];
  const isLast = idx === chunks.length - 1;

  const inA = easeOutCubic(win(t, c.start - 0.1, c.start + 0.06));
  // 非末块：下一块开始前就退场 → 两块永不同框
  const outA = isLast
    ? 1 - easeOutCubic(win(t, c.end + 0.28, c.end + 0.5))
    : 1 - easeOutCubic(win(t, chunks[idx + 1].start - 0.06, chunks[idx + 1].start + 0.04));
  const op = clamp01(inA * outA);

  return (
    <AbsoluteFill style={{ pointerEvents: "none" }}>
      {/* 底部渐隐遮罩：高度固定，不随块数变化 */}
      <div style={{
        position: "absolute", left: 0, right: 0, bottom: 0,
        height: 1440 - LAYOUT.captionTop - lineH + 44,
        background: "linear-gradient(to bottom, rgba(4,7,13,0) 0%, rgba(4,7,13,0.55) 100%)",
      }} />

      {op > 0.001 && (
        <div style={{
          position: "absolute",
          left: LAYOUT.marginX, right: LAYOUT.marginX,
          top: LAYOUT.captionTop, height: lineH,   // ← 位置与高度恒定 → 绝不跳位
          display: "flex", flexDirection: "row",
          flexWrap: "nowrap",                       // ← 硬性禁止换行
          alignItems: "center", justifyContent: "center",
          whiteSpace: "nowrap",
          opacity: op,
        }}>
          {c.words.map((w, wi) => {
            const abs = wordAbs(shot, w);
            const active = t >= abs - 0.05 && t < abs + w.d + 0.1;
            const passed = t >= abs + w.d + 0.1;
            return (
              <span key={wi} style={{
                fontFamily: FONT.family,
                fontSize: TYPE.caption,
                fontWeight: active ? 700 : 500,
                lineHeight: 1, whiteSpace: "nowrap",
                color: active ? COLORS.goldBright
                     : passed ? COLORS.ink
                     : "rgba(244,234,218,0.35)",     // 未念到 → 半透明
                textShadow: active
                  ? "0 0 18px rgba(232,198,110,0.55), 0 2px 8px rgba(0,0,0,0.8)"
                  : "0 2px 8px rgba(0,0,0,0.8)",
                transform: `scale(${active ? 1.06 : 1})`,   // 当前词微放大
                display: "inline-block",
              }}>{w.w}</span>
            );
          })}
        </div>
      )}
    </AbsoluteFill>
  );
};
```

### 3.3 三个"绝不"如何保证

| 保证 | 靠什么 |
|---|---|
| 绝不换行 | `MAX_UNITS` 留 30% 余量 + `flexWrap: nowrap` + `whiteSpace: nowrap` |
| 绝不叠字 | 任一时刻只渲染一块；非末块在下一块开始前退场 |
| 绝不跳位 | 容器 `top` 与 `height` 恒定（单行高度），只有内容在变 |

---

## 四、参数速查

| 参数 | 含义 | 起点值 | 调整依据 |
|---|---|---|---|
| `MAX_UNITS` | 单块宽度上限 | `净宽/字号 × 0.7` | 净宽 = 画布宽 − 2×边距 |
| `GAP_PREFERRED` | 认定"好断点"的停顿阈值 | 0.16s | 语速慢可提到 0.2s |
| `LOOKAHEAD` | 回溯词数 | 5 | 长句可加大到 8 |
| `MIN_UNITS` | 孤字块判定下限 | 6 | 字号大则同比上调 |
| 字号 | 字幕字号 | 净宽/16 左右 | 竖版 1080 宽建议 38~44px |

## 五、自检方法

渲染若干 **最宽块** 所在帧（用脚本按 `widthOf` 排序取 top5），逐帧确认：
1. 只有一行文字；
2. 高亮词与音频当前时间一致；
3. 与上一帧对比，位置没有上下移动（跳位检测：连续抽相邻两帧，字幕 y 坐标应一致）。
