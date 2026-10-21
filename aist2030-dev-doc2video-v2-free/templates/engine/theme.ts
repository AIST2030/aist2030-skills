// 微信小微AI盘点 · 视觉主题
// 深蓝黑底 + 暖金主色 + 冷青副色 + 电影感微光（AIST2030 品牌视觉规范）

export const VIDEO = {
  width: 1080,
  height: 1440, // 3:4 竖版，与 PPT(720x960) 同比例
  fps: 30,
};

export const COLORS = {
  // 底色层次
  void: "#04070D",
  abyss: "#070D18",
  deepNight: "#0B1424",
  nightBlue: "#122036",
  slateBlue: "#1B2E4A",

  // 暖金主色
  gold: "#E8C66E",
  goldBright: "#F7E3A8",
  goldDeep: "#C79F45",
  goldDim: "rgba(232,198,110,0.45)",

  // 冷青副色
  cyan: "#6ECFD8",
  cyanDim: "rgba(110,207,216,0.5)",

  // 微信绿（绿色眼睛图标专用，与官方一致）
  wechatGreen: "#07C160",
  wechatGreenDim: "rgba(7,193,96,0.45)",

  // 文本
  ink: "#F4EADA",
  inkSoft: "rgba(244,234,218,0.72)",
  inkFaint: "rgba(244,234,218,0.4)",
  bone: "#EFE7DA",

  // 冷灰
  gray: "#5A6472",
  grayDim: "rgba(90,100,114,0.55)",
};

export const FONT = {
  family:
    '"Microsoft YaHei","微软雅黑","PingFang SC","Noto Sans CJK SC",system-ui,sans-serif',
};

/** 布局基准（1080x1440 画布） */
export const LAYOUT = {
  marginX: 84,
  brandY: 46,
  sectionY: 172,
  titleY: 232,
  contentTop: 420,
  bannerY: 1122,
  bannerH: 96,
  captionTop: 1258,
};

/** 排版基准 */
export const TYPE = {
  hero: 128, // 封面主标题
  title: 74, // 页标题
  lead: 52, // 封面副标题
  cardTitle: 40, // 卡片标题
  cardDesc: 28, // 卡片描述
  caption: 40, // 字幕
  label: 30, // 章节标签/注释
  micro: 26, // 页码等
};

/* ---------------- 动画工具 ---------------- */

export const clamp01 = (x: number) => Math.max(0, Math.min(1, x));

/** 线性窗口进度：t 在 [a,b] 内从 0 到 1 */
export const win = (t: number, a: number, b: number) =>
  clamp01((t - a) / Math.max(0.0001, b - a));

export const easeOutCubic = (t: number) => 1 - Math.pow(1 - clamp01(t), 3);
export const easeInCubic = (t: number) => Math.pow(clamp01(t), 3);
export const easeInOut = (t: number) => {
  const x = clamp01(t);
  return x < 0.5 ? 2 * x * x : 1 - Math.pow(-2 * x + 2, 2) / 2;
};
export const easeOutBack = (t: number) => {
  const c1 = 1.70158;
  const c3 = c1 + 1;
  const x = clamp01(t);
  return 1 + c3 * Math.pow(x - 1, 3) + c1 * Math.pow(x - 1, 2);
};
export const easeOutElastic = (t: number) => {
  const x = clamp01(t);
  if (x === 0 || x === 1) return x;
  return (
    Math.pow(2, -10 * x) * Math.sin((x * 10 - 0.75) * ((2 * Math.PI) / 3)) + 1
  );
};

/** 元素在 at 时刻入场，dur 秒内完成（带回弹） */
export const reveal = (t: number, at: number, dur = 0.45) =>
  easeOutBack(win(t, at, at + dur));

/** 元素平滑淡入（无回弹） */
export const fadeIn = (t: number, at: number, dur = 0.4) =>
  easeOutCubic(win(t, at, at + dur));

/** 呼吸脉冲（用于图标高亮） */
export const pulse = (t: number, period = 2.0) =>
  0.5 + 0.5 * Math.sin((t / period) * Math.PI * 2);

/** 确定性伪随机，避免每帧抖动 */
export const rand = (n: number) => {
  const x = Math.sin(n * 127.1 + 311.7) * 43758.5453;
  return x - Math.floor(x);
};

/** 场景统一的出场/退场不透明度曲线 */
export const sceneAlpha = (p: number, fadeIn = 0.12, fadeOut = 0.12) => {
  const a = Math.min(1, p / fadeIn);
  const b = Math.min(1, (1 - p) / fadeOut);
  return Math.max(0, Math.min(a, b));
};

/**
 * 动效样式自适应选择（2026-10-18 用户需求：文字/形状动效再丰富）。
 * 按索引确定性挑选变体，避免每帧抖动；同一组内相邻元素必不同款，
 * 让版式有节奏又不杂乱。variants 至少 2 个。
 */
export const pickVariant = <T,>(variants: T[], i: number, groupSeed = 0): T => {
  if (variants.length <= 0) return undefined as unknown as T;
  if (variants.length === 1) return variants[0];
  const h = Math.abs(Math.sin((i + 1) * 12.9898 + groupSeed * 78.233));
  const v = variants[Math.floor(h * variants.length) % variants.length];
  // 相邻重复时顺延一位，保证相邻元素不同款
  const prev = variants[Math.floor(Math.abs(Math.sin(i * 12.9898 + groupSeed * 78.233)) * variants.length) % variants.length];
  return v === prev && i > 0
    ? variants[(variants.indexOf(v) + 1) % variants.length]
    : v;
};

/* ================= 视觉风格预设（2026-10-17 用户需求：备选主流风格） ================= */

export type StyleId = "cinematic" | "tech" | "warm" | "vivid";

export interface StylePreset {
  id: StyleId;
  name: string;
  /** 背景基色（兜底 + 氛围） */
  bg: string;
  /** 主色（高亮文字/数字/图形） */
  primary: string;
  primaryBright: string;
  /** 副色（辅助图形/图标） */
  accent: string;
  /** 正文文本 */
  text: string;
  textSoft: string;
  /** 素材叠加染色（叠在实拍上的 rgba，压暗用） */
  tint: string;
  /** 电影感黑边高度（px，0 = 无） */
  letterbox: number;
  /** 章节标签色 */
  labelColor: string;
  /** 图形卡片底 / 描边 */
  cardBg: string;
  cardBorder: string;
  /** 氛围参数 */
  glowRgb: string; // 主光晕颜色 RGB 分量（用于动态透明度）
  glow: string;
  grain: number;
  vignette: number;
}

export const STYLES: Record<StyleId, StylePreset> = {
  /** 电影感：深黑底 + 暖金高光 + 上下黑边 + 暗角，短片/预告片质感 */
  cinematic: {
    id: "cinematic",
    name: "电影感",
    bg: "#05080F",
    primary: "#E8C66E",
    primaryBright: "#F7E3A8",
    accent: "#8FA8C8",
    text: "#F4EADA",
    textSoft: "rgba(244,234,218,0.72)",
    tint: "rgba(6,9,16,0.42)",
    letterbox: 56,
    labelColor: "#C9A85C",
    cardBg: "rgba(8,12,20,0.84)",
    cardBorder: "rgba(232,198,110,0.35)",
    glowRgb: "232,198,110",
    glow: "rgba(232,198,110,0.10)",
    grain: 0.07,
    vignette: 0.38,
  },
  /** 科技感：深蓝底 + 冷青主色 + 电光蓝辅助，数据/产品向 */
  tech: {
    id: "tech",
    name: "科技感",
    bg: "#030B14",
    primary: "#6ECFD8",
    primaryBright: "#A8F0F7",
    accent: "#4D9FFF",
    text: "#E8F4F8",
    textSoft: "rgba(232,244,248,0.72)",
    tint: "rgba(3,14,26,0.38)",
    letterbox: 0,
    labelColor: "#6ECFD8",
    cardBg: "rgba(6,20,34,0.86)",
    cardBorder: "rgba(110,207,216,0.38)",
    glowRgb: "110,207,216",
    glow: "rgba(110,207,216,0.12)",
    grain: 0.04,
    vignette: 0.32,
  },
  /** 暖金（AIST2030 品牌默认）：深蓝黑 + 暖金 + 冷青 */
  warm: {
    id: "warm",
    name: "暖金（品牌）",
    bg: "#04070D",
    primary: "#E8C66E",
    primaryBright: "#F7E3A8",
    accent: "#6ECFD8",
    text: "#F4EADA",
    textSoft: "rgba(244,234,218,0.72)",
    tint: "rgba(7,13,24,0.38)",
    letterbox: 0,
    labelColor: "#E8C66E",
    cardBg: "rgba(11,20,36,0.86)",
    cardBorder: "rgba(232,198,110,0.4)",
    glowRgb: "232,198,110",
    glow: "rgba(232,198,110,0.12)",
    grain: 0.05,
    vignette: 0.34,
  },
  /** 鲜活民生风（2026-10-18 新增）：暖炭底 + 活力橙 + 微信绿。
   *  内容自适应逻辑：本地餐饮/门店/烟火气选题 → 橙金（食欲感）+ 鲜绿（微信生态），
   *  底色仍压深保证字幕可读；避开深底爆紫的冷粉/紫水晶系（血泪教训）。 */
  vivid: {
    id: "vivid",
    name: "鲜活（民生消费）",
    bg: "#150B06",
    primary: "#FFB03A",
    primaryBright: "#FFD37E",
    accent: "#2FD97A",
    text: "#FFF3E4",
    textSoft: "rgba(255,243,228,0.74)",
    tint: "rgba(21,11,6,0.36)",
    letterbox: 0,
    labelColor: "#FFB03A",
    cardBg: "rgba(30,17,10,0.86)",
    cardBorder: "rgba(255,176,58,0.42)",
    glowRgb: "255,176,58",
    glow: "rgba(255,176,58,0.13)",
    grain: 0.05,
    vignette: 0.30,
  },
};

/** 当前启用的风格：换风格只改这一行（重渲即生效）。
 *  ★ 风格按选题自适应（AI 分镜时决定，别无脑用默认）：
 *    科技/AI/数码 → tech；本地餐饮/门店/民生消费 → vivid；
 *    品牌/文创/暖调故事 → warm；通用叙事/暗调大片 → cinematic。 */
export const ACTIVE_STYLE: StyleId = "tech";
export const S = STYLES[ACTIVE_STYLE];

/* ================= 排版自适应工具（源自 PPT 任务实战） ================= */

/** 视觉宽度单位：中文全角 ≈ 1.0，英数半角 ≈ 0.58 */
export const textUnits = (s: string): number => {
  let n = 0;
  for (const ch of s) n += /[\x00-\xff]/.test(ch) ? 0.58 : 1;
  return n;
};

/**
 * 按容器可用宽度反推字号（防溢出/孤字行）。
 * letterSpacing 单位 em（如 0.02）。
 */
export const fitFontSize = (
  text: string,
  availWidth: number,
  maxSize: number,
  minSize = 20,
  letterSpacing = 0,
): number => {
  const u = textUnits(text) + text.length * letterSpacing;
  const size = availWidth / Math.max(1, u);
  return Math.max(minSize, Math.min(maxSize, Math.floor(size)));
};
