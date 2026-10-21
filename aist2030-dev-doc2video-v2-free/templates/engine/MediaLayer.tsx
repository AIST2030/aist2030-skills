import React from "react";
import {
  AbsoluteFill,
  Sequence,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
  Video,
} from "remotion";
import { S, clamp01, easeOutCubic } from "./theme";
import durations from "./data/mediaDurations.json";

/**
 * 素材层（通道 A）★ 2026-10-18 重写：**一页多素材播放列表**。
 *
 * 用户需求：视频素材时长与页面内容常常不匹配——单素材会出现停滞/卡顿/
 * 重复播放；素材不够就拼接多个，不要限制一个页面只播一个背景视频。
 *
 * 设计：
 *  1) spec.clips = 播放列表（≥1 个）。按素材**真实时长**（mediaDurations.json，
 *     由 scripts/gen_media_durations.py 用 ffmpeg 实测）顺序排段，
 *     段与段之间 XFADE 秒交叉淡接；整页不够长就循环列表再排一轮。
 *  2) 每段独立 Ken Burns（zoom/pan 逐段交替），段内进度按段时长算。
 *  3) 调色仍烘在 ffmpeg 转码里；渲染层禁 CSS filter / mixBlendMode（卡顿教训）。
 *  4) 列表为空 → 回退渐变底，绝不白屏。
 */

export type MediaKind = "video" | "none";

export interface MediaClip {
  /** public/media/ 下的文件名（含扩展名，不含目录） */
  file: string;
  /** Ken Burns 缩放幅度，0 表示不动 */
  zoom?: number;
  /** 平移方向 */
  pan?: "none" | "left" | "right" | "up" | "down";
}

export interface MediaSpec {
  kind: MediaKind;
  clips: MediaClip[];
  /** 本页时长（帧）——播放列表排布的总预算 */
  durationInFrames: number;
  /** 整体压暗程度 0-1（实拍垫片建议 0.4~0.55） */
  dim?: number;
}

const DUR = durations as Record<string, number>;
const XFADE = 0.6; // 段间交叉淡接（秒）
const MIN_SEG = 1.6; // 单段最短展示（秒）
const MAX_SEG = 6.5; // ★ 单段最长展示（秒）：长素材到点交棒下一个，
// 避免"整页一条视频"的停滞感（2026-10-18 用户需求：画面不要停/不要重复播）

const VideoTag = Video as unknown as React.FC<{
  src: string;
  muted?: boolean;
  style?: React.CSSProperties;
}>;

interface Segment {
  clip: MediaClip;
  /** 段起始（帧，页内） */
  from: number;
  /** 段主体时长（帧，不含淡接尾巴） */
  durF: number;
  /** 是否带淡入（首段不带） */
  fadeIn: boolean;
  panDir: "left" | "right" | "up" | "down";
  zoom: number;
  idx: number;
}

/** 把播放列表铺满页时长：顺序排段 + 循环续排 */
const buildSegments = (
  clips: MediaClip[],
  pageFrames: number,
  fps: number,
): Segment[] => {
  const segs: Segment[] = [];
  if (!clips.length || pageFrames <= 0) return segs;
  const xf = Math.round(XFADE * fps);
  let cursor = 0;
  let i = 0;
  while (cursor < pageFrames - fps * 0.25) {
    const clip = clips[i % clips.length];
    const realDur = DUR[clip.file] ?? 10;
    // 段主体 = min(素材实际时长, MAX_SEG) - 淡接；最短保底
    const durF = Math.max(
      Math.round(MIN_SEG * fps),
      Math.min(Math.round(realDur * fps), Math.round(MAX_SEG * fps)) - xf,
    );
    const from = cursor;
    const fadeIn = segs.length > 0;
    segs.push({
      clip,
      from,
      durF,
      fadeIn,
      panDir: (["left", "right", "up", "down"] as const)[segs.length % 4],
      zoom: clip.zoom ?? 0.1,
      idx: segs.length,
    });
    cursor = from + durF;
    i += 1;
    if (segs.length > 24) break; // 安全上限
  }
  return segs;
};

const ClipSegment: React.FC<{ seg: Segment; fps: number; total: number }> = ({
  seg,
  fps,
  total,
}) => {
  const frame = useCurrentFrame();
  // 段内进度（含淡接尾巴，让缓动走满整段）
  const p = clamp01((frame - seg.from) / Math.max(1, seg.durF));
  const scale = 1 + seg.zoom * p;
  const panPx = 44;
  const pan =
    seg.panDir === "left"
      ? { x: -panPx * p, y: 0 }
      : seg.panDir === "right"
        ? { x: panPx * p, y: 0 }
        : seg.panDir === "up"
          ? { x: 0, y: -panPx * p }
          : { x: 0, y: panPx * p };
  const inA = seg.fadeIn
    ? easeOutCubic(clamp01((frame - seg.from) / Math.max(1, Math.round(XFADE * fps))))
    : 1;
  // 末段收尾：页尾 0.4s 淡出（交给 SceneFade，也可省略）
  const outA = 1;
  return (
    <AbsoluteFill style={{ opacity: clamp01(inA * outA) }}>
      <div
        style={{
          position: "absolute",
          inset: -60,
          transform: `scale(${scale}) translate(${pan.x}px, ${pan.y}px)`,
        }}
      >
        <VideoTag
          src={staticFile(`media/${seg.clip.file}`)}
          muted
          style={{ width: "100%", height: "100%", objectFit: "cover" }}
        />
      </div>
    </AbsoluteFill>
  );
};

export const MediaLayer: React.FC<{ spec: MediaSpec }> = ({ spec }) => {
  const { fps } = useVideoConfig();
  const pageFrames = spec.durationInFrames ?? 0;
  const clips = spec.kind === "video" ? spec.clips.filter((c) => c.file) : [];
  const segs = React.useMemo(() => buildSegments(clips, pageFrames, fps), [
    spec.kind,
    pageFrames,
    fps,
    clips.length,
  ]);
  const dim = spec.dim ?? 0.55;

  if (spec.kind === "none" || !clips.length) {
    return (
      <AbsoluteFill
        style={{
          background: `radial-gradient(120% 90% at 50% 42%, ${S.bg} 0%, #000000 76%)`,
        }}
      />
    );
  }

  return (
    <AbsoluteFill style={{ backgroundColor: "#000000", overflow: "hidden" }}>
      {segs.map((seg) => (
        <Sequence
          key={`${seg.clip.file}#${seg.idx}`}
          from={seg.from}
          durationInFrames={seg.durF + Math.round(XFADE * fps)}
          name={`clip-${seg.clip.file}`}
        >
          <ClipSegment seg={seg} fps={fps} total={pageFrames} />
        </Sequence>
      ))}

      {/* 压暗渐变：底部加重（给字幕让位），上 2/3 保持通透——实拍视频必须可见 */}
      <AbsoluteFill
        style={{
          background: `linear-gradient(180deg, ${S.tint} 0%, rgba(0,0,0,${dim * 0.55}) 40%, rgba(0,0,0,${Math.min(0.72, dim * 0.55 + 0.26)}) 80%, rgba(0,0,0,0.86) 100%)`,
        }}
      />
      {/* 暗角：把视线收到画面中心（文字主体） */}
      <AbsoluteFill
        style={{
          background: `radial-gradient(118% 86% at 50% 44%, rgba(0,0,0,0) 38%, rgba(0,0,0,${S.vignette}) 100%)`,
        }}
      />
      {S.letterbox > 0 ? (
        <>
          <div style={{ position: "absolute", top: 0, left: 0, right: 0, height: S.letterbox, background: "#000000" }} />
          <div style={{ position: "absolute", bottom: 0, left: 0, right: 0, height: S.letterbox, background: "#000000" }} />
        </>
      ) : null}
    </AbsoluteFill>
  );
};
