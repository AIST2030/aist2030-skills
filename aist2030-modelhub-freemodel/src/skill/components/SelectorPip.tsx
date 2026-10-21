import React from "react";
import {
  AbsoluteFill,
  Easing,
  Img,
  interpolate,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import { FONT, S } from "./theme";

/**
 * 一次性画中画：WorkBuddy 模型下拉截图（真实截图，非生成图）。
 * 展示「在下拉里选中 AIST2030免费模型」这个动作，只出现一次，到时淡出。
 *
 * 高亮框坐标来自投影实测：截图 554×554，选中行 x118-440 / y358-390。
 */
const IMG_SIZE = 554;
const SHOW_W = 470; // 展示宽度
const SCALE = SHOW_W / IMG_SIZE;
const HL = { x: 118, y: 358, w: 322, h: 32 };
const LEFT = (1080 - SHOW_W) / 2;
const TOP = 560;

export const SelectorPip: React.FC<{
  at: number;
  dur: number;
  label: string;
}> = ({ at, dur, label }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const t = frame / fps;
  if (t < at || t > at + dur) return null;

  const life = t - at;
  const pin = Math.min(1, life / 0.55);
  const eIn = Easing.out(Easing.cubic)(pin);
  // 尾部淡出
  const out = interpolate(life, [dur - 0.45, dur], [1, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const op = Math.min(eIn, out);

  // 高亮框：入场 0.5s 后出现，带脉冲
  const hlIn = interpolate(life, [0.5, 1.0], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const pulse = 0.5 + 0.5 * Math.sin(life * Math.PI * 2.2);

  const bx = LEFT + HL.x * SCALE;
  const by = TOP + HL.y * SCALE;
  const bw = HL.w * SCALE;
  const bh = HL.h * SCALE;

  return (
    <AbsoluteFill style={{ pointerEvents: "none" }}>
      {/* 背景压暗，突出卡片 */}
      <div
        style={{
          position: "absolute",
          inset: 0,
          background: "rgba(2,6,14,0.45)",
          opacity: op * 0.9,
        }}
      />
      {/* 截图卡片 */}
      <div
        style={{
          position: "absolute",
          left: LEFT,
          top: TOP + (1 - eIn) * 46,
          width: SHOW_W,
          opacity: op,
          borderRadius: 26,
          overflow: "hidden",
          border: `1px solid rgba(255,255,255,0.16)`,
          boxShadow: `0 30px 90px rgba(0,0,0,0.65), 0 0 0 1px ${S.primary}33`,
        }}
      >
        <Img
          src={staticFile("pip/selector.png")}
          style={{ width: "100%", display: "block" }}
        />
      </div>

      {/* 选中行高亮框（脉冲） */}
      <div
        style={{
          position: "absolute",
          left: bx - 8,
          top: by - 6 + (1 - eIn) * 46,
          width: bw + 16,
          height: bh + 12,
          borderRadius: 14,
          border: `3px solid ${S.primaryBright}`,
          boxShadow: `0 0 ${18 + pulse * 22}px ${S.primary}${Math.round(
            70 + pulse * 90,
          )}`,
          opacity: hlIn * op,
        }}
      />

      {/* 右侧勾选标记光点 */}
      <div
        style={{
          position: "absolute",
          left: bx + bw + 18,
          top: by + 2 + (1 - eIn) * 46,
          width: 34,
          height: 34,
          borderRadius: "50%",
          background: S.primary,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          fontSize: 22,
          fontWeight: 900,
          color: "#04101F",
          boxShadow: `0 0 ${14 + pulse * 18}px ${S.primary}cc`,
          opacity: hlIn * op,
          fontFamily: FONT.family,
        }}
      >
        ✓
      </div>

      {/* 底部标签 */}
      <div
        style={{
          position: "absolute",
          left: 0,
          right: 0,
          top: TOP + SHOW_W + 26,
          textAlign: "center",
          opacity: hlIn * op,
        }}
      >
        <span
          style={{
            display: "inline-block",
            padding: "12px 26px",
            borderRadius: 999,
            background: "rgba(4,12,26,0.88)",
            border: `1px solid ${S.primary}88`,
            fontFamily: FONT.family,
            fontSize: 32,
            fontWeight: 700,
            color: "#EAF3FF",
            letterSpacing: 1,
            boxShadow: "0 10px 34px rgba(0,0,0,0.5)",
          }}
        >
          {label}
        </span>
      </div>
    </AbsoluteFill>
  );
};
