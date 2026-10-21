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
 * 放大镜特写：展示真实截图中「输入框下方 AIST2030免费模型」那一行。
 *
 * ★ 全部基于真实像素，不做任何合成假图：
 *   - 底图：public/zoom/shot_base.png（用户实拍界面 1440×900）
 *   - 镜内：同一张图按 2.5× 放大，对准文字行中心（原图坐标 1196,881）
 *   文字行坐标由投影分析实测得出（x 1076–1311, y 868–898），非目测估计。
 *
 * 几何：
 *   底图宽 800 → 缩放比 s = 800/1440
 *   镜内缩放 zs = s * MAG
 *   镜内 <Img> 偏移 = R - P * zs（P 为原图坐标），保证圆心的原图点落在圆心
 */
const SRC_W = 1440;
const SRC_H = 900;
const BASE_W = 800;
const BASE_X = (1080 - BASE_W) / 2; // 140
const BASE_Y = 560;
/** 文字行中心（原图像素，投影实测） */
const TX = 1196;
const TY = 881;
/** 文字行包围盒（原图像素） */
const BW = 288;
const BH = 46;
/** 放大倍数与圆半径：使「AIST2030免费模型」整行（原图 288px 宽）完整入镜 */
const MAG = 2.2;
const R = 180;

export const ZoomLens: React.FC<{ at: number; label: string }> = ({
  at,
  label,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const t = frame / fps;
  if (t < at - 0.05) return null;

  const p = Math.min(1, Math.max(0, (t - at) / 0.5));
  const ease = Easing.out(Easing.cubic)(p);

  const s = BASE_W / SRC_W; // 底图缩放比
  const zs = s * MAG; // 镜内缩放比
  const cx = BASE_X + TX * s; // 文字行中心（画布坐标）
  const cy = BASE_Y + TY * s;
  const r = R * (0.55 + 0.45 * ease);
  const op = interpolate(p, [0, 1], [0, 1]);

  const base = staticFile("zoom/shot_base.png");

  return (
    <AbsoluteFill style={{ pointerEvents: "none" }}>
      {/* ---------- 底图：真实界面截图 ---------- */}
      <Img
        src={base}
        style={{
          position: "absolute",
          left: BASE_X,
          top: BASE_Y,
          width: BASE_W,
          opacity: op,
          borderRadius: 16,
          border: `1px solid ${S.primary}55`,
          boxShadow: `0 18px 60px rgba(0,0,0,0.6), 0 0 0 1px rgba(255,255,255,0.06)`,
        }}
      />

      {/* ---------- 目标区虚线框（放大前的位置） ---------- */}
      <div
        style={{
          position: "absolute",
          left: cx - (BW * s) / 2,
          top: cy - (BH * s) / 2,
          width: BW * s,
          height: BH * s,
          border: `2px dashed ${S.primaryBright}`,
          borderRadius: 6,
          opacity: op * 0.9,
          boxShadow: `0 0 18px ${S.primary}88`,
        }}
      />

      {/* ---------- 放大镜圆 ---------- */}
      <div
        style={{
          position: "absolute",
          left: cx - r,
          top: cy - r,
          width: r * 2,
          height: r * 2,
          borderRadius: "50%",
          overflow: "hidden",
          opacity: op,
          border: `4px solid ${S.primary}`,
          boxShadow: `0 0 0 8px ${S.primary}22, 0 20px 60px rgba(0,0,0,0.7), inset 0 0 30px rgba(0,0,0,0.35)`,
          transform: `scale(${0.86 + 0.14 * ease})`,
        }}
      >
        {/* 镜内：真实截图按 MAG 倍放大，对准文字行 */}
        <Img
          src={base}
          style={{
            position: "absolute",
            left: r - TX * zs,
            top: r - TY * zs,
            width: SRC_W * zs,
            height: SRC_H * zs,
          }}
        />
        {/* 镜片高光 */}
        <div
          style={{
            position: "absolute",
            inset: 0,
            borderRadius: "50%",
            background:
              "radial-gradient(circle at 32% 26%, rgba(255,255,255,0.20), rgba(255,255,255,0) 46%)",
          }}
        />
      </div>

      {/* ---------- 标注：引线 + 标签 ---------- */}
      <div
        style={{
          position: "absolute",
          left: cx - 250,
          top: cy - r - 96,
          width: 500,
          textAlign: "center",
          opacity: op,
        }}
      >
        <div
          style={{
            display: "inline-block",
            padding: "10px 20px",
            borderRadius: 999,
            background: "rgba(4,12,26,0.86)",
            border: `1px solid ${S.primary}88`,
            fontFamily: FONT.family,
            fontSize: 30,
            fontWeight: 700,
            color: "#EAF3FF",
            letterSpacing: 0.5,
            boxShadow: `0 8px 30px rgba(0,0,0,0.5)`,
          }}
        >
          {label}
        </div>
        {/* 引线：从标签下沿连到放大镜 */}
        <div
          style={{
            width: 2,
            height: 62,
            margin: "6px auto 0",
            background: `linear-gradient(180deg, ${S.primary}, ${S.primaryBright})`,
            boxShadow: `0 0 12px ${S.primary}aa`,
          }}
        />
      </div>
    </AbsoluteFill>
  );
};
