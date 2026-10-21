import React from "react";
import type { PageData } from "../types";
import { trigger, usePageT } from "../Caption";
import {
  BrandChip,
  Glyph,
  PageNum,
  SceneFade,
} from "../ui";
import {
  COLORS,
  FONT,
  LAYOUT,
  TYPE,
  clamp01,
  easeOutCubic,
  fadeIn,
  pulse,
  reveal,
  win,
} from "../theme";

/** P1 封面：微信小微AI · 28个入口已经铺满微信 */
export const Cover: React.FC<{ page: PageData }> = ({ page }) => {
  const t = usePageT();
  const tTitle = trigger(page, 0, "大家好");
  const tLead = trigger(page, 1, "这一期");
  const tTag = trigger(page, 1, "状态", "end");
  const tDate = trigger(page, 2, "二零二六年");
  const tCount = trigger(page, 2, "二十八个");
  const tOut = trigger(page, 2, "地方", "end");

  // 封面大数字 28：随「二十八个」出口时滚动累加
  const countP = win(t, tCount, tCount + 1.1);
  const count = Math.round(28 * easeOutCubic(countP));

  const titleA = reveal(t, tTitle, 0.6);
  const leadA = reveal(t, tLead, 0.55);
  const tagA = reveal(t, tTag, 0.5);
  const dateA = fadeIn(t, tDate, 0.5);
  const outA = fadeIn(t, tOut, 0.5);

  return (
    <SceneFade t={t} pageDur={page.duration}>
      {/* 背景装饰：若隐若现的微信绿眼睛（小微主入口意象） */}
      <div
        style={{
          position: "absolute",
          left: "50%",
          top: 300,
          transform: "translate(-50%, -50%)",
          opacity: 0.1 + 0.05 * pulse(t, 3.2),
          filter: "blur(1px)",
        }}
      >
        <Glyph name="eye" size={420} color={COLORS.wechatGreen} strokeWidth={0.7} />
      </div>

      {/* 背景大数字水印 */}
      <div
        style={{
          position: "absolute",
          left: 0,
          right: 0,
          top: 560,
          textAlign: "center",
          fontFamily: FONT.family,
          fontSize: 460,
          fontWeight: 800,
          lineHeight: 1,
          color: "rgba(232,198,110,0.07)",
          opacity: clamp01(win(t, tCount - 0.2, tCount + 0.8)),
          userSelect: "none",
        }}
      >
        {count}
      </div>

      <BrandChip t={t} />

      {/* 主标题 */}
      <div
        style={{
          position: "absolute",
          left: 0,
          right: 0,
          top: 400,
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          gap: 18,
          opacity: clamp01(titleA),
          transform: `translateY(${(1 - clamp01(titleA)) * 40}px) scale(${0.9 + 0.1 * clamp01(titleA)})`,
        }}
      >
        <div
          style={{
            fontFamily: FONT.family,
            fontSize: TYPE.hero,
            fontWeight: 800,
            letterSpacing: 4,
            background: `linear-gradient(180deg, ${COLORS.goldBright} 20%, ${COLORS.gold} 80%)`,
            WebkitBackgroundClip: "text",
            backgroundClip: "text",
            color: "transparent",
            filter: "drop-shadow(0 6px 30px rgba(232,198,110,0.35))",
          }}
        >
          微信小微AI
        </div>
      </div>

      {/* 副标题 */}
      <div
        style={{
          position: "absolute",
          left: LAYOUT.marginX,
          right: LAYOUT.marginX,
          top: 610,
          textAlign: "center",
          fontFamily: FONT.family,
          fontSize: TYPE.lead,
          fontWeight: 700,
          color: COLORS.ink,
          letterSpacing: 2,
          opacity: clamp01(leadA),
          transform: `translateY(${(1 - clamp01(leadA)) * 30}px)`,
          textShadow: "0 4px 20px rgba(0,0,0,0.7)",
        }}
      >
        28个入口已经铺满微信
      </div>

      {/* 标签芯片 */}
      <div
        style={{
          position: "absolute",
          left: 0,
          right: 0,
          top: 730,
          display: "flex",
          justifyContent: "center",
          opacity: clamp01(tagA),
          transform: `scale(${0.85 + 0.15 * clamp01(tagA)})`,
        }}
      >
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: 12,
            padding: "14px 34px",
            borderRadius: 999,
            background: "rgba(110,207,216,0.1)",
            border: `1px solid ${COLORS.cyanDim}`,
          }}
        >
          <Glyph name="sparkles" size={28} color={COLORS.cyan} />
          <span
            style={{
              fontFamily: FONT.family,
              fontSize: 30,
              color: COLORS.cyan,
              fontWeight: 600,
              letterSpacing: 2,
            }}
          >
            最新消息盘点 · 9大场景全梳理
          </span>
        </div>
      </div>

      {/* 数据日期 */}
      <div
        style={{
          position: "absolute",
          left: 0,
          right: 0,
          top: 850,
          textAlign: "center",
          fontFamily: FONT.family,
          fontSize: TYPE.label,
          color: COLORS.inkSoft,
          letterSpacing: 3,
          opacity: dateA,
        }}
      >
        数据截至 二零二六年十月
      </div>

      {/* 出品方 */}
      <div
        style={{
          position: "absolute",
          left: 0,
          right: 0,
          top: 1120,
          display: "flex",
          justifyContent: "center",
          alignItems: "center",
          gap: 14,
          opacity: outA,
        }}
      >
        <div
          style={{
            width: 40,
            height: 2,
            background: COLORS.goldDim,
          }}
        />
        <span
          style={{
            fontFamily: FONT.family,
            fontSize: TYPE.label,
            color: COLORS.gold,
            letterSpacing: 6,
            fontWeight: 600,
          }}
        >
          AIST2030 出品
        </span>
        <div
          style={{
            width: 40,
            height: 2,
            background: COLORS.goldDim,
          }}
        />
      </div>

      <PageNum t={t} n={1} />
    </SceneFade>
  );
};
