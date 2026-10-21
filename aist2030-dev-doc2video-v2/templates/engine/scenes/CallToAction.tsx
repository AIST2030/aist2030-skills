import React from "react";
import type { PageData } from "../types";
import { trigger, usePageT } from "../Caption";
import {
  BrandChip,
  Banner,
  Glyph,
  PageNum,
  SceneFade,
  SectionHeader,
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

/** P6 行动号召：找到首页左上角的绿色眼睛图标 */
export const CallToAction: React.FC<{ page: PageData }> = ({ page }) => {
  const t = usePageT();
  const tHead = page.shots[0].start + 0.05;
  const tEye = trigger(page, 0, "绿色眼睛");
  const tLine1 = page.shots[1].start + 0.05;
  const tLine2 = trigger(page, 1, "恭喜");
  const tCta = trigger(page, 2, "关注");
  const tBanner = trigger(page, 2, "下一期");

  const eyeA = reveal(t, tEye, 0.7);
  const ringPulse = 0.5 + 0.5 * pulse(t, 2.0);

  return (
    <SceneFade t={t} pageDur={page.duration}>
      <BrandChip t={t} />
      <SectionHeader
        t={t}
        at={tHead}
        label="现在就做"
        title="打开微信，看看首页左上角"
      />

      {/* 中央：绿色眼睛图标 + 脉冲光环 */}
      <div
        style={{
          position: "absolute",
          left: 0,
          right: 0,
          top: 430,
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          gap: 30,
        }}
      >
        <div
          style={{
            position: "relative",
            width: 220,
            height: 220,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            opacity: clamp01(eyeA),
            transform: `scale(${0.6 + 0.4 * clamp01(eyeA)})`,
          }}
        >
          {/* 脉冲光环 */}
          <div
            style={{
              position: "absolute",
              inset: 0,
              borderRadius: 110,
              border: `2px solid rgba(7,193,96,${0.25 + 0.35 * ringPulse})`,
              transform: `scale(${1 + 0.12 * ringPulse})`,
              boxShadow: `0 0 ${30 + 30 * ringPulse}px rgba(7,193,96,${0.2 + 0.2 * ringPulse})`,
            }}
          />
          <div
            style={{
              position: "absolute",
              inset: 26,
              borderRadius: 84,
              background:
                "radial-gradient(circle at 50% 42%, rgba(7,193,96,0.28) 0%, rgba(11,20,36,0.9) 70%)",
              border: "1px solid rgba(7,193,96,0.5)",
            }}
          />
          <Glyph name="eye" size={110} color={COLORS.wechatGreen} strokeWidth={1.6} />
        </div>

        {/* 两行说明 */}
        <div
          style={{
            fontFamily: FONT.family,
            fontSize: 40,
            fontWeight: 700,
            color: COLORS.ink,
            letterSpacing: 1,
            opacity: clamp01(fadeIn(t, tLine1, 0.5)),
            transform: `translateY(${(1 - clamp01(fadeIn(t, tLine1, 0.5))) * 20}px)`,
            textShadow: "0 4px 20px rgba(0,0,0,0.7)",
          }}
        >
          那个绿色眼睛图标，就是小微主入口
        </div>
        <div
          style={{
            fontFamily: FONT.family,
            fontSize: 34,
            color: COLORS.inkSoft,
            letterSpacing: 1,
            opacity: clamp01(fadeIn(t, tLine2, 0.5)),
            transform: `translateY(${(1 - clamp01(fadeIn(t, tLine2, 0.5))) * 20}px)`,
          }}
        >
          有的话，恭喜你已经在第一批里了
        </div>
      </div>

      {/* 关注 CTA */}
      <div
        style={{
          position: "absolute",
          left: LAYOUT.marginX,
          right: LAYOUT.marginX,
          top: 950,
          display: "flex",
          justifyContent: "center",
          opacity: clamp01(reveal(t, tCta, 0.55)),
          transform: `translateY(${(1 - clamp01(reveal(t, tCta, 0.55))) * 26}px)`,
        }}
      >
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: 16,
            padding: "20px 44px",
            borderRadius: 999,
            background: "linear-gradient(135deg, rgba(232,198,110,0.22) 0%, rgba(18,32,54,0.9) 70%)",
            border: `1px solid ${COLORS.goldDim}`,
            boxShadow: "0 0 30px rgba(232,198,110,0.2)",
          }}
        >
          <Glyph name="sparkles" size={34} color={COLORS.goldBright} />
          <span
            style={{
              fontFamily: FONT.family,
              fontSize: 36,
              fontWeight: 700,
              color: COLORS.goldBright,
              letterSpacing: 2,
            }}
          >
            关注视频号 AIST2030
          </span>
        </div>
      </div>

      <Banner t={t} at={tBanner} text="下一期我们详解28个入口的用法" icon="arrow" />
      <PageNum t={t} n={6} />
    </SceneFade>
  );
};
