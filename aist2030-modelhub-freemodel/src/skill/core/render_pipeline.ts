import { ContentAnalyzer } from '../intelligence/ContentAnalyzer';
import { VisualStrategyMapper } from '../intelligence/VisualStrategyMapper';
import { MediaSelector } from '../intelligence/MediaSelector';
import { SchedulerFlow } from '../components/SchedulerFlow';
import { ZoomLens } from '../components/ZoomLens';
import { SelectorPip } from '../components/SelectorPip';
import { LiveScrollScene } from '../components/LiveScrollScene';
import { DataVizChart } from '../components/DataVizChart';

/**
 * 智能渲染管道：统一入口，支持任意输入类型
 * - 输入：string（文案 / URL / 路径）
 * - 输出：Remotion Composition 配置对象（含 scenes, duration, fps）
 */
export async function renderPipeline(input: string): Promise<RenderConfig> {
  console.log(`[Skill] 开始分析输入: ${input.substring(0, 50)}...`);

  // Step 1: 内容分析
  const analysis = await ContentAnalyzer.analyze(input);
  console.log(`[Skill] 分析完成 → 类型: ${analysis.type}, 实体: ${analysis.entities.join(', ')}`);

  // Step 2: 可视化策略匹配
  const strategies = VisualStrategyMapper.map(analysis);
  console.log(`[Skill] 匹配 ${strategies.length} 个可视化策略`);

  // Step 3: 媒体素材选择（背景视频）
  let backgroundVideo = '';
  if (analysis.type === 'plain_text') {
    backgroundVideo = await MediaSelector.selectBackgroundVideo(analysis.entities.join(' '));
  }
  console.log(`[Skill] 背景视频已选: ${backgroundVideo}`);

  // Step 4: 构建 Remotion Compositions
  const scenes = [];

  for (const strategy of strategies) {
    switch (strategy.type) {
      case 'schedulerFlow':
        scenes.push({
          id: `scheduler-${Date.now()}`,
          component: SchedulerFlow,
          props: strategy.config,
          durationInFrames: Math.round(strategy.duration * 30),
          fps: 30
        });
        break;
      case 'zoomLens':
        scenes.push({
          id: `zoom-${Date.now()}`,
          component: ZoomLens,
          props: strategy.config,
          durationInFrames: Math.round(strategy.duration * 30),
          fps: 30
        });
        break;
      case 'selectorPip':
        scenes.push({
          id: `pip-${Date.now()}`,
          component: SelectorPip,
          props: strategy.config,
          durationInFrames: Math.round(strategy.duration * 30),
          fps: 30
        });
        break;
      case 'liveScrollScene':
        scenes.push({
          id: `scroll-${Date.now()}`,
          component: LiveScrollScene,
          props: strategy.config,
          durationInFrames: Math.round(strategy.duration * 30),
          fps: 30
        });
        break;
      case 'dataVizChart':
        scenes.push({
          id: `chart-${Date.now()}`,
          component: DataVizChart,
          props: strategy.config,
          durationInFrames: Math.round(strategy.duration * 30),
          fps: 30
        });
        break;
    }
  }

  return {
    scenes,
    backgroundVideo,
    totalDuration: Math.max(...strategies.map(s => s.duration)) + 1.5,
    fps: 30
  };
}

type RenderConfig = {
  scenes: Array<{
    id: string;
    component: any;
    props: any;
    durationInFrames: number;
    fps: number;
  }>
  backgroundVideo: string;
  totalDuration: number;
  fps: number;
};