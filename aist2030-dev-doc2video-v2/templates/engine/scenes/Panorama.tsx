import React from "react";
import type { PageData } from "../types";
import { trigger, usePageT } from "../Caption";
import {
  BrandChip,
  Banner,
  FormulaChip,
  PageNum,
  PlusSign,
  SceneFade,
  SectionHeader,
  StatCard,
} from "../ui";
import { COLORS, FONT, LAYOUT, TYPE, clamp01, fadeIn } from "../theme";

/** P3 入口全景：28个入口 = 9大场景公式 + 四类场景芯片 */
export const Panorama: React.FC<{ page: PageData }> = ({ page }) => {
  const t = usePageT();
  const tHead = page.shots[0].start + 0.05;

  // 公式行：随旁白逐项点亮
  const f1 = trigger(page, 1, "主入口");
  const f2 = trigger(page, 1, "聊天");
  const f3 = trigger(page, 1, "朋友圈");
  const f4 = trigger(page, 1, "公众号");
  const f5 = trigger(page, 1, "视频号");

  // 四类场景卡
  const g1 = trigger(page, 2, "听一听");
  const g2 = trigger(page, 2, "扫一扫");
  const g3 = trigger(page, 2, "搜索");
  const g4 = trigger(page, 2, "电脑端");
  const tBanner = trigger(page, 3, "小微");
  const END = 1e9;

  return (
    <SceneFade t={t} pageDur={page.duration}>
      <BrandChip t={t} />
      <SectionHeader
        t={t}
        at={tHead}
        label="二 · 入口全景"
        title="28个入口分布在9个场景"
      />

      {/* 公式行：1主入口 + 5聊天 + 5朋友圈 + 6公众号 + 2视频号 */}
      <div
        style={{
          position: "absolute",
          left: LAYOUT.marginX,
          right: LAYOUT.marginX,
          top: 408,
          display: "flex",
          alignItems: "stretch",
          gap: 8,
        }}
      >
        <FormulaChip t={t} at={f1} num="1" label="主入口" icon="eye" activeFrom={f1} activeTo={f2} />
        <PlusSign t={t} at={f1} />
        <FormulaChip t={t} at={f2} num="5" label="聊天" icon="chat" activeFrom={f2} activeTo={f3} />
        <PlusSign t={t} at={f2} />
        <FormulaChip t={t} at={f3} num="5" label="朋友圈" icon="users" activeFrom={f3} activeTo={f4} />
        <PlusSign t={t} at={f3} />
        <FormulaChip t={t} at={f4} num="6" label="公众号" icon="fileText" activeFrom={f4} activeTo={f5} />
        <PlusSign t={t} at={f4} />
        <FormulaChip t={t} at={f5} num="2" label="视频号" icon="play" activeFrom={f5} activeTo={END} />
      </div>

      {/* 2x2 场景卡 */}
      <div
        style={{
          position: "absolute",
          left: LAYOUT.marginX,
          right: LAYOUT.marginX,
          top: 610,
          display: "grid",
          gridTemplateColumns: "1fr 1fr",
          gap: 20,
        }}
      >
        <StatCard
          t={t}
          at={g1}
          title="2个听一听"
          desc="听歌场景AI问答与推荐"
          icon="music"
          activeFrom={g1}
          activeTo={g2}
        />
        <StatCard
          t={t}
          at={g2}
          title="2个图片扫一扫"
          desc="截图处理与拍照识别"
          icon="scan"
          activeFrom={g2}
          activeTo={g3}
        />
        <StatCard
          t={t}
          at={g3}
          title="1个搜索场景"
          desc="搜一搜按住语音问小微"
          icon="search"
          activeFrom={g3}
          activeTo={g4}
        />
        <StatCard
          t={t}
          at={g4}
          title="4个PC专属入口"
          desc="桌面端微信右键唤起AI"
          icon="monitor"
          activeFrom={g4}
          activeTo={END}
        />
      </div>

      <Banner t={t} at={tBanner} text="入口埋在你日常用微信的每一个环节" icon="globe" />
      <PageNum t={t} n={3} />
    </SceneFade>
  );
};
