import React from "react";
import {
  COLORS,
  FONT,
  LAYOUT,
  S,
  TYPE,
  clamp01,
  easeOutCubic,
  fadeIn,
  fitFontSize,
  pulse,
  reveal,
  win,
} from "./theme";
import { usePageT } from "./Caption";

/* ================= 图标库（Lucide 风格描边） ================= */

export type GlyphName =
  | "eye"
  | "chat"
  | "users"
  | "fileText"
  | "play"
  | "music"
  | "scan"
  | "search"
  | "monitor"
  | "shield"
  | "lock"
  | "trash"
  | "wallet"
  | "bookOpen"
  | "check"
  | "sparkles"
  | "arrow"
  | "calendar"
  | "globe";

const PATHS: Record<GlyphName, React.ReactNode> = {
  eye: (
    <>
      <path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7-10-7-10-7Z" />
      <circle cx="12" cy="12" r="3" />
    </>
  ),
  chat: <path d="M7.9 20A9 9 0 1 0 4 16.1L2 22Z" />,
  users: (
    <>
      <path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2" />
      <circle cx="9" cy="7" r="4" />
      <path d="M22 21v-2a4 4 0 0 0-3-3.87" />
      <path d="M16 3.13a4 4 0 0 1 0 7.75" />
    </>
  ),
  fileText: (
    <>
      <path d="M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7Z" />
      <path d="M14 2v5h5" />
      <path d="M16 13H8" />
      <path d="M16 17H8" />
      <path d="M10 9H8" />
    </>
  ),
  play: <polygon points="6 3 20 12 6 21 6 3" />,
  music: (
    <>
      <path d="M9 18V5l12-2v13" />
      <circle cx="6" cy="18" r="3" />
      <circle cx="18" cy="16" r="3" />
    </>
  ),
  scan: (
    <>
      <path d="M3 7V5a2 2 0 0 1 2-2h2" />
      <path d="M17 3h2a2 2 0 0 1 2 2v2" />
      <path d="M21 17v2a2 2 0 0 1-2 2h-2" />
      <path d="M7 21H5a2 2 0 0 1-2-2v-2" />
      <path d="M7 12h10" />
    </>
  ),
  search: (
    <>
      <circle cx="11" cy="11" r="8" />
      <path d="m21 21-4.3-4.3" />
    </>
  ),
  monitor: (
    <>
      <rect width="20" height="14" x="2" y="3" rx="2" />
      <path d="M8 21h8" />
      <path d="M12 17v4" />
    </>
  ),
  shield: (
    <>
      <path d="M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 0 1-.67-.01C7.5 20.5 4 18 4 13V6a1 1 0 0 1 1-1c2 0 4.5-1.2 6.24-2.72a1 1 0 0 1 1.52 0C14.51 3.81 17 5 19 5a1 1 0 0 1 1 1Z" />
      <path d="m9 12 2 2 4-4" />
    </>
  ),
  lock: (
    <>
      <rect width="18" height="11" x="3" y="11" rx="2" />
      <path d="M7 11V7a5 5 0 0 1 10 0v4" />
    </>
  ),
  trash: (
    <>
      <path d="M3 6h18" />
      <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6" />
      <path d="M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
    </>
  ),
  wallet: (
    <>
      <path d="M21 12V7H5a2 2 0 0 1 0-4h14v4" />
      <path d="M3 5v14a2 2 0 0 0 2 2h16v-5" />
      <path d="M18 12a2 2 0 0 0 0 4h4v-4Z" />
    </>
  ),
  bookOpen: (
    <>
      <path d="M12 7v14" />
      <path d="M3 18a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1h5a4 4 0 0 1 4 4 4 4 0 0 1 4-4h5a1 1 0 0 1 1 1v13a1 1 0 0 1-1 1h-6a3 3 0 0 0-3 3 3 3 0 0 0-3-3z" />
    </>
  ),
  check: (
    <>
      <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" />
      <path d="m9 11 3 3L22 4" />
    </>
  ),
  sparkles: (
    <path d="m12 3-1.9 5.8a2 2 0 0 1-1.3 1.3L3 12l5.8 1.9a2 2 0 0 1 1.3 1.3L12 21l1.9-5.8a2 2 0 0 1 1.3-1.3L21 12l-5.8-1.9a2 2 0 0 1-1.3-1.3Z" />
  ),
  arrow: (
    <>
      <path d="M5 12h14" />
      <path d="m12 5 7 7-7 7" />
    </>
  ),
  calendar: (
    <>
      <path d="M8 2v4" />
      <path d="M16 2v4" />
      <rect width="18" height="18" x="3" y="4" rx="2" />
      <path d="M3 10h18" />
    </>
  ),
  globe: (
    <>
      <circle cx="12" cy="12" r="10" />
      <path d="M12 2a14.5 14.5 0 0 0 0 20 14.5 14.5 0 0 0 0-20" />
      <path d="M2 12h20" />
    </>
  ),
};

export const Glyph: React.FC<{
  name: GlyphName;
  size?: number;
  color?: string;
  strokeWidth?: number;
}> = ({ name, size = 40, color = COLORS.gold, strokeWidth = 1.8 }) => (
  <svg
    width={size}
    height={size}
    viewBox="0 0 24 24"
    fill="none"
    stroke={color}
    strokeWidth={strokeWidth}
    strokeLinecap="round"
    strokeLinejoin="round"
    style={{ flexShrink: 0 }}
  >
    {PATHS[name]}
  </svg>
);

/* ================= 通用页面元素 ================= */

/** 右上角品牌条（与 PPT 每页一致） */
export const BrandChip: React.FC<{ t: number; at?: number }> = ({
  t,
  at = 0,
}) => {
  const a = fadeIn(t, at, 0.5);
  return (
    <div
      style={{
        position: "absolute",
        top: LAYOUT.brandY + 72, // 避开电影感黑边
        right: LAYOUT.marginX,
        opacity: a,
        display: "flex",
        alignItems: "center",
        gap: 10,
      }}
    >
      <div
        style={{
          width: 8,
          height: 8,
          borderRadius: 4,
          background: S.primary,
          boxShadow: `0 0 10px ${S.primary}`,
        }}
      />
      <span
        style={{
          fontFamily: FONT.family,
          fontSize: TYPE.label,
          color: S.primary,
          letterSpacing: 2,
          fontWeight: 600,
        }}
      >
        视频号：AIST2030
      </span>
    </div>
  );
};

/** 章节标签 + 页标题（按视觉宽度反推字号，杜绝溢出/孤字行） */
export const SectionHeader: React.FC<{
  t: number;
  label: string;
  title: string;
  at?: number;
}> = ({ t, label, title, at = 0 }) => {
  const la = fadeIn(t, at, 0.4);
  const ta = reveal(t, at + 0.15, 0.5);
  // ★ 按视觉宽度反推字号（中文 1.0 / 英数 0.58），不再两档切换——
  // 长标题两档切换仍会溢出画布（PPT 任务踩过的坑）。
  const size = fitFontSize(title, 912, TYPE.title, 40, 0.02);
  return (
    <div style={{ position: "absolute", left: LAYOUT.marginX, top: LAYOUT.sectionY + 8, right: LAYOUT.marginX }}>
      <div style={{ display: "flex", alignItems: "center", gap: 12, opacity: la }}>
        <div style={{ width: 34, height: 4, background: S.primary, borderRadius: 2 }} />
        <span
          style={{
            fontFamily: FONT.family,
            fontSize: TYPE.label,
            color: S.labelColor,
            letterSpacing: 4,
            fontWeight: 600,
          }}
        >
          {label}
        </span>
      </div>
      <h1
        style={{
          margin: "14px 0 0 0",
          fontFamily: FONT.family,
          fontSize: size,
          fontWeight: 800,
          color: S.text,
          lineHeight: 1.25,
          letterSpacing: 1,
          whiteSpace: "nowrap",
          opacity: clamp01(ta),
          transform: `translateY(${(1 - clamp01(ta)) * 26}px)`,
          textShadow: "0 4px 24px rgba(0,0,0,0.6)",
        }}
      >
        {title}
      </h1>
    </div>
  );
};

/**
 * 骨架占位：元素尚未被语音触发时，以极暗的轮廓卡占位。
 * 作用 —— 1) 布局稳定，不会讲一条才长出一条；2) 暗示"后面还有"，提升节奏期待
 */
export const GhostCard: React.FC<{ h: number; radius?: number }> = ({
  h,
  radius = 20,
}) => (
  <div
    style={{
      height: h,
      borderRadius: radius,
      border: `1px dashed ${COLORS.goldDim}`,
      background: "rgba(11,20,36,0.35)",
      boxSizing: "border-box",
    }}
  />
);

/** 底部金色结论条 */
export const Banner: React.FC<{
  t: number;
  at: number;
  text: string;
  icon?: GlyphName;
}> = ({ t, at, text, icon = "sparkles" }) => {
  const a = reveal(t, at, 0.55);
  const glow = 0.5 + 0.5 * pulse(t, 2.4);
  return (
    <div
      style={{
        position: "absolute",
        left: LAYOUT.marginX,
        right: LAYOUT.marginX,
        top: LAYOUT.bannerY,
        height: LAYOUT.bannerH,
        borderRadius: 18,
        background: `linear-gradient(135deg, rgba(232,198,110,0.16) 0%, rgba(18,32,54,0.9) 60%)`,
        border: `1px solid rgba(232,198,110,${0.35 + 0.25 * glow})`,
        boxShadow: `0 0 ${18 + 14 * glow}px rgba(232,198,110,${0.12 + 0.08 * glow})`,
        display: "flex",
        alignItems: "center",
        gap: 16,
        padding: "0 28px",
        opacity: clamp01(a),
        transform: `translateY(${(1 - clamp01(a)) * 30}px) scale(${0.96 + 0.04 * clamp01(a)})`,
      }}
    >
      <Glyph name={icon} size={38} color={COLORS.gold} />
      <span
        style={{
          fontFamily: FONT.family,
          fontSize: 34,
          fontWeight: 700,
          color: COLORS.goldBright,
          letterSpacing: 1,
        }}
      >
        {text}
      </span>
    </div>
  );
};

/** 页码（左上角，避开底部字幕与结论条） */
export const PageNum: React.FC<{ t: number; n: number; total?: number }> = ({
  t,
  n,
  total = 6,
}) => {
  const a = fadeIn(t, 0.2, 0.5);
  return (
    <div
      style={{
        position: "absolute",
        left: LAYOUT.marginX,
        top: LAYOUT.brandY + 20, // 避开电影感黑边（48px）
        opacity: a * 0.9,
        fontFamily: FONT.family,
        fontSize: TYPE.micro,
        color: S.primary,
        letterSpacing: 2,
        fontWeight: 600,
      }}
    >
      {String(n).padStart(2, "0")} / {String(total).padStart(2, "0")}
    </div>
  );
};

/* ================= 数据卡片 ================= */

export const StatCard: React.FC<{
  t: number;
  at: number;
  /** 大数字（可空） */
  num?: string;
  unit?: string;
  title: string;
  desc: string;
  icon: GlyphName;
  /** 高亮激活期 [from, to] */
  activeFrom?: number;
  activeTo?: number;
  width?: number | string;
}> = ({
  t,
  at,
  num,
  unit,
  title,
  desc,
  icon,
  activeFrom = -1,
  activeTo = -1,
  width = "100%",
}) => {
  const a = reveal(t, at, 0.5);
  const active = t >= activeFrom && t < activeTo;
  const glow = active ? 0.5 + 0.5 * pulse(t, 1.6) : 0;
  return (
    <div
      style={{
        width,
        borderRadius: 20,
        background: active
          ? "linear-gradient(160deg, rgba(232,198,110,0.14) 0%, rgba(11,20,36,0.95) 55%)"
          : "linear-gradient(160deg, rgba(18,32,54,0.85) 0%, rgba(7,13,24,0.95) 100%)",
        border: `1px solid rgba(232,198,110,${0.28 + 0.5 * glow})`,
        boxShadow: active
          ? `0 0 ${24 + 18 * glow}px rgba(232,198,110,${0.2 + 0.15 * glow}), 0 10px 30px rgba(0,0,0,0.5)`
          : "0 8px 24px rgba(0,0,0,0.45)",
        padding: "26px 28px",
        opacity: clamp01(a),
        transform: `translateY(${(1 - clamp01(a)) * 34}px) scale(${0.94 + 0.06 * clamp01(a) + (active ? 0.015 : 0)})`,
        display: "flex",
        flexDirection: "column",
        gap: 10,
        boxSizing: "border-box",
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
        <div
          style={{
            width: 58,
            height: 58,
            borderRadius: 14,
            background: "rgba(232,198,110,0.12)",
            border: "1px solid rgba(232,198,110,0.3)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            flexShrink: 0,
          }}
        >
          <Glyph name={icon} size={32} color={active ? COLORS.goldBright : COLORS.gold} />
        </div>
        <div style={{ display: "flex", flexDirection: "column" }}>
          {num ? (
            <div style={{ display: "flex", alignItems: "baseline", gap: 6 }}>
              <span
                style={{
                  fontFamily: FONT.family,
                  fontSize: 52,
                  fontWeight: 800,
                  color: COLORS.goldBright,
                  lineHeight: 1,
                }}
              >
                {num}
              </span>
              {unit ? (
                <span
                  style={{
                    fontFamily: FONT.family,
                    fontSize: 26,
                    color: COLORS.gold,
                    fontWeight: 600,
                  }}
                >
                  {unit}
                </span>
              ) : null}
            </div>
          ) : null}
          <span
            style={{
              fontFamily: FONT.family,
              fontSize: num ? 30 : TYPE.cardTitle,
              fontWeight: 700,
              color: COLORS.ink,
              letterSpacing: 0.5,
            }}
          >
            {title}
          </span>
        </div>
      </div>
      <span
        style={{
          fontFamily: FONT.family,
          fontSize: TYPE.cardDesc,
          color: COLORS.inkSoft,
          lineHeight: 1.45,
        }}
      >
        {desc}
      </span>
    </div>
  );
};

/* ================= 列表行（P4 用） ================= */

export const ListRow: React.FC<{
  t: number;
  at: number;
  index: number;
  title: string;
  desc: string;
  icon: GlyphName;
  activeFrom?: number;
  activeTo?: number;
}> = ({ t, at, index, title, desc, icon, activeFrom = -1, activeTo = -1 }) => {
  const a = reveal(t, at, 0.5);
  const active = t >= activeFrom && t < activeTo;
  const glow = active ? 0.5 + 0.5 * pulse(t, 1.6) : 0;
  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        gap: 20,
        borderRadius: 18,
        background: active
          ? "linear-gradient(100deg, rgba(232,198,110,0.13) 0%, rgba(11,20,36,0.92) 70%)"
          : "rgba(11,20,36,0.78)",
        border: `1px solid rgba(232,198,110,${0.22 + 0.5 * glow})`,
        boxShadow: active
          ? `0 0 ${20 + 14 * glow}px rgba(232,198,110,${0.16 + 0.12 * glow})`
          : "0 6px 18px rgba(0,0,0,0.4)",
        padding: "20px 24px",
        opacity: clamp01(a),
        transform: `translateX(${(1 - clamp01(a)) * 40}px)`,
        boxSizing: "border-box",
      }}
    >
      <div
        style={{
          width: 52,
          height: 52,
          borderRadius: 26,
          background: active ? COLORS.gold : "rgba(232,198,110,0.14)",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          flexShrink: 0,
          fontFamily: FONT.family,
          fontSize: 28,
          fontWeight: 800,
          color: active ? COLORS.void : COLORS.gold,
        }}
      >
        {index}
      </div>
      <Glyph name={icon} size={36} color={active ? COLORS.goldBright : COLORS.gold} />
      <div style={{ display: "flex", flexDirection: "column", gap: 4, flex: 1 }}>
        <span
          style={{
            fontFamily: FONT.family,
            fontSize: 34,
            fontWeight: 700,
            color: COLORS.ink,
          }}
        >
          {title}
        </span>
        <span
          style={{
            fontFamily: FONT.family,
            fontSize: TYPE.cardDesc,
            color: COLORS.inkSoft,
            lineHeight: 1.4,
          }}
        >
          {desc}
        </span>
      </div>
    </div>
  );
};

/* ================= 小芯片（P3 公式行用） ================= */

export const FormulaChip: React.FC<{
  t: number;
  at: number;
  num: string;
  label: string;
  icon?: GlyphName;
  activeFrom?: number;
  activeTo?: number;
}> = ({ t, at, num, label, icon, activeFrom = -1, activeTo = -1 }) => {
  const a = reveal(t, at, 0.45);
  const active = t >= activeFrom && t < activeTo;
  const glow = active ? 0.5 + 0.5 * pulse(t, 1.5) : 0;
  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        gap: 8,
        padding: "16px 10px",
        borderRadius: 16,
        background: active
          ? "linear-gradient(170deg, rgba(232,198,110,0.18) 0%, rgba(11,20,36,0.9) 80%)"
          : "rgba(11,20,36,0.8)",
        border: `1px solid rgba(232,198,110,${0.25 + 0.5 * glow})`,
        boxShadow: active
          ? `0 0 ${16 + 12 * glow}px rgba(232,198,110,${0.18 + 0.12 * glow})`
          : "0 5px 16px rgba(0,0,0,0.4)",
        opacity: clamp01(a),
        transform: `translateY(${(1 - clamp01(a)) * 24}px) scale(${0.9 + 0.1 * clamp01(a)})`,
        flex: 1,
        boxSizing: "border-box",
      }}
    >
      {icon ? <Glyph name={icon} size={34} color={active ? COLORS.goldBright : COLORS.gold} /> : null}
      <div style={{ display: "flex", alignItems: "baseline", gap: 4 }}>
        <span
          style={{
            fontFamily: FONT.family,
            fontSize: 46,
            fontWeight: 800,
            color: COLORS.goldBright,
            lineHeight: 1,
          }}
        >
          {num}
        </span>
        <span
          style={{
            fontFamily: FONT.family,
            fontSize: 22,
            color: COLORS.gold,
            fontWeight: 600,
          }}
        >
          个
        </span>
      </div>
      <span
        style={{
          fontFamily: FONT.family,
          fontSize: 24,
          color: COLORS.inkSoft,
          fontWeight: 600,
          whiteSpace: "nowrap",
        }}
      >
        {label}
      </span>
    </div>
  );
};

/** 公式行中的 "+" 连接符 */
export const PlusSign: React.FC<{ t: number; at: number }> = ({ t, at }) => {
  const a = fadeIn(t, at, 0.3);
  return (
    <div
      style={{
        alignSelf: "center",
        fontFamily: FONT.family,
        fontSize: 34,
        color: COLORS.goldDim,
        fontWeight: 700,
        opacity: a,
        paddingBottom: 26,
      }}
    >
      +
    </div>
  );
};

/** 场景内容包裹层：负责页切换时的淡入淡出 */
export const SceneFade: React.FC<{
  t: number;
  pageDur: number;
  children: React.ReactNode;
}> = ({ t, pageDur, children }) => {
  const inA = easeOutCubic(win(t, 0, 0.45));
  const outA = easeOutCubic(win(pageDur - t, 0, 0.45));
  return (
    <div style={{ position: "absolute", inset: 0, opacity: inA * outA }}>
      {children}
    </div>
  );
};

export { usePageT };
