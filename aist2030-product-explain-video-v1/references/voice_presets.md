# 配音 / 数字人选型

## 一、配音（TTS）

| 方案 | 类型 | 优势 | 约束 | 适用 route |
|---|---|---|---|---|
| VoxCPM2 | 本地 TTS | GGUF CPU 版无显卡可跑；30 语言；Apache-2.0 商用免费 | Python 3.10–3.12 | 全本地 / 混合兜底 |
| Fish Speech | 本地 TTS | 零/少样本音色克隆；多语种 | 需逐条确认授权 | 全本地 / 混合 |
| OmniVoice | 本地 TTS | 600+ 语言声音克隆 | 需 CUDA / 镜像 | 混合 |
| 平台 TTS（Edge/千帆/腾讯云） | 云端 | 质量稳、快、免部署 | 需 Key / 按量 | 混合 / 全云端 |

**混合路线默认**：先平台 TTS；失败/不可达 → 回退 VoxCPM2（标注「本地 TTS 兜底」）。

## 二、数字人口播（仅 narrator=数字人，发布会档推荐）

| 方案 | 说明 | 许可 | 备注 |
|---|---|---|---|
| Avatar Forge | 图+声音+口播稿→完整数字人口播视频的开源 Agent Skill，带 WorkBuddy 流水线 | MIT | 本地 Agent Skill，最省心 |
| InfiniteTalk | 图+音频→无限长口播数字人 | — | 需 CUDA+flash-attn；8G 走低显存 480p |
| LiveTalking | 实时流式数字人，可直播 | — | 官方仅测 Ubuntu |

## 三、选型矩阵

| route | 配音 | 数字人 |
|---|---|---|
| 混合(默认) | 平台 TTS → 失败回退 VoxCPM2 | Avatar Forge（如需） |
| 全本地开源 | VoxCPM2 / Fish Speech | InfiniteTalk（有卡） |
| 全云端 | 平台 TTS | 平台数字人（如有） |

## 四、字幕
- TTS 同时输出 SRT；数字人方案用其自带口型对齐
- 字幕投入 adu-motion-video（subtitle-options），白字描边、安全区
