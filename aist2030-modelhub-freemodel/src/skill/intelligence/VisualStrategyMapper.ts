import { ContentAnalysis } from './ContentAnalyzer';

/**
 * 可视化策略映射器：根据内容分析结果，匹配最优可视化组件
 * - 纯文案 → 自动查资料生成 DataVizChart / SchedulerFlow
 * - 含截图 → SelectorPip（放大镜）或 ZoomLens
 * - 含 URL → LiveScrollScene（全屏滚动录屏）
 * - 含 HTML 页面 → SchedulerFlow + LiveScrollScene 混合
 */
export class VisualStrategyMapper {
  static map(analysis: ContentAnalysis): VisualStrategy[] {
    const strategies: VisualStrategy[] = [];

    switch (analysis.type) {
      case 'plain_text':
        // 文案含“调度”、“多模型” → 启用 SchedulerFlow
        if (analysis.assertions.some(a => a.includes('调度') || a.includes('多模型'))) {
          strategies.push({
            type: 'schedulerFlow',
            duration: 4.5,
            position: 'p1',
            config: { bubbleCount: 7 }
          });
        }

        // 文案含“响应快”、“低延迟” → 启用 ZoomLens
        if (analysis.assertions.some(a => a.includes('响应快') || a.includes('低延迟'))) {
          strategies.push({
            type: 'zoomLens',
            duration: 3.2,
            position: 'p3',
            config: { targetElement: 'input-box', zoomLevel: 2.5 }
          });
        }

        // 默认启用 DataVizChart（自动联网查模型对比数据）
        strategies.push({
          type: 'dataVizChart',
          duration: 5.0,
          position: 'p4',
          config: { chartType: 'bar', title: 'AIST2030 免费模型响应时间对比' }
        });
        break;

      case 'screenshot':
        strategies.push({
          type: 'selectorPip',
          duration: 4.0,
          position: 'p6',
          config: { screenshotPath: analysis.screenshotPath, x: 118, y: 358, width: 322, height: 32 }
        });
        break;

      case 'url':
      case 'html_page':
        strategies.push({
          type: 'liveScrollScene',
          duration: 8.0,
          position: 'p4',
          config: { url: analysis.url || analysis.path, scrollDuration: 6000 }
        });
        break;

      case 'document':
        strategies.push({
          type: 'dataVizChart',
          duration: 5.0,
          position: 'p2',
          config: { chartType: 'pie', title: '文档关键信息分布' }
        });
        break;
    }

    return strategies;
  }
}

type VisualStrategy = 
  | { type: 'schedulerFlow'; duration: number; position: string; config: { bubbleCount: number } }
  | { type: 'zoomLens'; duration: number; position: string; config: { targetElement: string; zoomLevel: number } }
  | { type: 'selectorPip'; duration: number; position: string; config: { screenshotPath: string; x: number; y: number; width: number; height: number } }
  | { type: 'liveScrollScene'; duration: number; position: string; config: { url: string; scrollDuration: number } }
  | { type: 'dataVizChart'; duration: number; position: string; config: { chartType: string; title: string } };