import React from "react";
import type { PageData } from "../types";
import { trigger, usePageT } from "../Caption";
import {
  BrandChip,
  Glyph,
  PageNum,
  Banner,
  SceneFade,
  SectionHeader,
  StatCard,
} from "../ui";
import {
  COLORS,
  FONT,
  LAYOUT,
  TYPE,
  clamp01,
  fadeIn,
  reveal,
  win,
} from "../theme";

/** P2 最新进展：灰度时间线 + 四项关键数据 */
export const Progress: React.FC<{ page: PageData }> = ({ page }) => {
  const t = usePageT();
  const tHead = page.shots[0].start + 0.05;
  const tN1 = trigger(page, 1, "二十号");
  const tN2 = trigger(page, 1, "扩大");
  const tN3 = trigger(page, 1, "十五号");
  const tBanner = trigger(page, 1, "PC");
  const tCard3 = trigger(page, 2, "WeLM");
  const tCard4 = trigger(page, 2, "长上下文");
  const END = 1e9;

  const nodes = [
    { at: tN1, date: "06.20", label: "启动灰度" },
    { at: tN2, date: "09月", label: "扩大范围" },
    { at: tN3, date: "09.15", label: "登陆PC版微信" },
  ];

  return (
    <SceneFade t={t} pageDur={page.duration}>
      <BrandChip t={t} />
      <SectionHeader
        t={t}
        at={tHead}
        label="一 · 最新进展"
        title="小微还在灰度，入口已铺到28个"
      />

      {/* 灰度推进时间线 */}
      <div
        style={{
          position: "absolute",
          left: LAYOUT.marginX,
          right: LAYOUT.marginX,
          top: 400,
          height: 170,
        }}
      >
        {/* 连接线 */}
        <div
          style={{
            position: "absolute",
            left: 60,
            right: 60,
            top: 34,
            height: 3,
            background: "rgba(232,198,110,0.18)",
            borderRadius: 2,
          }}
        />
        <div
          style={{
            position: "absolute",
            left: 60,
            top: 34,
            height: 3,
            width: `calc(100% - 120px)`,
            background: `linear-gradient(90deg, ${COLORS.gold}, ${COLORS.goldDeep})`,
            borderRadius: 2,
            transformOrigin: "left center",
            transform: `scaleX(${clamp01(win(t, tN1 - 0.1, tN3))})`,
            boxShadow: "0 0 12px rgba(232,198,110,0.5)",
          }}
        />
        <div style={{ display: "flex", justifyContent: "space-between" }}>
          {nodes.map((n, i) => {
            const a = reveal(t, n.at, 0.45);
            return (
              <div
                key={i}
                style={{
                  display: "flex",
                  flexDirection: "column",
                  alignItems: "center",
                  gap: 10,
                  width: 200,
                  opacity: clamp01(a),
                  transform: `translateY(${(1 - clamp01(a)) * 20}px)`,
                }}
              >
                <div
                  style={{
                    width: 22,
                    height: 22,
                    borderRadius: 11,
                    background: COLORS.gold,
                    border: `4px solid ${COLORS.void}`,
                    boxShadow: "0 0 16px rgba(232,198,110,0.8)",
                  }}
                />
                <span
                  style={{
                    fontFamily: FONT.family,
                    fontSize: 32,
                    fontWeight: 800,
                    color: COLORS.goldBright,
                  }}
                >
                  {n.date}
                </span>
                <span
                  style={{
                    fontFamily: FONT.family,
                    fontSize: 24,
                    color: COLORS.inkSoft,
                  }}
                >
                  {n.label}
                </span>
              </div>
            );
          })}
        </div>
      </div>

      {/* 2x2 数据卡片 */}
      <div
        style={{
          position: "absolute",
          left: LAYOUT.marginX,
          right: LAYOUT.marginX,
          top: 620,
          display: "grid",
          gridTemplateColumns: "1fr 1fr",
          gap: 20,
        }}
      >
        <StatCard
          t={t}
          at={tHead + 0.3}
          num="28"
          unit="个"
          title="入口"
          desc="覆盖微信9大使用场景"
          icon="globe"
          activeFrom={tHead}
          activeTo={tN1}
        />
        <StatCard
          t={t}
          at={tN1}
          num="4"
          unit="个"
          title="全量开放"
          desc="即便没灰度，人人都能用"
          icon="check"
          activeFrom={tN1}
          activeTo={tCard3}
        />
        <StatCard
          t={t}
          at={tCard3}
          title="WeLM-80B主模型"
          desc="总参数800亿 · 激活30亿"
          icon="sparkles"
          activeFrom={tCard3}
          activeTo={tCard4}
        />
        <StatCard
          t={t}
          at={tCard4}
          title="128K长上下文"
          desc="支持约十万字长文本"
          icon="fileText"
          activeFrom={tCard4}
          activeTo={END}
        />
      </div>

      <Banner t={t} at={tBanner} text="九月已登陆PC端，桌面端同步可用" icon="monitor" />
      <PageNum t={t} n={2} />
    </SceneFade>
  );
};
