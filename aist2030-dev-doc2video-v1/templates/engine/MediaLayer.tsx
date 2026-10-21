import React from "react";
import {
  AbsoluteFill,
  staticFile,
  useCurrentFrame,
  Video,
} from "remotion";
import { S, clamp01 } from "./theme";

/**
 * 素材层（通道 A）：把 fetch_media.py 下好的实拍视频铺成镜头底片。
 *
 * 设计要点（踩过的坑都固化在这里）：
 *  1) ★ 调色**烘在 ffmpeg 转码里**（eq 饱和度/对比度 + gblur 柔化），
 *     渲染层**严禁**给视频容器加 CSS filter / mixBlendMode ——
 *     实测（2026-10-17）：那会让 Chrome 每帧重新光栅化视频层，
 *     1080×1440 成片明显卡顿。这里只留廉价渐变叠加。
 *  2) Ken Burns 进度必须按**镜头时长**算（durationInFrames 由场景传入），
 *     用全局帧会让缩放几乎不动（早期 bug：122s 的片里 6s 镜头只走了 5%）。
 *  3) 缺失兜底：素材没下到时回退渐变底，绝不白屏。
 *  4) 静音：素材音轨一律丢弃（fetch_media 已 -an，这里再保险一次）。
 */

export type MediaKind = "video" | "none";

export interface MediaSpec {
  /** public/media/ 下的文件名（含扩展名，不含目录） */
  file?: string;
  kind: MediaKind;
  /** Ken Burns 缩放幅度，0 表示不动 */
  zoom?: number;
  /** 平移方向 */
  pan?: "none" | "left" | "right" | "up" | "down";
  /** 整体压暗程度 0-1（实拍垫片建议 0.4~0.55，文字主体版式偏浓） */
  dim?: number;
  /** 本镜头时长（帧）——Ken Burns 进度的分母，必传 */
  durationInFrames?: number;
}

const VideoTag = Video as unknown as React.FC<{
  src: string;
  muted?: boolean;
  style?: React.CSSProperties;
}>;

export const MediaLayer: React.FC<{ spec: MediaSpec }> = ({ spec }) => {
  const frame = useCurrentFrame();

  if (spec.kind === "none" || !spec.file) {
    return (
      <AbsoluteFill
        style={{
          background: `radial-gradient(120% 90% at 50% 42%, ${S.bg} 0%, #000000 76%)`,
        }}
      />
    );
  }

  // ★ 按镜头时长算进度（不是全局帧）——单镜 6s 也能走完整段缓动
  const dur =
    spec.durationInFrames && spec.durationInFrames > 0
      ? spec.durationInFrames
      : 1;
  const p = clamp01(frame / dur);
  const zoom = spec.zoom ?? 0.1;
  const scale = 1 + zoom * p;
  const panPx = 48;
  const pan =
    spec.pan === "left"
      ? { x: -panPx * p, y: 0 }
      : spec.pan === "right"
        ? { x: panPx * p, y: 0 }
        : spec.pan === "up"
          ? { x: 0, y: -panPx * p }
          : spec.pan === "down"
            ? { x: 0, y: panPx * p }
            : { x: 0, y: 0 };
  const dim = spec.dim ?? 0.55;

  const src = staticFile(`media/${spec.file}`);

  return (
    <AbsoluteFill style={{ backgroundColor: "#000000", overflow: "hidden" }}>
      <div
        style={{
          position: "absolute",
          inset: -60,
          transform: `scale(${scale}) translate(${pan.x}px, ${pan.y}px)`,
        }}
      >
        <VideoTag
          src={src}
          muted
          style={{ width: "100%", height: "100%", objectFit: "cover" }}
        />
      </div>

      {/* 压暗渐变：**底部加重**（给字幕让位），上 2/3 保持通透——实拍视频必须可见。
          2026-10-17 用户反馈"背景看不到视频"：真因是转码 eq.brightness=1.08 把素材
          冲成纯白（见 fetch_media.py 注释），叠加层只是次要因素。现已双修：
          转码恢复正常影调 + 这里 dim≈0.30 的中间调压暗（保留画面质感与高光）。 */}
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
      {/* 电影感黑边 */}
      {S.letterbox > 0 ? (
        <>
          <div
            style={{
              position: "absolute",
              top: 0,
              left: 0,
              right: 0,
              height: S.letterbox,
              background: "#000000",
            }}
          />
          <div
            style={{
              position: "absolute",
              bottom: 0,
              left: 0,
              right: 0,
              height: S.letterbox,
              background: "#000000",
            }}
          />
        </>
      ) : null}
    </AbsoluteFill>
  );
};
