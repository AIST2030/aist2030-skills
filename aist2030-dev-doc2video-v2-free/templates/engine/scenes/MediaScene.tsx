import React from "react";
import {
  AbsoluteFill,
  Audio as RawAudio,
  Sequence,
  useVideoConfig,
} from "remotion";
import type { PageData } from "../types";
import { MediaLayer, type MediaSpec, type MediaClip } from "../MediaLayer";
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
  easeOutBack,
  easeOutCubic,
  fadeIn,
  fitFontSize,
  pickVariant,
  pulse,
  reveal,
  win,
} from "../theme";
import { triggerAny, usePageT } from "../Caption";
import { sfxFile } from "../sfxConfig";
import { PipOverlay } from "../PipOverlay";

/**
 * 通用混剪场景：实拍素材打底（通道A）+ **提炼信息主体**图形叠加（通道B）。
 *
 * ★ 2026-10-18 版本（贵阳本地消费选题）：
 *   1) 主画面 = 提炼内容：封面 / 金句 / 关键词卡片 / 大数字 / 结论条，每页 1-2 类；
 *   2) 完整讲稿走底部单行卡拉OK字幕（Caption），主屏不搬全文；
 *   3) 背景视频改**播放列表**：一页可拼多个素材，交叉淡接，不再单素材循环卡顿；
 *   4) 文字/形状动效按索引自适应挑变体（rise / 交替滑入 / 弹性缩放 / 翻转入场），
 *      全部只动 transform+opacity，不碰 CSS filter（渲染性能红线）；
 *   5) 音效仅入场点轻点缀，无 BGM（用户明令）。
 */

/* ================= 叠加配置类型 ================= */

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
  cover?: { tag: string; title: string; subtitle: string };
  section?: { label: string; title: string };
  golden?: { text: string; triggerWord?: string }[];
  keywords?: KeywordItem[];
  bigNumber?: { value: number; suffix?: string; label: string; triggerWord?: string };
  banner?: { text: string; icon?: GlyphName; triggerWord?: string };
}

interface Props {
  page: PageData;
  /** 本页播放列表：public/media/ 文件名数组（顺序播放，交叉淡接，不够长循环） */
  playlist: string[];
  overlay: OverlaySpec;
  pageIndex: number;
  totalPages?: number;
}

/* ================= 垂直分区（1080×1440 画布） ================= */
const GOLDEN_TOP = 356;
const GOLDEN_STEP = 96;
const GRID_TOP = 596;
const GRID_H = 426;
const BANNER_TOP = 1146;
const BIGNUM_COVER_TOP = 700;
const BIGNUM_TOP = 1024;

/* ================= 音效 ================= */
const Audio = RawAudio as unknown as React.FC<{
  src: string;
  volume?: number | ((frame: number) => number);
}>;

const Sfx: React.FC<{
  file: string;
  at: number;
  volume?: number;
  fps: number;
}> = ({ file, at, volume = 0.18, fps }) => {
  if (!(at >= 0) || at > 1e8) return null;
  // ★ 音效一律走内联 data URI（sfxConfig.sfxFile → embed_sfx.py 生成的
  //   src/data/sfxData.ts）。staticFile 音频在长渲染中是确定性崩溃地雷
  //   （MediaError → cancelRender，Error Boundary 拦不住）；
  //   在 still/QC 中表现为 `Loading <Audio> duration` delayRender 超时。
  //   传空串（用户未勾选该触发点音效）→ 静音。
  if (!file) return null;
  const frame = Math.max(0, Math.round(at * fps));
  return (
    <Sequence from={frame} durationInFrames={150}>
      <Audio src={file} volume={volume} />
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

/* ================= 关键词卡片（多套入场变体） ================= */

type CardVariant = "rise" | "slideX" | "drop" | "flip";
const CARD_VARIANTS: CardVariant[] = ["rise", "slideX", "drop", "flip"];

const cardTransform = (v: CardVariant, a: number): string => {
  const off = (1 - a) * 100;
  switch (v) {
    case "slideX":
      return `translateX(${-off * 0.5}px)`;
    case "drop":
      return `translateY(${-off * 0.4}px) scale(${0.9 + 0.1 * a})`;
    case "flip":
      return `perspective(900px) rotateY(${(1 - a) * 26}deg) scale(${0.94 + 0.06 * a})`;
    default:
      return `translateY(${(1 - a) * 26}px) scale(${0.94 + 0.06 * a})`;
  }
};

const KeywordCard: React.FC<{
  item: KeywordItem;
  cell: Cell;
  t: number;
  at: number;
  active: boolean;
  variant: CardVariant;
}> = ({ item, cell, t, at, active, variant }) => {
  const raw = win(t, at, at + 0.5);
  // rise/slideX 用平滑曲线，drop/flip 用回弹
  const a =
    variant === "drop" || variant === "flip"
      ? clamp01(easeOutBack(raw))
      : clamp01(easeOutCubic(raw));
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
          ? `linear-gradient(160deg, ${S.primary}26 0%, ${S.cardBg} 60%)`
          : S.cardBg,
        border: `1px solid ${S.cardBorder}`,
        boxShadow: active
          ? `0 0 ${22 + 16 * glow}px ${S.primary}${Math.round(0.16 * 255 + 0.14 * glow * 255).toString(16).padStart(2, "0")}, 0 10px 26px rgba(0,0,0,0.5)`
          : "0 8px 22px rgba(0,0,0,0.45)",
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        gap: big ? 10 : 6,
        opacity: a,
        transform: `${cardTransform(variant, a)}${active ? " scale(1.02)" : ""}`,
      }}
    >
      {/* 左上角小三角标（形状层点缀） */}
      <div
        style={{
          position: "absolute",
          left: 0,
          top: 0,
          width: 0,
          height: 0,
          borderLeft: `14px solid ${S.primary}${active ? "cc" : "55"}`,
          borderBottom: "14px solid transparent",
          borderTopLeftRadius: 20,
        }}
      />
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

/** 三角形连线（仅 3 项布局） */
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

/* ================= 金句（大字体 · 三套逐字变体） ================= */

type GoldenVariant = "rise" | "altSlide" | "popScale";
const GOLDEN_VARIANTS: GoldenVariant[] = ["rise", "altSlide", "popScale"];

const GoldenLine: React.FC<{
  text: string;
  t: number;
  at: number;
  variant: GoldenVariant;
}> = ({ text, t, at, variant }) => {
  const size = fitFontSize(text, 912 - 56, 62, 34, 0.02);
  const chars = [...text];
  return (
    <div style={{ position: "relative", paddingLeft: 28, height: 76 }}>
      {/* 左侧色条：随入场自上而下生长 */}
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
          const st = at + 0.1 + i * 0.035;
          const a = clamp01(easeOutCubic(win(t, st, st + 0.26)));
          let transform = `translateY(${(1 - a) * 26}px)`;
          if (variant === "altSlide") {
            const dir = i % 2 === 0 ? -1 : 1;
            transform = `translateX(${dir * (1 - a) * 34}px) rotate(${dir * (1 - a) * 5}deg)`;
          } else if (variant === "popScale") {
            const b = clamp01(easeOutBack(win(t, st, st + 0.32)));
            transform = `scale(${0.4 + 0.6 * b})`;
          }
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
                transform,
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
  const ta = clamp01(easeOutBack(win(t, 0.45, 1.05)));
  const chars = [...title];
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
      <div
        style={{
          padding: "10px 28px",
          borderRadius: 999,
          border: `1px solid ${S.cardBorder}`,
          background: S.cardBg,
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
      {/* 主标题：逐字弹性入场 */}
      <div style={{ marginTop: 56, display: "flex" }}>
        {chars.map((ch, i) => {
          const st = 0.5 + i * 0.09;
          const b = clamp01(easeOutBack(win(t, st, st + 0.42)));
          return (
            <span
              key={i}
              style={{
                fontFamily: FONT.family,
                fontSize: 150,
                fontWeight: 800,
                letterSpacing: 10,
                lineHeight: 1,
                color: S.primaryBright,
                textShadow: `0 0 60px ${S.primary}55, 0 8px 30px rgba(0,0,0,0.85)`,
                opacity: clamp01(b),
                transform: `translateY(${(1 - b) * 40}px) scale(${0.8 + 0.2 * b})`,
                display: "inline-block",
              }}
            >
              {ch}
            </span>
          );
        })}
      </div>
      <div
        style={{
          marginTop: 44,
          fontFamily: FONT.family,
          fontSize: 46,
          fontWeight: 600,
          letterSpacing: 6,
          color: S.textSoft,
          opacity: fadeIn(t, 1.0, 0.5),
          transform: `translateY(${(1 - clamp01(fadeIn(t, 1.0, 0.5))) * 18}px)`,
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
  playlist,
  overlay,
  pageIndex,
  totalPages = 5,
}) => {
  const t = usePageT();
  const { fps } = useVideoConfig();

  /* ---------- 背景播放列表（一页多素材，交叉淡接，不够长循环） ---------- */
  const clips: MediaClip[] = playlist.map((file, i) => ({
    file,
    zoom: 0.1 + (i % 2) * 0.03,
    pan: (["right", "left", "down", "up"] as const)[i % 4],
  }));
  const spec: MediaSpec = {
    kind: clips.length ? "video" : "none",
    clips,
    dim: 0.55,
    durationInFrames: page.durationFrames,
  };

  /* ---------- 触发器 ---------- */
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

  /* ---------- 关键词：入场与高亮解耦 ---------- */
  const kws = overlay.keywords ?? [];
  const kBase = overlay.section ? tSection : 0.4;
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
  // ★ 动效变体按索引确定性挑选，相邻不同款
  const kVariants = kws.map((_, i) =>
    pickVariant(CARD_VARIANTS, i, page.startFrame),
  );

  /* ---------- 金句 ---------- */
  const goldens = overlay.golden ?? [];
  const gAt = goldens.map((g, i) =>
    g.triggerWord ? triggerAny(page, g.triggerWord, 0.6 + i * 0.4) : 0.6 + i * 0.4,
  );
  const gVariants = goldens.map((_, i) =>
    pickVariant(GOLDEN_VARIANTS, i, page.startFrame + 7),
  );

  return (
    <SceneFade t={t} pageDur={page.duration}>
      <MediaLayer spec={spec} />
      <Atmosphere glow="center" intensity={0.85} grain={S.grain} warm={0.3} />

      <BrandChip t={t} />
      <PipOverlay />

      {overlay.section ? (
        <SectionHeader
          t={t}
          at={tSection}
          label={overlay.section.label}
          title={overlay.section.title}
        />
      ) : null}

      {/* ============ 封面 ============ */}
      {overlay.cover ? (
        <CoverBlock
          tag={overlay.cover.tag}
          title={overlay.cover.title}
          subtitle={overlay.cover.subtitle}
          t={t}
        />
      ) : null}

      {/* ============ 金句 ============ */}
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
          <GoldenLine text={g.text} t={t} at={gAt[i]} variant={gVariants[i]} />
        </div>
      ))}

      {/* ============ 关键词卡片 ============ */}
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
              variant={kVariants[i]}
            />
          ))}
        </div>
      ) : null}

      {/* ============ 大数字（滚动计数 + 进度环） ============ */}
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
            transform: `scale(${0.9 + 0.1 * clamp01(easeOutBack(numP))})`,
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: 22 }}>
            <svg width={26} height={26} viewBox="0 0 36 36" style={{ opacity: 0.9 }}>
              <circle cx="18" cy="18" r="15" fill="none" stroke={`${S.primary}33`} strokeWidth={4} />
              <circle
                cx="18" cy="18" r="15" fill="none" stroke={S.primary} strokeWidth={4}
                strokeLinecap="round"
                strokeDasharray={2 * Math.PI * 15}
                strokeDashoffset={2 * Math.PI * 15 * (1 - numP)}
                transform="rotate(-90 18 18)"
              />
            </svg>
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

      {/* ============ 底部结论条（扫光条动画） ============ */}
      {overlay.banner && t >= tBanner - 0.1 ? (
        <div
          style={{
            position: "absolute",
            left: LAYOUT.marginX,
            right: LAYOUT.marginX,
            top: BANNER_TOP,
            height: 88,
            borderRadius: 18,
            background: `linear-gradient(135deg, ${S.primary}26 0%, ${S.cardBg} 60%)`,
            border: `1px solid ${S.cardBorder}`,
            display: "flex",
            alignItems: "center",
            gap: 16,
            padding: "0 28px",
            opacity: clamp01(reveal(t, tBanner, 0.5)),
            boxShadow: `0 0 28px ${S.primary}22`,
            overflow: "hidden",
          }}
        >
          {/* 扫光：亮带从左到右周期滑过（只动 transform，廉价） */}
          <div
            style={{
              position: "absolute",
              top: 0,
              bottom: 0,
              width: 120,
              left: `${((t * 0.55) % 1.4) * 130 - 20}%`,
              background: `linear-gradient(100deg, transparent 0%, ${S.primaryBright}2e 50%, transparent 100%)`,
              pointerEvents: "none",
            }}
          />
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

      {/* ============ 音效（sfxConfig 驱动，尊重用户勾选） ============ */}
      {/*★ 每组必须给「类型前缀 + 触发时刻」的稳定 key：同一页里不同触发点可能映射到
          同一个音频文件，无 key 的相邻 <Sfx> 会被 React 复用同一实例 → src 中途被替换
          → Chrome 报 MediaError 整片中断。key 里带 at 避免同类型多次触发互相顶掉。 */}
      {overlay.cover ? (
        <Sfx key="sfx-cover" file={sfxFile("cover")} at={0.4} volume={0.16} fps={fps} />
      ) : null}
      {overlay.section ? (
        <Sfx key="sfx-section" file={sfxFile("section")} at={tSection} volume={0.14} fps={fps} />
      ) : null}
      {goldens.map((g, i) => (
        <Sfx key={`sfx-golden-${i}-${Math.round(gAt[i] * 100)}`} file={sfxFile("golden")} at={gAt[i]} volume={0.15} fps={fps} />
      ))}
      {kws.map((k, i) => (
        <Sfx key={`sfx-kw-${i}-${Math.round(kEnter[i] * 100)}`} file={sfxFile("keywordEnter")} at={kEnter[i]} volume={0.13} fps={fps} />
      ))}
      {overlay.bigNumber ? (
        <Sfx key="sfx-bignum" file={sfxFile("bigNumber")} at={tNum} volume={0.2} fps={fps} />
      ) : null}
      {overlay.banner ? (
        <Sfx key="sfx-banner" file={sfxFile("banner")} at={tBanner} volume={0.2} fps={fps} />
      ) : null}
    </SceneFade>
  );
};
