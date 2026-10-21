// 音效配置（用户试听勾选后由 AI 回写 enabled 列表）。
// map: 每个触发事件默认映射的音效文件；enabled: 实际启用的文件池。
// 若某事件映射的文件不在 enabled 中 → 该事件静音（尊重用户勾选）。

import { SFX_DATA } from "./data/sfxData";

export type SfxTrigger =
  | "cover"
  | "section"
  | "golden"
  | "keywordEnter"
  | "bigNumber"
  | "banner";

export const SFX_CONFIG: {
  enabled: string[];
  map: Record<SfxTrigger, string>;
} = {
  // ★ 用户 2026-10-17 试听勾选结果：**只保留 4 个**（全部是短促 UI 反馈音，
  //   无人声/无夸张转场音），其余 18 个一律不进池。
  //   选型逻辑：这套视频是逐字跟读的科技风解说，whoosh/sparkle/magic/impact
  //   这类"过场大音效"会压旁白；短 click/pop/interface/notification 最贴 UI 反馈语义。
  enabled: [
    "click_1.mp3",
    "interface_1.mp3",
    "notification_1.mp3",
    "pop.mp3",
  ],
  map: {
    // 4 个音分给 6 个触发点，按语义强弱分配，避免同页反复撞同一个音
    cover: "notification_1.mp3", // 开场：提示进入，音量足但不喧哗
    section: "interface_1.mp3", // 章节切换：界面感，跟"翻页"动作对齐
    golden: "pop.mp3", // 金句：干脆一点，收尾有落点
    keywordEnter: "click_1.mp3", // 关键词逐个入场：高频轻点
    bigNumber: "notification_1.mp3", // 大数字：需要一点存在感
    banner: "interface_1.mp3", // 横幅/结论条：承接章节音
  },
};

/** 取某触发事件的音效 src（被禁用则返回 null → 静音）
 *
 *★ 返回的是 **data URI**（从 data/sfxData.ts 取），不是 staticFile 路径。
 *  原因：长片渲染时 `<Audio src={staticFile(...)}>` 会走 HTTP 取文件，
 *  实测两次都精确崩在第 8355 帧的 "Could not play audio ... MediaError"，
 *  而 Remotion 把音频 onError 硬编码成 cancelRender() → 整片报废、无法容错。
 *  内联 data URI 后 src 不经过任何文件 I/O，从源头消除该故障。
 */
export const sfxFile = (t: SfxTrigger): string | null => {
  const f = SFX_CONFIG.map[t];
  if (!f || !SFX_CONFIG.enabled.includes(f)) return null;
  return SFX_DATA[f] ?? null;
};
