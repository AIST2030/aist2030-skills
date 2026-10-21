import React from "react";
import { AbsoluteFill, useCurrentFrame } from "remotion";
import type { Shot, Word } from "./types";

/**
 * 课件出片式字幕·窄带版（渲染在画面下方的纯黑外扩条内）：
 * - 词序列切成若干「严格单行块」（溢出优先在 TTS 停顿处断句），只显示词序列 → 天然无标点
 * - 分块上限 15 视觉宽度单位：短语化断句，不堆长句，画面简洁
 * - 互斥渲染：任一时刻只有一块在场，绝不叠字/换行
 * - 块内词级卡拉OK：当前词金色微放大；字体/字号/字重全块统一，无跳变
 * - 字号三档可选（plan.json captionSize: small/medium/large → timeline.captionFontSize）
 */

const FONT_FAMILY = '"Microsoft YaHei", "PingFang SC", sans-serif';

/** 视觉宽度单位：中文 1.0 / 英数 0.58 */
const unitsOf = (s: string): number => {
  let n = 0;
  for (const ch of s) n += /[\x00-\xff]/.test(ch) ? 0.58 : 1;
  return n;
};

/** 单块最大视觉宽度单位：取「按字号反推的安全宽度」与 15（短语化上限）的较小值 */
const HARD_CAP_UNITS = 15;
const maxUnitsFor = (fontSize: number): number =>
  Math.min(HARD_CAP_UNITS, Math.max(8, Math.floor(((1920 - 160) / fontSize) * 0.88)));

/** 溢出回看时最多向后找几个词 */
const LOOKAHEAD = 8;
/** 达到此词间停顿（秒）即认为是好的断句点（0.12 能命中文本大部分语义边界，实测「区|屏面」=0.13） */
const GAP_PREFERRED = 0.12;
/** 块宽下限：低于此值视为孤字尾块，回退并入前块 */
const MIN_UNITS = 6;

interface Chunk {
  words: Word[];
  /** 句内绝对时间：首词开始 */
  start: number;
  /** 句内绝对时间：末词结束 */
  end: number;
}

/** 把一个 shot 的词序列切成若干单行块（与 skill 版 chunkShot 一致） */
const chunkShot = (shot: Shot, maxUnits: number): Chunk[] => {
  const ws = shot.words;
  const gapAfter = (i: number): number =>
    i + 1 < ws.length ? ws[i + 1].t - (ws[i].t + ws[i].d) : Infinity;

  const mk = (from: number, to: number): Chunk => {
    const slice = ws.slice(from, to);
    const first = slice[0];
    const last = slice[slice.length - 1];
    return {
      words: slice,
      start: first.t,
      end: last.t + last.d,
    };
  };
  const widthOf = (from: number, to: number): number => {
    let n = 0;
    for (let k = from; k < to; k++) n += unitsOf(ws[k].w);
    return n;
  };

  // 第一遍：按宽度 + 自然停顿贪心切分
  const raw: Array<[number, number]> = [];
  let from = 0;
  let u = 0;
  for (let i = 0; i < ws.length; i++) {
    const wu = unitsOf(ws[i].w);
    if (i > from && u + wu > maxUnits) {
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

  // 第二遍：消除孤字尾块（尾部不足 MIN_UNITS 并回上一块）
  const merged: Array<[number, number]> = [];
  for (const r of raw) {
    const prev = merged[merged.length - 1];
    const isTail = r[1] === ws.length;
    if (
      prev &&
      (widthOf(r[0], r[1]) < MIN_UNITS ||
        (isTail && widthOf(r[0], r[1]) < MIN_UNITS * 1.35))
    ) {
      if (widthOf(prev[0], r[1]) <= maxUnits * 1.25) {
        prev[1] = r[1];
        continue;
      }
    }
    merged.push([r[0], r[1]]);
  }

  return merged.map(([a, b]) => mk(a, b));
};

const easeOut = (x: number): number => 1 - Math.pow(1 - Math.max(0, Math.min(1, x)), 3);
/** 窗口函数：t 进入 [a,b] 区间时从 0 平滑升到 1 */
const win = (t: number, a: number, b: number): number =>
  b <= a ? (t >= b ? 1 : 0) : easeOut((t - a) / (b - a));
const clamp01 = (x: number): number => Math.max(0, Math.min(1, x));

export const Caption: React.FC<{
  shot: Shot;
  pageStart: number;
  fps: number;
  fontSize?: number;
}> = ({ shot, pageStart, fps, fontSize = 70 }) => {
  const frame = useCurrentFrame();
  const t = frame / fps;
  const lt = t - pageStart; // 句内时间
  if (!shot.words.length) return null;

  const chunks = chunkShot(shot, maxUnitsFor(fontSize));

  // 互斥：找出当前活跃块（最后一个 start <= lt）。块切换时上一块立即退场。
  let idx = 0;
  for (let i = 0; i < chunks.length; i++) {
    if (lt >= chunks[i].start) idx = i;
  }
  const c = chunks[idx];
  const isLast = idx === chunks.length - 1;

  const inA = easeOut(win(lt, c.start - 0.1, c.start + 0.06));
  const outA = isLast
    ? 1 - easeOut(win(lt, c.end + 0.28, c.end + 0.5))
    : 1 - easeOut(win(lt, chunks[idx + 1].start - 0.06, chunks[idx + 1].start + 0.04));
  const op = clamp01(inA * outA);
  if (op <= 0.001) return null;

  return (
    <AbsoluteFill
      style={{
        // 渲染在外扩黑带容器内：垂直水平居中，无遮罩
        justifyContent: "center",
        alignItems: "center",
        pointerEvents: "none",
        overflow: "hidden",
      }}
    >
      <div
        style={{
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
          const abs = w.t;
          const active = lt >= abs - 0.05 && lt < abs + w.d + 0.1 ? 1 : 0;
          const passed = lt >= abs + w.d + 0.1 ? 1 : 0;
          return (
            <span
              key={wi}
              style={{
                fontFamily: FONT_FAMILY,
                fontSize,
                fontWeight: 600, // 字重统一，高亮只靠颜色/缩放，无宽度跳变
                lineHeight: 1,
                whiteSpace: "nowrap",
                color: active ? "#FFC933" : passed ? "#FFFFFF" : "rgba(255,255,255,0.55)",
                transform: `scale(${active ? 1.03 : 1})`, // 72px 窄带内防裁边
                display: "inline-block",
              }}
            >
              {w.w}
            </span>
          );
        })}
      </div>
    </AbsoluteFill>
  );
};
