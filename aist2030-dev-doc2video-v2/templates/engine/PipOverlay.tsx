import React from "react";
import {
  AbsoluteFill,
  Easing,
  interpolate,
  staticFile,
  useCurrentFrame,
  Video,
} from "remotion";
import { FONT, S } from "./theme";
import { PIP } from "./pipConfig";

/**
 * 画中画（用户提供的真人/讲解员视频），常驻角落。
 * 可行性评估结论：完全可行 —— Remotion <Video> 直接渲染用户文件，
 * 圆角裁切 + 主色描边 + 入场缩放，不干扰主画面与字幕。
 * 文件由用户提供（竖版最佳，建议 480×640 以上、无声或低音量），
 * 放入 remotion/public/pip/pip.mp4 并把 pipConfig.enabled 改 true 即生效。
 */
export const PipOverlay: React.FC = () => {
  if (!PIP.enabled) return null;
  const frame = useCurrentFrame();
  const size = PIP.size;
  const top = 1440 - PIP.bottomGap - size;
  const right =
    PIP.position === "bottomRight"
      ? 1080 - size - PIP.margin
      : PIP.margin;
  const sc = interpolate(frame, [0, 20], [0.82, 1], {
    extrapolateRight: "clamp",
    easing: Easing.out(Easing.cubic),
  });
  const op = interpolate(frame, [0, 20], [0, 1], {
    extrapolateRight: "clamp",
  });
  return (
    <AbsoluteFill style={{ pointerEvents: "none" }}>
      <div
        style={{
          position: "absolute",
          top,
          left: right,
          width: size,
          height: size,
          borderRadius: 26,
          overflow: "hidden",
          border: `2px solid ${S.primary}`,
          boxShadow: `0 14px 44px rgba(0,0,0,0.55), 0 0 0 1px ${S.primary}55`,
          transform: `scale(${sc})`,
          opacity: op,
        }}
      >
        <Video
          src={staticFile(PIP.file)}
          muted
          loop
          startFrom={0}
          style={{ width: "100%", height: "100%", objectFit: "cover" }}
        />
        {/* 主色细描边内圈，强化科技感 */}
        <div
          style={{
            position: "absolute",
            inset: 0,
            borderRadius: 24,
            border: `1px solid ${S.primary}66`,
            boxShadow: `inset 0 0 30px rgba(0,0,0,0.35)`,
          }}
        />
        <div
          style={{
            position: "absolute",
            left: 0,
            right: 0,
            bottom: 0,
            padding: "6px 10px",
            background:
              "linear-gradient(0deg, rgba(2,8,14,0.78), rgba(2,8,14,0))",
            fontFamily: FONT.family,
            fontSize: 22,
            fontWeight: 600,
            color: S.primaryBright,
            textAlign: "center",
          }}
        >
          讲解
        </div>
      </div>
    </AbsoluteFill>
  );
};
