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

// Remotion 4.0 类型与 React 19 types 兼容差异，轻量封装
const Audio = RawAudio as unknown as React.FC<{
  src: string;
  volume?: number | ((frame: number) => number);
}>;

/**
 * 素材播放列表：页 id → public/media/ 文件名数组（★ v2.1 一页多素材）。
 * 默认「一页一列表」：整页用 remotion/public/media/p{n}*.mp4；
 * fetch_media.py 会按 shotplan 落成 p{n}.mp4 或 p{n}x{k}.mp4，
 * 这里把同一页的多个文件按期望顺序列入数组即可 —— 播放列表会按
 * mediaDurations.json 的实测时长顺序排段、0.6s 交叉淡接、单段上限 6.5s、
 * 整页不够长自动循环（根治单素材循环的停滞/重复感）。
 * ★ 换素材后必须重跑：python scripts/gen_media_durations.py --project <项目根>
 *
 * ★ 用户自定义素材：把 video 放进 public/custom_media/（同名 p{n}.mp4），
 *   跑 fetch_media.py --custom public/custom_media 会优先于 Mixkit 使用（不联网）。
 */
const PLAYLIST: Record<string, string[]> = (() => {
  const m: Record<string, string[]> = {};
  const tl = timeline as unknown as Timeline;
  for (const p of tl.pages) {
    const pid = p.id.replace("p", "");
    m[p.id] = [`p${pid}.mp4`]; // 多素材页改成 ["p1x1.mp4","p1x2.mp4",...]
  }
  return m;
})();

/**
 * 每页图形叠加配置（通道 B）——★ 换文案时只改这里 /这是 AI 分镜的主要产出。
 *
 * 版式规约：
 *   - 主画面只放提炼内容：封面 / 金句 / 关键词卡片 / 大数字 / 结论条；
 *   - 完整讲稿走底部单行字幕（Caption），主屏不搬全文；
 *   - 关键词按项数自适应布局：3=正三角 / 4=2×2 / 5=3+2 / 6=3+3 / 9=3×3；
 *   - triggerWord = 说到这个词时元素入场/高亮（跨镜头匹配）。
 *
 * ★★ HARD RULE：每个 triggerWord 必须**逐字出现在该页旁白里**，否则元素永不入场
 *   （渲染不报错，画面静默少一块）。改完文案务必跑：
 *     python scripts/check_triggers.py --project .
 *
 * 可用叠加类型（见 scenes/MediaScene.tsx 的 OverlaySpec）：
 *   cover{ tag,title,subtitle }封面（大标题）
 *   section  { label,title }            章节页眉
 *   keywords [{ text,triggerWord }]    关键词卡片（自适应网格）
 *   golden   [{ text,triggerWord }]    金句（居中大字）
 *   banner   { text,triggerWord }      结论横条
 *   num      { value,unit,label,triggerWord }  大数字
 *   list     [{ title,desc }]          要点列表
 *
 * 风格：theme.ts 的 ACTIVE_STYLE（cinematic / tech / warm / vivid，按选题自适应）。
 * 音效：sfxConfig.ts 驱动（enabled 为用户试听勾选的音效池）。
 * 画中画：pipConfig.ts 驱动（PIP.enabled=true + public/pip/pip.mp4 即开）。
 */
const OVERLAYS: Record<string, OverlaySpec> = {
  // ★★★ 这里是空的 —— AI 分镜时按逐页填入 ★★★
  // 示例（p1 封面）：
  // p1: {
  //   cover: { tag: "标签", title: "主标题", subtitle: "副标题" },
  // },
  // 示例（p2 章节 + 关键词）：
  // p2: {
  //   section: { label: "一 · 开篇", title: "章节标题" },
  //   keywords: [
  //     { text: "要点一", triggerWord: "第一个" },
  //     { text: "要点二", triggerWord: "第二个" },
  //   ],
  //   banner: { text: "本页结论", triggerWord: "一句话结论词" },
  // },
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
            playlist={PLAYLIST[p.id] ?? []}
            overlay={OVERLAYS[p.id] ?? {}}
            pageIndex={pi + 1}
            totalPages={pages.length}
          />
          {/* 底部单行卡拉OK字幕（严格一行；完整讲稿走这里，主画面只放提炼） */}
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