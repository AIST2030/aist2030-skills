import React from "react";
import { AbsoluteFill, useCurrentFrame, useVideoConfig } from "remotion";
import type { PageData, Shot, Word } from "./types";
import { COLORS, FONT, LAYOUT, TYPE, clamp01, easeOutCubic, win } from "./theme";

/** 页内本地时间（秒） */
export const usePageT = (): number => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  return frame / fps;
};

/** 当前 shot 索引（最后一个 start <= t 的 shot） */
export const shotIndexAt = (page: PageData, t: number): number => {
  let idx = 0;
  for (let i = 0; i < page.shots.length; i++) {
    if (page.shots[i].start <= t + 1e-6) idx = i;
    else break;
  }
  return idx;
};

/**
 * 触发器：在 shot si 的 clean 文本中定位 substr（按字符索引），
 * 返回包含该位置的首个词的**页内绝对时间**。
 * 基于字符索引对齐，不受 edge-tts 分词粒度影响。
 * notFoundFallback: "start" 取 shot 起点 / "end" 取 shot 终点 / 数字取该秒数
 */
export const trigger = (
  page: PageData,
  si: number,
  substr: string,
  notFoundFallback: "start" | "end" | number = "start",
  occurrence = 0,
): number => {
  const shot = page.shots[si];
  if (!shot) return 0;
  const clean = shot.clean || "";
  let occ = 0;
  let from = 0;
  for (;;) {
    const idx = clean.indexOf(substr, from);
    if (idx < 0) break;
    if (occ === occurrence) {
      for (const w of shot.words) {
        if (w.ci >= 0 && w.ci <= idx && idx < w.ci + w.w.length) {
          return shot.start + w.t;
        }
      }
      for (const w of shot.words) {
        if (w.ci >= idx) return shot.start + w.t;
      }
      return shot.start + shot.audioDur;
    }
    occ++;
    from = idx + 1;
  }
  if (notFoundFallback === "start") return shot.start + 0.05;
  if (notFoundFallback === "end") return shot.start + shot.audioDur;
  return notFoundFallback;
};

/** 词的页内绝对时间 */
export const wordAbs = (shot: Shot, w: Word): number => shot.start + w.t;

/* ---------------- 词级卡拉OK 字幕（严格单行，绝不换行） ---------------- */

/**
 * 单块最大"视觉宽度单位"。中文按 1.0 计，英数按 0.58 计。
 * 字幕容器净宽 = 1080 - 84*2 = 912px，字号 40px → 上限约 22 单位。
 * 取 15 留足余量，保证任何块都能稳稳塞进一行。
 */
const MAX_UNITS = 15;

/** 估算一段文字的视觉宽度单位 */
const unitsOf = (s: string): number => {
  let n = 0;
  for (const ch of s) n += /[\x00-\xff]/.test(ch) ? 0.58 : 1;
  return n;
};

interface Chunk {
  words: Word[];
  /** 页内绝对时间：首词开始 */
  start: number;
  /** 页内绝对时间：末词结束 */
  end: number;
}

/**
 * 把一个 shot 的词序列切成若干**单行块**。
 * 关键：溢出时**优先在词间停顿处断句**（TTS 在语义边界停顿最大），
 * 让每块都是语义完整的短语，而不是从词组中间硬切。
 */
const GAP_PREFERRED = 0.16; // 秒：达到此停顿即认为是好的断点
const LOOKAHEAD = 5; // 最多向后找几个词
const MIN_UNITS = 6; // 块宽下限：低于此值视为"孤字尾块"，回退并入前块

const chunkShot = (shot: Shot): Chunk[] => {
  const ws = shot.words;
  /** 两词之间的停顿秒数 */
  const gapAfter = (i: number): number =>
    i + 1 < ws.length ? ws[i + 1].t - (ws[i].t + ws[i].d) : Infinity;

  const mk = (from: number, to: number): Chunk => {
    const slice = ws.slice(from, to);
    const first = slice[0];
    const last = slice[slice.length - 1];
    return {
      words: slice,
      start: shot.start + first.t,
      end: shot.start + last.t + last.d,
    };
  };
  const widthOf = (from: number, to: number): number => {
    let n = 0;
    for (let k = from; k < to; k++) n += unitsOf(ws[k].w);
    return n;
  };

  // --- 第一遍：按宽度 + 自然停顿贪心切分 ---
  const raw: Array<[number, number]> = [];
  let from = 0;
  let u = 0;
  for (let i = 0; i < ws.length; i++) {
    const wu = unitsOf(ws[i].w);
    if (i > from && u + wu > MAX_UNITS) {
      let cut = i;
      for (let k = 0; k < LOOKAHEAD; k++) {
        const idx = i - 1 - k;
        if (idx <= from) break;
        if (gapAfter(idx) >= GAP_PREFERRED) {
          cut = idx + 1;
          break;
        }
      }
      raw.push([from, cut]);
      from = cut;
      u = widthOf(from, i + 1);
    } else {
      u += wu;
    }
  }
  if (from < ws.length) raw.push([from, ws.length]);

  // --- 第二遍：消除孤字尾块（尾部不足 MIN_UNITS 就并回上一块） ---
  const merged: Array<[number, number]> = [];
  for (const r of raw) {
    const prev = merged[merged.length - 1];
    const isTail = r[1] === ws.length;
    if (
      prev &&
      (widthOf(r[0], r[1]) < MIN_UNITS ||
        (isTail && widthOf(r[0], r[1]) < MIN_UNITS * 1.35))
    ) {
      // 并回上一块，但整体不得超MAX_UNITS * 1.25（留余量）
      if (widthOf(prev[0], r[1]) <= MAX_UNITS * 1.25) {
        prev[1] = r[1];
        continue;
      }
    }
    merged.push([r[0], r[1]]);
  }

  return merged.map(([a, b]) => mk(a, b));
};

export const Caption: React.FC<{ page: PageData }> = ({ page }) => {
  const t = usePageT();
  const si = shotIndexAt(page, t);
  const shot = page.shots[si];
  if (!shot || !shot.words.length) return null;

  const chunks = chunkShot(shot);
  const lineH = TYPE.caption * 1.5;

  // 互斥：找出当前活跃块（最后一个start <= t）。块切换时上一块立即退场，
  // 任一时刻只有一块文字在场，**绝不出现叠字或第二行**。
  let idx = 0;
  for (let i = 0; i < chunks.length; i++) {
    if (t >= chunks[i].start) idx = i;
  }
  const c = chunks[idx];
  const isLast = idx === chunks.length - 1;

  const inA = easeOutCubic(win(t, c.start - 0.1, c.start + 0.06));
  const outA = isLast
    ? 1 - easeOutCubic(win(t, c.end + 0.28, c.end + 0.5))
    : 1 - easeOutCubic(win(t, chunks[idx + 1].start - 0.06, chunks[idx + 1].start + 0.04));
  const op = clamp01(inA * outA);

  return (
    <AbsoluteFill style={{ pointerEvents: "none" }}>
      {/* 底部渐隐遮罩（固定单行高度） */}
      <div
        style={{
          position: "absolute",
          left: 0,
          right: 0,
          bottom: 0,
          height: 1440 - LAYOUT.captionTop - lineH + 44,
          background:
            "linear-gradient(to bottom, rgba(4,7,13,0) 0%, rgba(4,7,13,0.55) 100%)",
        }}
      />

      {op > 0.001 && (
        <div
          style={{
            position: "absolute",
            left: LAYOUT.marginX,
            right: LAYOUT.marginX,
            top: LAYOUT.captionTop,
            height: lineH,
            display: "flex",
            flexDirection: "row",
            flexWrap: "nowrap",
            alignItems: "center",
            justifyContent: "center",
            whiteSpace: "nowrap",
            opacity: op,
          }}
        >
          {c.words.map((w, wi) => {
            const abs = wordAbs(shot, w);
            const active = t >= abs - 0.05 && t < abs + w.d + 0.1 ? 1 : 0;
            const passed = t >= abs + w.d + 0.1 ? 1 : 0;
            return (
              <span
                key={wi}
                style={{
                  fontFamily: FONT.family,
                  fontSize: TYPE.caption,
                  fontWeight: active ? 700 : 500,
                  lineHeight: 1,
                  whiteSpace: "nowrap",
                  color: active
                    ? COLORS.goldBright
                    : passed
                      ? COLORS.ink
                      : "rgba(244,234,218,0.35)",
                  textShadow: active
                    ? "0 0 18px rgba(232,198,110,0.55), 0 2px 8px rgba(0,0,0,0.8)"
                    : "0 2px 8px rgba(0,0,0,0.8)",
                  transform: `scale(${active ? 1.06 : 1})`,
                  display: "inline-block",
                }}
              >
                {w.w}
              </span>
            );
          })}
        </div>
      )}
    </AbsoluteFill>
  );
};
