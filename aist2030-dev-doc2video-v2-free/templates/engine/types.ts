/** 时间轴数据类型（由 scripts/gen_narration.py 生成） */

export interface Word {
  /** 相对本 shot 起始的秒数 */
  t: number;
  /** 单词持续秒数 */
  d: number;
  /** 词文本 */
  w: string;
  /** 该词首字在 shot.clean（去标点空白文本）中的字符索引，-1 表示未能对齐 */
  ci: number;
}

export interface Shot {
  id: string;
  /** 本句讲稿文本 */
  text: string;
  /** 去空白与标点后的文本，用于按字符定位触发点 */
  clean: string;
  /** 音频文件（public 下相对路径） */
  audioFile: string;
  /** 相对页起始的秒数 */
  start: number;
  startFrame: number;
  /** 音频净时长 */
  audioDur: number;
  /** 本 shot 占屏时长（含句间呼吸停顿） */
  duration: number;
  durationFrames: number;
  words: Word[];
}

export interface PageData {
  id: string;
  /** 场景组件 key */
  scene: string;
  /** 页标题（调试用） */
  title: string;
  start: number;
  startFrame: number;
  duration: number;
  durationFrames: number;
  shots: Shot[];
}

export interface Timeline {
  fps: number;
  width: number;
  height: number;
  totalSeconds: number;
  totalFrames: number;
  bgm: string;
  pages: PageData[];
}
