import React from "react";
import type { PageData } from "../types";
import { trigger, usePageT } from "../Caption";
import {
  BrandChip,
  Banner,
  GhostCard,
  PageNum,
  SceneFade,
  SectionHeader,
  StatCard,
} from "../ui";
import { COLORS, LAYOUT } from "../theme";

/** P5 安全边界：三条红线 + 权限对等 */
export const Safety: React.FC<{ page: PageData }> = ({ page }) => {
  const t = usePageT();
  const tHead = page.shots[0].start + 0.05;
  const c1 = trigger(page, 1, "第一");
  const c2 = trigger(page, 2, "第二");
  const c3 = trigger(page, 3, "第三");
  const c4 = trigger(page, 3, "账户");
  const tBanner = trigger(page, 0, "红线");
  const END = 1e9;
  const CARD_H = 214;
  const pending = (at: number) => t < at - 0.05;

  return (
    <SceneFade t={t} pageDur={page.duration}>
      <BrandChip t={t} />
      <SectionHeader
        t={t}
        at={tHead}
        label="四 · 安全边界"
        title="能力很强，权限很克制"
      />

      <div
        style={{
          position: "absolute",
          left: LAYOUT.marginX,
          right: LAYOUT.marginX,
          top: 430,
          display: "grid",
          gridTemplateColumns: "1fr 1fr",
          gap: 22,
        }}
      >
        {pending(c1) ? (
          <GhostCard h={CARD_H} />
        ) : (
          <StatCard
            t={t}
            at={c1}
            title="读取有边界"
            desc="不主动读聊天，只有你点它才临时调用当前页"
            icon="bookOpen"
            activeFrom={c1}
            activeTo={c2}
          />
        )}
        {pending(c2) ? (
          <GhostCard h={CARD_H} />
        ) : (
          <StatCard
            t={t}
            at={c2}
            title="数据用完即弃"
            desc="不存档不上传，不用于模型训练"
            icon="trash"
            activeFrom={c2}
            activeTo={c3}
          />
        )}
        {pending(c3) ? (
          <GhostCard h={CARD_H} />
        ) : (
          <StatCard
            t={t}
            at={c3}
            title="资金有隔离"
            desc="转账发红包必须你手动点确认，AI不能碰账户"
            icon="wallet"
            activeFrom={c3}
            activeTo={c4}
          />
        )}
        {pending(c4) ? (
          <GhostCard h={CARD_H} />
        ) : (
          <StatCard
            t={t}
            at={c4}
            title="权限对等"
            desc="它能看到的信息不会超过你本人能看到的"
            icon="lock"
            activeFrom={c4}
            activeTo={END}
          />
        )}
      </div>

      <Banner t={t} at={tBanner} text="官方已经把隐私边界说得明明白白" icon="shield" />
      <PageNum t={t} n={5} />
    </SceneFade>
  );
};
