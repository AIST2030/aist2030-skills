import React from "react";
import {
  AbsoluteFill,
  Easing,
  interpolate,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import { FONT, S } from "./theme";

/**
 * 调度链路动画（封面页下方信息区）：画面自身承载信息，不依赖旁白文案。
 * 一句话 → 智能调度 → 按任务分流到不同模型 → 故障自动接管。
 * 视觉：玻璃面板 + 扫描光线 + 渠道 chip 依次点亮（still-850 数据感风格）。
 */
const ROUTES = [
  { k: "中文对话", v: "国产模型" },
  { k: "写代码", v: "推理强的" },
  { k: "长文档", v: "长上下文" },
  { k: "故障", v: "自动接管" },
];

export const SchedulerFlow: React.FC<{ at: number }> = ({ at }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const t = frame / fps;
  if (t < at) return null;

  const life = t - at;
  const eIn = Easing.out(Easing.cubic)(Math.min(1, life / 0.6));
  // 扫描光：2.4s 一循环，从左到右
  const sweep = ((life - 0.7) % 2.4) / 2.4;
  const sweepX = sweep < 0 ? -100 : sweep * 100;

  return (
    <AbsoluteFill style={{ pointerEvents: "none" }}>
      <div
        style={{
          position: "absolute",
          left: 84,
          right: 84,
          top: 780,
          opacity: eIn,
          transform: `translateY(${(1 - eIn) * 42}px)`,
        }}
      >
        <div
          style={{
            position: "relative",
            borderRadius: 26,
            background: "rgba(255,255,255,0.05)",
            border: "1px solid rgba(255,255,255,0.13)",
            boxShadow: "0 24px 70px rgba(0,0,0,0.5)",
            padding: "28px 32px 30px",
            overflow: "hidden",
            fontFamily: FONT.family,
          }}
        >
          {/* 扫描光线 */}
          <div
            style={{
              position: "absolute",
              top: 0,
              bottom: 0,
              left: `${sweepX}%`,
              width: 130,
              background: `linear-gradient(90deg, transparent, ${S.primary}2e, transparent)`,
              opacity: sweepX >= 0 && sweepX <= 100 ? 1 : 0,
            }}
          />

          {/* 标题行 */}
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: 14,
              marginBottom: 22,
            }}
          >
            <div
              style={{
                width: 10,
                height: 28,
                borderRadius: 5,
                background: `linear-gradient(180deg, ${S.primary}, ${S.primaryBright})`,
                boxShadow: `0 0 14px ${S.primary}aa`,
              }}
            />
            <div
              style={{
                fontSize: 30,
                fontWeight: 800,
                color: "#D9E8FF",
                letterSpacing: 2,
              }}
            >
              一句话，自动分配
            </div>
            <div
              style={{
                marginLeft: "auto",
                fontSize: 22,
                color: "#7FA8E8",
                fontWeight: 600,
              }}
            >
              每句话都在比
            </div>
          </div>

          {/* 链路：问题 → 调度 → 分流 */}
          <div style={{ display: "flex", alignItems: "center", gap: 18 }}>
            {/* 问题气泡 */}
            <div
              style={{
                flexShrink: 0,
                padding: "14px 20px",
                borderRadius: 16,
                background: "rgba(79,140,255,0.14)",
                border: "1px solid rgba(79,140,255,0.35)",
                color: "#EAF3FF",
                fontSize: 24,
                fontWeight: 700,
              }}
            >
              随口一句话
            </div>

            {/* 流动箭头 */}
            <div style={{ flex: 1, position: "relative", height: 4, borderRadius: 2, background: "rgba(127,168,232,0.25)" }}>
              <div
                style={{
                  position: "absolute",
                  top: -5,
                  left: `${Math.min(92, Math.max(0, ((life - 0.5) % 1.6) / 1.6 * 100))}%`,
                  width: 14,
                  height: 14,
                  borderRadius: "50%",
                  background: S.primaryBright,
                  boxShadow: `0 0 16px ${S.primaryBright}`,
                }}
              />
            </div>

            {/* 调度核心 */}
            <div
              style={{
                flexShrink: 0,
                padding: "14px 22px",
                borderRadius: 999,
                background: `linear-gradient(135deg, ${S.primary}, ${S.primaryBright})`,
                color: "#04101F",
                fontSize: 24,
                fontWeight: 900,
                boxShadow: `0 8px 30px ${S.primary}66`,
              }}
            >
              智能调度
            </div>
          </div>

          {/* 分流 chips：依次点亮 */}
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "1fr 1fr",
              gap: 12,
              marginTop: 20,
            }}
          >
            {ROUTES.map((r, i) => {
              const on = interpolate(
                life,
                [0.8 + i * 0.28, 1.1 + i * 0.28],
                [0, 1],
                { extrapolateLeft: "clamp", extrapolateRight: "clamp" },
              );
              return (
                <div
                  key={r.k}
                  style={{
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "space-between",
                    padding: "13px 18px",
                    borderRadius: 14,
                    background: `rgba(79,140,255,${0.05 + on * 0.1})`,
                    border: `1px solid rgba(127,168,232,${0.14 + on * 0.4})`,
                    opacity: 0.35 + on * 0.65,
                    transform: `translateX(${(1 - on) * -14}px)`,
                  }}
                >
                  <span style={{ fontSize: 23, fontWeight: 700, color: "#C9DCF8" }}>
                    {r.k}
                  </span>
                  <span style={{ fontSize: 23, fontWeight: 800, color: S.primaryBright }}>
                    → {r.v}
                  </span>
                </div>
              );
            })}
          </div>
        </div>
      </div>
    </AbsoluteFill>
  );
};
