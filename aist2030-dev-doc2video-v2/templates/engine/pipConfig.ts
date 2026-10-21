// 画中画（PiP）配置：由用户提供真人/讲解员视频，常驻角落。
// enabled=false 时完全不渲染（也不会去加载文件，避免缺文件报错）。
// 用户放入文件后，把 enabled 改为 true 即可。
export const PIP = {
  enabled: false,
  /** 相对 remotion/public 的路径；请放入用户自己的真人讲解视频（竖版最佳） */
  file: "pip/pip.mp4",
  /** 角标位置：bottomRight / bottomLeft */
  position: "bottomRight" as "bottomRight" | "bottomLeft",
  /** 尺寸（px，1080×1440 画布） */
  size: 300,
  /** 上边距避让字幕（字幕在 1258 起） */
  bottomGap: 150,
  /** 轻微边距 */
  margin: 48,
};
