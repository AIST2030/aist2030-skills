import React from "react";
import type { PageData } from "../types";
import { trigger, usePageT } from "../Caption";
import {
  BrandChip,
  Banner,
  GhostCard,
  ListRow,
  PageNum,
  SceneFade,
  SectionHeader,
} from "../ui";
import { COLORS, FONT, LAYOUT, TYPE, clamp01, fadeIn, win } from "../theme";

/** P4 全量开放：4个不用等灰度的入口 */
export const OpenAccess: React.FC<{ page: PageData }> = ({ page }) => {
  const t = usePageT();
  const tHead = page.shots[0].start + 0.05;
  const r1 = trigger(page, 1, "第一个");
  const r2 = trigger(page, 1, "第二个");
  const r3 = trigger(page, 2, "第三个");
  const r4 = trigger(page, 2, "第四个");
  const tBanner = trigger(page, 3, "现在");
  const END = 1e9;

  // 骨架占位：未到触发时刻的条目用等高虚线框占位，保证四行布局始终稳定
  const pending = (at: number) => t < at - 0.05;

  return (
    <SceneFade t={t} pageDur={page.duration}>
      <BrandChip t={t} />
      <SectionHeader
        t={t}
        at={tHead}
        label="三 · 全量开放"
        title="这4个入口，现在就能用"
      />

      <div
        style={{
          position: "absolute",
          left: LAYOUT.marginX,
          right: LAYOUT.marginX,
          top: 420,
          display: "flex",
          flexDirection: "column",
          gap: 22,
        }}
      >
        {pending(r1) ? (
          <GhostCard h={116} />
        ) : (
          <ListRow
            t={t}
            at={r1}
            index={1}
            title="公众号文章AI摘要"
            desc="任意公众号文章，标题下方直接显示AI摘要入口"
            icon="fileText"
            activeFrom={r1}
            activeTo={r2}
          />
        )}
        {pending(r2) ? (
          <GhostCard h={116} />
        ) : (
          <ListRow
            t={t}
            at={r2}
            index={2}
            title="搜索页按住问小微"
            desc="微信顶部搜索框长按直接语音唤起小微"
            icon="search"
            activeFrom={r2}
            activeTo={r3}
          />
        )}
        {pending(r3) ? (
          <GhostCard h={116} />
        ) : (
          <ListRow
            t={t}
            at={r3}
            index={3}
            title="PC聊天右键问AI"
            desc="电脑微信里右键选中文字，直接调用AI分析"
            icon="monitor"
            activeFrom={r3}
            activeTo={r4}
          />
        )}
        {pending(r4) ? (
          <GhostCard h={116} />
        ) : (
          <ListRow
            t={t}
            at={r4}
            index={4}
            title="PC内置浏览器问AI"
            desc="微信内置浏览器打开网页，页面直接有小微入口"
            icon="globe"
            activeFrom={r4}
            activeTo={END}
          />
        )}
      </div>

      <Banner t={t} at={tBanner} text="不用等灰度，打开微信现在就能体验" icon="check" />
      <PageNum t={t} n={4} />
    </SceneFade>
  );
};
