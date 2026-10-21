import React from "react";
import {
  AbsoluteFill,
  Audio as RawAudio,
  Composition,
  Sequence,
  staticFile,
  useCurrentFrame,
} from "remotion";
import timeline from "./data/timeline.json";
import { MediaScene, type OverlaySpec } from "./scenes/MediaScene";
import { Caption } from "./Caption";
import { COLORS, S } from "./theme";
import type { Timeline } from "./types";

// Remotion 4.0 类型与 React 19 types 存在兼容差异，轻量封装
const Audio = RawAudio as unknown as React.FC<{
  src: string;
  volume?: number | ((frame: number) => number);
}>;

/**
 * 素材映射：shot id → public/media/ 下文件名。
 * 由 fetch_media.py 的 media_manifest.json 驱动；缺失项回退纯图形层（不白屏）。
 * ★ 2026-10-17：只采集视频，无图片；id 与 gen_narration.py 的分句一一对应。
 */
const MEDIA: Record<string, string> = {
  p1_s0: "p1_s0.mp4", p1_s1: "p1_s1.mp4", p1_s2: "p1_s2.mp4",
  p2_s0: "p2_s0.mp4", p2_s1: "p2_s1.mp4", p2_s2: "p2_s2.mp4",
  p3_s0: "p3_s0.mp4", p3_s1: "p3_s1.mp4", p3_s2: "p3_s2.mp4",
  p4_s0: "p4_s0.mp4", p4_s1: "p4_s1.mp4", p4_s2: "p4_s2.mp4",
  p4_s3: "p4_s3.mp4", p4_s4: "p4_s4.mp4",
  p5_s0: "p5_s0.mp4", p5_s1: "p5_s1.mp4", p5_s2: "p5_s2.mp4",
  p6_s0: "p6_s0.mp4", p6_s1: "p6_s1.mp4", p6_s2: "p6_s2.mp4", p6_s3: "p6_s3.mp4",
};

/**
 * 每页图形叠加配置（通道 B）—— 换文案时只改这里。
 * ★ 版式规约（2026-10-17 用户两轮反馈后的定位）：
 *   - 主画面只放**提炼**内容：封面 / 金句 / 关键词卡片 / 大数字 / 结论条；
 *   - 完整讲稿走底部单行字幕（Caption），主屏不搬全文；
 *   - 关键词按项数自适应布局：3=正三角形、4=2×2、5=3+2、6=3+3；
 *   - triggerWord = 说到这个词时元素入场/高亮（跨镜头匹配）。
 */
const OVERLAYS: Record<string, OverlaySpec> = {
  p1: {
    cover: { tag: "微信原生 AI 助手", title: "小微", subtitle: "一分钟讲清最新状态" },
    bigNumber: { value: 28, suffix: "个入口", label: "覆盖微信常用场景", triggerWord: "二十八个" },
  },
  p2: {
    section: { label: "一 · 最新进展", title: "灰度半年，已上 PC 版" },
    golden: [{ text: "每次任务只激活 30 亿参数", triggerWord: "三十亿" }],
    keywords: [
      { text: "6/20 启动灰度", icon: "calendar", triggerWord: "六月二十号" },
      { text: "9 月扩大范围", icon: "users", triggerWord: "扩大范围" },
      { text: "9/15 登陆 PC 版", icon: "monitor", triggerWord: "九月十五号" },
    ],
  },
  p3: {
    section: { label: "二 · 入口全景", title: "28 个入口分布在 9 个场景" },
    keywords: [
      { text: "消息首页", num: "×1", icon: "eye", triggerWord: "主入口" },
      { text: "聊天", num: "×5", icon: "chat", triggerWord: "聊天场景" },
      { text: "朋友圈", num: "×5", icon: "users", triggerWord: "朋友圈场景" },
      { text: "公众号", num: "×6", icon: "fileText", triggerWord: "公众号场景" },
      { text: "电脑端", num: "×4", icon: "monitor", triggerWord: "电脑端四个" },
    ],
    banner: { text: "不是独立 App，嵌在每个环节里", icon: "check", triggerWord: "环节" },
  },
  p4: {
    section: { label: "三 · 全量开放", title: "四个入口人人可用" },
    golden: [{ text: "没有灰度资格，现在就能用", triggerWord: "不管你有没有" }],
    keywords: [
      { text: "公众号 AI 摘要", icon: "fileText", triggerWord: "第一个" },
      { text: "搜索框长按问小微", icon: "search", triggerWord: "第二个" },
      { text: "电脑端右键问 AI", icon: "monitor", triggerWord: "第三个" },
      { text: "内置浏览器问 AI", icon: "globe", triggerWord: "第四个" },
    ],
    banner: { text: "现在就可以打开微信试试看", icon: "sparkles", triggerWord: "试试看" },
  },
  p5: {
    section: { label: "四 · 安全边界", title: "官方划了三条红线" },
    keywords: [
      { text: "不主动读取", desc: "手动点问，才临时调用上下文", icon: "lock", triggerWord: "不会主动读取" },
      { text: "用完即弃", desc: "不存档不上传做训练", icon: "trash", triggerWord: "立刻丢弃" },
      { text: "不碰账户", desc: "资金操作必须本人确认", icon: "shield", triggerWord: "资金操作" },
    ],
    banner: { text: "资金操作必须由你本人确认", icon: "shield", triggerWord: "账户" },
  },
  p6: {
    golden: [
      { text: "没有也不用急，四个入口现在就能用", triggerWord: "没有也不用急" },
      { text: "关注视频号 AIST2030", triggerWord: "关注" },
    ],
    banner: { text: "下一期详解 28 个入口怎么用", icon: "sparkles", triggerWord: "下一期" },
  },
};

const Main: React.FC = () => {
  const tl = timeline as unknown as Timeline;
  const { pages } = tl;

  return (
    <AbsoluteFill style={{ backgroundColor: S.bg }}>
      {pages.map((p, pi) => (
        <Sequence
          key={p.id}
          from={p.startFrame}
          durationInFrames={p.durationFrames}
          name={p.id}
        >
          <MediaScene
            page={p}
            media={MEDIA}
            overlay={OVERLAYS[p.id] ?? {}}
            pageIndex={pi + 1}
          />
          {/* ★ 底部单行卡拉OK字幕（用户明令：保持原来的样式，坚决一行）。
              完整讲稿在这里走词级高亮；主画面只放提炼内容。 */}
          <Caption page={p} />
          {p.shots.map((s) => (
            <Sequence
              key={s.id}
              from={s.startFrame}
              durationInFrames={Math.max(1, s.durationFrames)}
              name={s.id}
            >
              <Audio src={staticFile(s.audioFile)} />
            </Sequence>
          ))}
        </Sequence>
      ))}

      {/* ★ 2026-10-17 用户明令：不要 BGM。背景音乐整体移除（音效走 MediaScene 内 Sfx） */}

      <ProgressBar tl={tl} />
    </AbsoluteFill>
  );
};

/** 顶部细进度条 */
const ProgressBar: React.FC<{ tl: Timeline }> = ({ tl }) => {
  const frame = useCurrentFrame();
  const p = tl.totalFrames > 0 ? frame / tl.totalFrames : 0;
  return (
    <div
      style={{
        position: "absolute",
        top: 0,
        left: 0,
        height: 4,
        background: `linear-gradient(90deg, ${S.primary}, ${S.primaryBright})`,
        boxShadow: `0 0 10px ${S.primary}99`,
        width: `${p * 100}%`,
      }}
    />
  );
};

export const RemotionRoot: React.FC = () => {
  const tl = timeline as unknown as Timeline;
  return (
    <Composition
      id="WeiXinXiaoWei"
      component={Main}
      durationInFrames={tl.totalFrames}
      fps={tl.fps}
      width={tl.width}
      height={tl.height}
    />
  );
};
