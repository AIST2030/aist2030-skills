# 音效试听勾选 · 自定义素材 · 画中画（v2 三项新增能力）

> 三项能力**互相独立、任意组合，缺省都不启用**。启用任一项都不会打断主流程。

---

## A. 音效试听勾选闭环

### 为什么做成"试听页"而不是让 AI 直接选
音效是**审美判断**，不能由 AI 代替用户决定。所以流程设计成：
AI 抓一批 → 生成离线试听页 → **用户勾选** → AI 回写配置。

### 跑法

```bash
# A1 抓音效（Mixkit 分类页；每类抓 2 个）
python scripts/fetch_sfx.py --out <项目>/remotion/public/sfx
# 可指定分类：--cats whoosh,click,pop,interface,notification,sci-tech

# A2 生成自包含试听页（音效 base64 内嵌，离线可播，374KB 左右）
python scripts/build_sfx_audition.py \
  --sfx-dir <项目>/remotion/public/sfx \
  --out <项目>/output/sfx_audition.html
```

或走编排入口：`python scripts/pipeline.py --project <项目根> --stage sfx`

### 你（AI）要做的三步

1. 用 `present_files` 把 `sfx_audition.html` 展示给用户。
2. 让用户试听 → 勾选 → 点「导出选择」，得到：
   ```json
   {"enabled":["click_1.mp3","interface_1.mp3","notification_1.mp3","pop.mp3"]}
   ```
3. 回写 `<项目>/remotion/src/sfxConfig.ts` 的 `enabled` 数组。

### sfxConfig.ts 结构

```ts
export const SFX_CONFIG = {
  enabled: ["click_1.mp3", "interface_1.mp3"],   // ← 用户勾选的池子
  map: {
    cover:        "notification_1.mp3",  // 封面
    section:      "interface_1.mp3",     // 章节切换
    golden:       "pop.mp3",             // 金句
    keywordEnter: "click_1.mp3",         // 关键词入场
    bigNumber:    "notification_1.mp3",  // 大数字
    banner:       "interface_1.mp3",     // 结论条
  },
};
```

**规则**：`sfxFile(trigger)` 只在 `map[trigger]` 命中 `enabled` 时返回文件名，
否则返回 `null` → 该触发点静音。**尊重用户勾选，不要擅自启用未勾选的音效。**

### 分配音色的经验（本项目实证）
- 4 个短促 UI 音（click/pop/interface/notification）适合**逐字跟读解说**，
  不压旁白。
- whoosh / sparkle / magic / impact 这类"过场大音效"在解说视频里容易盖过人声，
  用户实测只留了 4 个短音。**同类视频建议同样从短音起步。**

---

## B. 用户自定义素材通道

### 用法

用户把实拍素材放进 `<项目>/remotion/public/custom_media/`：

| 命名 | 作用范围 |
|---|---|
| `p{n}.mp4` | 替换第 n 页整页素材（一页一镜结构下最常用） |
| `{shot}.mp4` | 替换单个镜头（多镜头结构） |

然后：

```bash
python scripts/fetch_media.py --plan shotplan.json \
  --out <项目>/remotion/public/media \
  --custom <项目>/remotion/public/custom_media
```

命中的走**用户素材、不联网**；未命中的仍走 Mixkit → 天然支持混合。

走编排入口：`python scripts/pipeline.py --project <项目根> --stage media --custom <目录>`

### 注意
- 自定义素材同样会被 ffmpeg 统一转码（1080×1440 / 静音 / 调色 / 柔化），
  **直接丢任意分辨率的原始视频即可**，不必自己预处理。
- 素材清单 `media_manifest.json` 里 `source: "custom:..."` 的即为用户素材。

---

## C. 画中画 PiP

### 可行性结论：完全可行
Remotion 用 `<Video>` 就能嵌，无需任何外部工具。

### 用法

1. 用户把讲解视频放 `<项目>/remotion/public/pip/pip.mp4`。
2. 改 `<项目>/remotion/src/pipConfig.ts`：
   ```ts
   export const PIP = {
     enabled: true,          // ← 翻开关
     file: "pip/pip.mp4",
     position: "bottomRight",// bottomRight / bottomLeft / topRight / topLeft
     size: 300,              // 卡片宽度 px
     bottomGap: 150,         // 距底部 px（避让字幕区，字幕在 1258+）
     margin: 48,
   };
   ```
3. 重新渲染即可。`PipOverlay` 已在 `MediaScene` 内挂载，**无需改 Root.tsx**。

### 行为
- 圆角卡片 + 主色描边 + 进场缩放动画（20 帧 0.82→1）。
- **静音循环**（不与人声/音效冲突）。
- 位置在**右下角、且bottomGap 已避开底部字幕**，不会压字。

---

## 三项能力的编排入口速查

```bash
# 主流程（不含音效、不含分镜——分镜必须 AI 亲自做）
python scripts/pipeline.py --project <项目> --script script.txt --stage all

# 混入用户自定义素材
python scripts/pipeline.py --project <项目> --stage media --custom <项目>/remotion/public/custom_media

# 音效试听闭环
python scripts/pipeline.py --project <项目> --stage sfx

# 自动闸门（triggerWord 校验）
python scripts/pipeline.py --project <项目> --stage gates

# 整片渲染（必须显式 --yes）
python scripts/pipeline.py --project <项目> --stage render --yes
```