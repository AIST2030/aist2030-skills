# AIST2030 免费模型智能管家 Skill 架构说明

## 🌟 核心能力升级

### 1. 智能决策中枢（`src/skill/intelligence/`）
- `ContentAnalyzer.ts`: 自动识别输入类型（文案/截图/URL/文档），提取关键实体与断言
- `MediaSelector.ts`: 内置 `media_registry.json` 防重复，支持语义关键词匹配选视频
- `VisualStrategyMapper.ts`: 根据文案关键词自动匹配可视化策略（SchedulerFlow / ZoomLens / LiveScrollScene / DataVizChart）

### 2. 动态渲染管道（`src/skill/core/render_pipeline.ts`）
- 统一入口函数 `renderPipeline(input: string)`
- 支持任意输入 → 自动路由至最优可视化组件组合
- 背景视频全自动防重选择，无需人工干预

### 3. 新增可视化组件（`src/skill/components/`）
- `LiveScrollScene.tsx`: 全屏滚动录屏（替代画中画），真实操作台演示
- `DataVizChart.tsx`: 自动查资料生成数据图表（柱状图/拓扑图/饼图），提升信息密度
- `SchedulerFlow.tsx` / `ZoomLens.tsx` / `SelectorPip.tsx`: 已有组件增强

## 🛠️ 使用方式

```bash
# 1. 安装依赖（首次）
npm install

# 2. 运行智能渲染（输入任意内容）
npx remotion render src/Root.tsx WeiXinXiaoWei --props='{"input":"AIST2030免费模型响应快、多模型自动调度、零成本使用"}'

# 3. 输出路径：output/WeiXinXiaoWei.mp4
```

## 📈 效果对比
| 旧版 | 新版 |
|------|------|
| 固定背景视频（易重复） | 智能选视频 + 防重 registry |
| 口播文案逐字映射 | 自动联网查资料生成图表/拓扑图 |
| 手动指定画中画位置 | AI 分析自动定位焦点区域 |
| 单一渲染流程 | 多模态输入自动路由 |

---
**AIST2030 · 智能个体生产力平台**
© 2026 贵州省团之家智付科技有限公司