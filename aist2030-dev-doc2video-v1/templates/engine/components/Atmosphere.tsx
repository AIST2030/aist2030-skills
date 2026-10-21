import React from "react";
import { AbsoluteFill, staticFile } from "remotion";
import { COLORS, S } from "../theme";

/**
 * 全局氛围层：深蓝黑底 + 呼吸微光 + 胶片颗粒 + 暗角
 * 叠在每个场景之上，保证全片统一的电影质感
 *
 * ⚠ 性能纪律（2026-10-17 卡顿排查结论）：本层**禁用 mixBlendMode**。
 * 实测 CSS filter / blend mode 会让 Chrome 每帧重新光栅化，1080×1440
 * 成片明显卡顿。颗粒改用普通透明度叠加（视觉差异极小，成本为零）。
 */
export const Atmosphere: React.FC<{
  glow?: "center" | "top" | "bottom" | "none";
  intensity?: number;
  grain?: number;
  warm?: number; // 0-1，暖色偏移
}> = ({ glow = "center", intensity = 1, grain = 0.055, warm = 0.35 }) => {
  const pos =
    glow === "top" ? "50% 18%" : glow === "bottom" ? "50% 82%" : "50% 46%";
  return (
    <AbsoluteFill style={{ pointerEvents: "none" }}>
      {/* 主光晕（风格色） */}
      {glow !== "none" ? (
        <div
          style={{
            position: "absolute",
            inset: 0,
            background: `radial-gradient(120% 78% at ${pos}, rgba(${S.glowRgb},${0.1 * intensity}) 0%, rgba(18,32,54,${0.22 * intensity}) 34%, rgba(4,7,13,0) 68%)`,
          }}
        />
      ) : null}
      {/* 暖色偏移 */}
      <div
        style={{
          position: "absolute",
          inset: 0,
          background: `radial-gradient(140% 100% at 50% 50%, rgba(${S.glowRgb},${0.05 * warm}) 0%, rgba(4,7,13,0) 62%)`,
        }}
      />
      {/* 胶片颗粒（普通透明度叠加，不用混合模式） */}
      <img
        src={staticFile("noise.png")}
        style={{
          position: "absolute",
          width: "112%",
          height: "112%",
          left: "-6%",
          top: "-6%",
          opacity: grain,
        }}
      />
      {/* 暗角 */}
      <div
        style={{
          position: "absolute",
          inset: 0,
          background:
            "radial-gradient(100% 72% at 50% 50%, rgba(0,0,0,0) 42%, rgba(0,0,0,0.42) 78%, rgba(0,0,0,0.78) 100%)",
        }}
      />
    </AbsoluteFill>
  );
};

/** 纯深蓝黑的背景底 */
export const Backdrop: React.FC<{ from?: string; to?: string }> = ({
  from = COLORS.abyss,
  to = COLORS.void,
}) => (
  <AbsoluteFill
    style={{
      background: `radial-gradient(120% 90% at 50% 42%, ${from} 0%, ${to} 76%)`,
    }}
  />
);

/** 柔光点：用渐变模拟发光，避免昂贵的 blur filter */
export const GlowDot: React.FC<{
  size: number;
  color?: string;
  opacity?: number;
  style?: React.CSSProperties;
}> = ({ size, color = COLORS.goldBright, opacity = 1, style }) => (
  <div
    style={{
      position: "absolute",
      width: size,
      height: size,
      borderRadius: "50%",
      background: `radial-gradient(circle, ${color} 0%, ${color}55 26%, ${color}22 46%, rgba(0,0,0,0) 70%)`,
      opacity,
      ...style,
    }}
  />
);

/** 光束（侧上方射入） */
export const LightShaft: React.FC<{
  angle?: number;
  width?: number;
  opacity?: number;
  color?: string;
}> = ({ angle = -28, width = 320, opacity = 0.5, color = COLORS.gold }) => (
  <div
    style={{
      position: "absolute",
      left: "50%",
      top: "-30%",
      width,
      height: "160%",
      transform: `translateX(-50%) rotate(${angle}deg)`,
      background: `linear-gradient(to bottom, ${color}00 0%, ${color}44 18%, ${color}22 52%, ${color}00 92%)`,
      opacity,
    }}
  />
);
