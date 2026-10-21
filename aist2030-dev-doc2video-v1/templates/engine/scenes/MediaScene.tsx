import React from "react";
import {
  AbsoluteFill,
  Audio as RawAudio,
  Sequence,
  staticFile,
  useVideoConfig,
} from "remotion";
import type { PageData } from "../types";
import { MediaLayer, type MediaSpec } from "../MediaLayer";
import { Atmosphere } from "../components/Atmosphere";
import {
  BrandChip,
  Glyph,
  GlyphName,
  PageNum,
  SceneFade,
  SectionHeader,
} from "../ui";
import {
  COLORS,
  FONT,
  LAYOUT,
  S,
  clamp01,
  easeOutCubic,
  fadeIn,
  fitFontSize,
  pulse,
  reveal,
  win,
} from "../theme";
import { triggerAny, usePageT } from "../Caption";

/**
 * 通用混剪场景：实拍素材打底（通道A）+ **提炼信息主体**图形叠加（通道B）。
 *
 * ★ 2026-10-17 按用户反馈重构版式（两次迭代的结论）：
 *   第一版把"讲稿全文"放大到主屏 → 用户否掉："不是把所有字幕搬到主画面"。
 *   本版定位：
 *     1) 主画面 = **提炼**内容：封面大标题 / 金句大字体动画 / 关键词卡片 /
 *        大数字滚动 / 结论条 —— 每页只放 1-2 类，绝不堆满；
 *     2) 完整讲稿走**底部单行卡拉OK字幕**（Caption 组件，原样式，坚决一行）；
 *     3) 背景实拍视频保持可见（轻压暗 + 底部渐隐），只作氛围与观赏性；
 *     4) 关键词按项数自适应布局：3=正三角形 / 4=2×2矩形 / 5=3+2 / 6=3+3…；
 *     5) 图形元素全部语音触发入场，并配轻音效（whoosh/pop/sparkle/alert）。
 */

/* ================= 叠加配置（换文案时只改这里） ================= */

export interface KeywordItem {
  text: string;
  desc?: string;
  icon?: GlyphName;
  /** 右上角逐变徽标，如 "×5" */
  num?: string;
  /** 说到它时卡片高亮 */
  triggerWord?: string;
}

export interface OverlaySpec {
  /** 封面（p1）：大标题 + 副标题 + 标签 */
  cover?: { tag: string; title: string; subtitle: string };
  /** 章节头 */
  section?: { label: string; title: string };
  /** 金句（大字体动画，可多条，按 triggerWord 依次入场） */
  golden?: { text: string; triggerWord?: string }[];
  /** 关键词卡片组（自适应布局） */
  keywords?: KeywordItem[];
  /** 大数字滚动 */
  bigNumber?: { value: number; suffix?: string; label: string; triggerWord?: string };
  /** 结论条 */
  banner?: { text: string; icon?: GlyphName; triggerWord?: string };
}

interface Props {
  page: PageData;
  media: Record<string, string>;
  overlay: OverlaySpec;
  pageIndex: number;
  totalPages?: number;
}

/* ================= 垂直分区（1080×1440 画布） ================= */
const GOLDEN_TOP = 356; // 金句区（章节头之下）
const GOLDEN_STEP = 96; // 多条金句的行距
const GRID_TOP = 596; // 关键词网格区
const GRID_H = 426; // 网格区高（底 1022）
const BANNER_TOP = 1146; // 结论条（底 1234，字幕 1258 起）
const BIGNUM_COVER_TOP = 700; // 封面大数字
const BIGNUM_TOP = 1024; // 非封面大数字

/* ================= 音效（Mixkit 免费可商用，public/sfx/） ================= */
// Remotion 4.0 类型与 React 19 types 兼容差异，轻量封装
const Audio = RawAudio as unknown as React.FC<{
  src: string;
  volume?: number | ((frame: number) => number);
}>;

/** 一次性音效：在 at（秒，页内）处触发，低音量 */
const Sfx: React.FC<{
  file: string;
  at: number;
  volume?: number;
  fps: number;
}> = ({ file, at, volume = 0.18, fps }) => {
  if (!(at >= 0) || at > 1e8) return null;
  const frame = Math.max(0, Math.round(at * fps));
  return (
    <Sequence from={frame} durationInFrames={150}>
      <Audio src={staticFile(`sfx/${file}`)} volume={volume} />
    </Sequence>
  );
};

/* ================= 关键词自适应布局引擎 ================= */

interface Cell {
  x: number;
  y: number;
  w: number;
  h: number;
}

/**
 * 按项数 N 计算卡片位置（容器内相对坐标）：
 *   1 → 居中通栏；2 → 一行两张；3 → **正三角形**（上1下2）；
 *   4 → 2×2 矩形；5 → 3+2；6 → 3+3；7 → 3+2+2；8 → 3+3+2；9 → 3×3。
 * 规则：≤2 单行；3 三角形；≥4 按最多 3 列均分多行（避免孤行）。
 */
const gridCells = (
  n: number,
  zoneW: number,
  zoneH: number,
  gap: number,
): Cell[] => {
  if (n <= 0) return [];
  if (n === 1) {
    const h = Math.min(200, zoneH);
    return [{ x: 0, y: (zoneH - h) / 2, w: zoneW, h }];
  }
  if (n === 2) {
    const w = (zoneW - gap) / 2;
    const h = Math.min(200, zoneH);
    return [
      { x: 0, y: (zoneH - h) / 2, w, h },
      { x: w + gap, y: (zoneH - h) / 2, w, h },
    ];
  }
  if (n === 3) {
    // 正三角形：上 1 下 2
    const topH = Math.round(zoneH * 0.4);
    const botH = zoneH - topH - gap;
    const wTop = Math.round(zoneW * 0.56);
    const wBot = (zoneW - gap) / 2;
    return [
      { x: (zoneW - wTop) / 2, y: 0, w: wTop, h: topH },
      { x: 0, y: topH + gap, w: wBot, h: botH },
      { x: wBot + gap, y: topH + gap, w: wBot, h: botH },
    ];
  }
  const rows = Math.ceil(n / 3);
  const base = Math.floor(n / rows);
  const rem = n % rows;
  const counts: number[] = [];
  for (let r = 0; r < rows; r++) counts.push(base + (r < rem ? 1 : 0));
  const rowH = (zoneH - (rows - 1) * gap) / rows;
  const cells: Cell[] = [];
  // ★ 等宽原则：所有行共用第一行（最多列）的卡片宽度，少的行整体居中。
  //   否则 3+2 的第二行会被拉宽，同一页出现两种卡片尺寸，观感廉价。
  const maxCols = Math.max(...counts);
  const w = (zoneW - (maxCols - 1) * gap) / maxCols;
  let y = 0;
  for (const c of counts) {
    const rowW = c * w + (c - 1) * gap;
    let x = (zoneW - rowW) / 2;
    for (let i = 0; i < c; i++) {
      cells.push({ x, y, w, h: rowH });
      x += w + gap;
    }
    y += rowH + gap;
  }
  return cells;
};

/* ================= 关键词卡片 ================= */

const KeywordCard: React.FC<{
  item: KeywordItem;
  cell: Cell;
  t: number;
  at: number;
  active: boolean;
}> = ({ item, cell, t, at, active }) => {
  const a = clamp01(reveal(t, at, 0.5));
  const big = cell.h > 150;
  const textSize = fitFontSize(item.text, cell.w - 36, big ? 32 : 28, 18, 0.02);
  const descSize = item.desc ? fitFontSize(item.desc, cell.w - 36, 22, 14) : 0;
  const glow = active ? 0.5 + 0.5 * pulse(t, 1.6) : 0;
  return (
    <div
      style={{
        position: "absolute",
        left: cell.x,
        top: cell.y,
        width: cell.w,
        height: cell.h,
        borderRadius: 20,
        boxSizing: "border-box",
        padding: big ? 22 : 13,
        background: active
          ? `linear-gradient(160deg, ${S.primary}1f 0%, rgba(10,16,28,0.92) 60%)`
          : "linear-gradient(160deg, rgba(16,26,44,0.82) 0%, rgba(7,12,22,0.90) 100%)",
        border: `1px solid rgba(232,198,110,${0.22 + 0.55 * glow})`,
        boxShadow: active
          ? `0 0 ${22 + 16 * glow}px rgba(232,198,110,${0.16 + 0.14 * glow}), 0 10px 26px rgba(0,0,0,0.5)`
          : "0 8px 22px rgba(0,0,0,0.45)",
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        gap: big ? 10 : 6,
        opacity: a,
        transform: `translateY(${(1 - a) * 26}px) scale(${0.94 + 0.06 * a + (active ? 0.02 : 0)})`,
      }}
    >
      {item.num ? (
        <span
          style={{
            position: "absolute",
            top: 10,
            right: 14,
            fontFamily: FONT.family,
            fontSize: 22,
            fontWeight: 800,
            color: S.primary,
          }}
        >
          {item.num}
        </span>
      ) : null}
      {item.icon ? (
        <Glyph
          name={item.icon}
          size={big ? 44 : 32}
          color={active ? S.primaryBright : S.primary}
        />
      ) : null}
      <span
        style={{
          fontFamily: FONT.family,
          fontSize: textSize,
          fontWeight: 700,
          color: active ? S.primaryBright : S.text,
          textAlign: "center",
          lineHeight: 1.2,
          letterSpacing: 0.5,
        }}
      >
        {item.text}
      </span>
      {item.desc ? (
        <span
          style={{
            fontFamily: FONT.family,
            fontSize: descSize,
            color: S.textSoft,
            textAlign: "center",
            lineHeight: 1.35,
          }}
        >
          {item.desc}
        </span>
      ) : null}
    </div>
  );
};

/** 三角形连线（仅 3 项布局）：顶点间画金色细线，pathLength 归一化做描绘动画 */
const TriangleLines: React.FC<{ cells: Cell[]; t: number; at: number }> = ({
  cells,
  t,
  at,
}) => {
  const [top, left, right] = cells;
  if (!top || !left || !right) return null;
  const p = clamp01(easeOutCubic(win(t, at + 0.3, at + 0.9)));
  const cxTop = top.x + top.w / 2;
  const yTop = top.y + top.h;
  const cxL = left.x + left.w / 2;
  const cxR = right.x + right.w / 2;
  const yBot = left.y;
  const midY = left.y + left.h / 2;
  return (
    <svg
      style={{ position: "absolute", inset: 0, pointerEvents: "none" }}
      width="100%"
      height="100%"
      viewBox={`0 0 912 ${GRID_H}`}
    >
      <g stroke={S.primary} strokeWidth={2} fill="none" opacity={0.45}>
        <line x1={cxTop} y1={yTop} x2={cxL} y2={yBot} pathLength={1}
          strokeDasharray="1" strokeDashoffset={1 - p} />
        <line x1={cxTop} y1={yTop} x2={cxR} y2={yBot} pathLength={1}
          strokeDasharray="1" strokeDashoffset={1 - p} />
        <line x1={left.x + left.w} y1={midY} x2={right.x} y2={midY} pathLength={1}
          strokeDasharray="1" strokeDashoffset={1 - p} />
      </g>
    </svg>
  );
};

/* ================= 金句（大字体 + 逐字入场动画） ================= */

const GoldenLine: React.FC<{ text: string; t: number; at: number }> = ({
  text,
  t,
  at,
}) => {
  const size = fitFontSize(text, 912 - 56, 62, 34, 0.02);
  const chars = [...text];
  return (
    <div style={{ position: "relative", paddingLeft: 28, height: 76 }}>
      {/* 左侧金条：随入场自上而下生长 */}
      <div
        style={{
          position: "absolute",
          left: 0,
          top: 8,
          bottom: 8,
          width: 6,
          borderRadius: 3,
          background: `linear-gradient(180deg, ${S.primaryBright}, ${S.primary})`,
          boxShadow: `0 0 14px ${S.primary}66`,
          transform: `scaleY(${clamp01(easeOutCubic(win(t, at, at + 0.4)))})`,
          transformOrigin: "top",
        }}
      />
      <div style={{ display: "flex", whiteSpace: "nowrap", alignItems: "center", height: "100%" }}>
        {chars.map((ch, i) => {
          const a = clamp01(easeOutCubic(win(t, at + 0.1 + i * 0.035, at + 0.1 + i * 0.035 + 0.26)));
          return (
            <span
              key={i}
              style={{
                fontFamily: FONT.family,
                fontSize: size,
                fontWeight: 800,
                lineHeight: 1,
                color: S.primaryBright,
                textShadow: `0 0 30px ${S.primary}55, 0 4px 16px rgba(0,0,0,0.85)`,
                opacity: a,
                transform: `translateY(${(1 - a) * 26}px)`,
                display: "inline-block",
              }}
            >
              {ch}
            </span>
          );
        })}
      </div>
    </div>
  );
};

/* ================= 封面（p1） ================= */

const CoverBlock: React.FC<{
  tag: string;
  title: string;
  subtitle: string;
  t: number;
}> = ({ tag, title, subtitle, t }) => {
  const ta = clamp01(reveal(t, 0.45, 0.6));
  return (
    <div
      style={{
        position: "absolute",
        left: 0,
        right: 0,
        top: 292,
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        gap: 0,
      }}
    >
      {/* 标签 */}
      <div
        style={{
          padding: "10px 28px",
          borderRadius: 999,
          border: `1px solid ${S.cardBorder}`,
          background: "rgba(8,12,20,0.72)",
          fontFamily: FONT.family,
          fontSize: 30,
          fontWeight: 600,
          color: S.primary,
          letterSpacing: 4,
          opacity: fadeIn(t, 0.25, 0.5),
        }}
      >
        {tag}
      </div>
      {/* 主标题 */}
      <div
        style={{
          marginTop: 56,
          fontFamily: FONT.family,
          fontSize: 150,
          fontWeight: 800,
          letterSpacing: 10,
          lineHeight: 1,
          color: S.primaryBright,
          textShadow: `0 0 60px ${S.primary}55, 0 8px 30px rgba(0,0,0,0.85)`,
          opacity: ta,
          transform: `translateY(${(1 - ta) * 34}px) scale(${0.92 + 0.08 * ta})`,
        }}
      >
        {title}
      </div>
      {/* 副标题 */}
      <div
        style={{
          marginTop: 44,
          fontFamily: FONT.family,
          fontSize: 46,
          fontWeight: 600,
          letterSpacing: 6,
          color: S.textSoft,
          opacity: fadeIn(t, 1.0, 0.5),
        }}
      >
        {subtitle}
      </div>
    </div>
  );
};

/* ================= 场景 ================= */

export const MediaScene: React.FC<Props> = ({
  page,
  media,
  overlay,
  pageIndex,
  totalPages = 6,
}) => {
  const t = usePageT();
  const { fps } = useVideoConfig();

  // 当前镜头（取对应素材）
  let si = 0;
  for (let i = 0; i < page.shots.length; i++) {
    if (page.shots[i].start <= t + 1e-6) si = i;
  }
  const shot = page.shots[si];
  const file = media[shot?.id ?? ""];

  const spec: MediaSpec = {
    kind: file ? "video" : "none",
    file,
    zoom: 0.1,
    pan: si % 2 === 0 ? "right" : "left",
    dim: 0.55, // ★ 中间调压暗 ≈0.30（MediaLayer 内 dim*0.55）：视频可见且保住深色底
    durationInFrames: shot?.durationFrames ?? 1,
  };

  /* ---------- 触发器（跨镜头找词，找不到退回页尾前 1s） ---------- */
  const tSection = overlay.section ? 0.05 : 1e9;
  const tBanner = overlay.banner
    ? overlay.banner.triggerWord
      ? triggerAny(page, overlay.banner.triggerWord, page.duration - 1.0)
      : page.duration - 1.2
    : 1e9;
  const tNum = overlay.bigNumber?.triggerWord
    ? triggerAny(page, overlay.bigNumber.triggerWord, 1.0)
    : 1e9;

  const numP = clamp01((t - tNum) / 1.2);
  const num = overlay.bigNumber
    ? Math.round(overlay.bigNumber.value * (1 - Math.pow(1 - numP, 3)))
    : 0;

  /* ---------- 关键词：入场时刻（紧凑） + 语音高亮窗口（解耦） ----------
     教训：早期「入场时刻 = 触发词时刻」，p5 三条红线里第三个词说得晚，
     正三角布局会长时间只剩两条腿（画面缺角像 bug）。现拆成两套时间：
       kEnter —— 整组在 ~0.6s 内依次浮现，版式立刻完整；
       kHi    —— 严格跟语音，说到哪个词哪张卡发光。 */
  const kws = overlay.keywords ?? [];
  const kBase = overlay.section ? tSection : 0.4; // 无章节头的页面也要能出场
  const kEnter = kws.map((_, i) => kBase + 0.3 + i * 0.2);
  const kHi = kws.map((k, i) =>
    k.triggerWord ? triggerAny(page, k.triggerWord, kEnter[i] + 0.2) : kEnter[i] + 0.2,
  );
  const cells = gridCells(kws.length, 912, GRID_H, 22);
  const kActive = kws.map((_, i) => {
    if (!kws[i].triggerWord) return false;
    const from = kHi[i];
    const to = i + 1 < kws.length && kws[i + 1].triggerWord ? kHi[i + 1] : from + 3.0;
    return t >= from && t < to;
  });

  /* ---------- 金句：触发时刻 ---------- */
  const goldens = overlay.golden ?? [];
  const gAt = goldens.map((g, i) =>
    g.triggerWord ? triggerAny(page, g.triggerWord, 0.6 + i * 0.4) : 0.6 + i * 0.4,
  );

  return (
    <SceneFade t={t} pageDur={page.duration}>
      <MediaLayer spec={spec} />
      <Atmosphere glow="center" intensity={0.85} grain={S.grain} warm={0.3} />

      <BrandChip t={t} />

      {overlay.section ? (
        <SectionHeader
          t={t}
          at={tSection}
          label={overlay.section.label}
          title={overlay.section.title}
        />
      ) : null}

      {/* ============ 封面（p1） ============ */}
      {overlay.cover ? (
        <CoverBlock
          tag={overlay.cover.tag}
          title={overlay.cover.title}
          subtitle={overlay.cover.subtitle}
          t={t}
        />
      ) : null}

      {/* ============ 金句（大字体逐字动画） ============ */}
      {goldens.map((g, i) => (
        <div
          key={g.text}
          style={{
            position: "absolute",
            left: LAYOUT.marginX,
            right: LAYOUT.marginX,
            top: GOLDEN_TOP + i * GOLDEN_STEP,
          }}
        >
          <GoldenLine text={g.text} t={t} at={gAt[i]} />
        </div>
      ))}

      {/* ============ 关键词卡片（自适应布局） ============ */}
      {kws.length ? (
        <div
          style={{
            position: "absolute",
            left: LAYOUT.marginX,
            right: LAYOUT.marginX,
            top: GRID_TOP,
            height: GRID_H,
          }}
        >
          {kws.length === 3 ? (
            <TriangleLines cells={cells} t={t} at={kBase} />
          ) : null}
          {cells.map((cell, i) => (
            <KeywordCard
              key={kws[i].text}
              item={kws[i]}
              cell={cell}
              t={t}
              at={kEnter[i]}
              active={kActive[i]}
            />
          ))}
        </div>
      ) : null}

      {/* ============ 大数字（滚动计数） ============ */}
      {overlay.bigNumber && t >= tNum - 0.2 ? (
        <div
          style={{
            position: "absolute",
            left: LAYOUT.marginX,
            right: LAYOUT.marginX,
            top: overlay.cover ? BIGNUM_COVER_TOP : BIGNUM_TOP,
            display: "flex",
            flexDirection: "column",
            alignItems: "center",
            gap: 10,
            opacity: clamp01(numP * 1.4),
          }}
        >
          <div style={{ display: "flex", alignItems: "baseline", gap: 12 }}>
            <span
              style={{
                fontFamily: FONT.family,
                fontSize: overlay.cover ? 132 : 110,
                fontWeight: 800,
                color: S.primaryBright,
                lineHeight: 1,
                textShadow: `0 0 44px ${S.primary}66, 0 6px 20px rgba(0,0,0,0.8)`,
              }}
            >
              {num}
            </span>
            {overlay.bigNumber.suffix ? (
              <span
                style={{
                  fontFamily: FONT.family,
                  fontSize: 44,
                  fontWeight: 700,
                  color: S.primary,
                }}
              >
                {overlay.bigNumber.suffix}
              </span>
            ) : null}
          </div>
          <span
            style={{
              fontFamily: FONT.family,
              fontSize: 30,
              color: COLORS.inkSoft,
              letterSpacing: 2,
            }}
          >
            {overlay.bigNumber.label}
          </span>
        </div>
      ) : null}

      {/* ============ 底部结论条 ============ */}
      {overlay.banner && t >= tBanner - 0.1 ? (
        <div
          style={{
            position: "absolute",
            left: LAYOUT.marginX,
            right: LAYOUT.marginX,
            top: BANNER_TOP,
            height: 88,
            borderRadius: 18,
            background: `linear-gradient(135deg, ${S.primary}22 0%, rgba(10,16,28,0.92) 60%)`,
            border: `1px solid ${S.cardBorder}`,
            display: "flex",
            alignItems: "center",
            gap: 16,
            padding: "0 28px",
            opacity: clamp01(reveal(t, tBanner, 0.5)),
            boxShadow: `0 0 28px ${S.primary}22`,
          }}
        >
          <Glyph name={overlay.banner.icon ?? "sparkles"} size={38} color={S.primary} />
          <span
            style={{
              fontFamily: FONT.family,
              fontSize: fitFontSize(overlay.banner.text, 912 - 90, 34, 24, 0.02),
              fontWeight: 700,
              color: S.primaryBright,
              letterSpacing: 1,
              whiteSpace: "nowrap",
            }}
          >
            {overlay.banner.text}
          </span>
        </div>
      ) : null}

      <PageNum t={t} n={pageIndex} total={totalPages} />

      {/* ============ 音效（轻量，不抢旁白） ============ */}
      {overlay.cover ? <Sfx file="whoosh.mp3" at={0.4} volume={0.16} fps={fps} /> : null}
      {overlay.section ? <Sfx file="whoosh.mp3" at={tSection} volume={0.14} fps={fps} /> : null}
      {goldens.map((g, i) => (
        <Sfx key={`sfx-g${i}`} file="whoosh.mp3" at={gAt[i]} volume={0.15} fps={fps} />
      ))}
      {kws.map((k, i) => (
        <Sfx key={`sfx-k${i}`} file="pop.mp3" at={kEnter[i]} volume={0.13} fps={fps} />
      ))}
      {overlay.bigNumber ? (
        <Sfx file="sparkle.mp3" at={tNum} volume={0.2} fps={fps} />
      ) : null}
      {overlay.banner ? (
        <Sfx file="alert.mp3" at={tBanner} volume={0.2} fps={fps} />
      ) : null}
    </SceneFade>
  );
};
