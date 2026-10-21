import React from 'react';
import { AbsoluteFill, Sequence, staticFile, useCurrentFrame, useVideoConfig } from 'remotion';
import { renderPipeline } from './skill/core/render_pipeline';

// 旧版入口（保留兼容）
import { SchedulerFlow } from './skill/components/SchedulerFlow';
import { ZoomLens } from './skill/components/ZoomLens';
import { SelectorPip } from './skill/components/SelectorPip';
import { LiveScrollScene } from './skill/components/LiveScrollScene';
import { DataVizChart } from './skill/components/DataVizChart';

// 新版智能入口
export const Root: React.FC<{ input?: string }> = ({ input = 'AIST2030免费模型响应快、多模型自动调度、零成本使用' }) => {
  // ✅ 调用智能渲染管道
  const config = renderPipeline(input);

  return (
    <AbsoluteFill>
      {/* 示例：动态注入策略组件（实际中由 render_pipeline 返回的 scenes 数组驱动） */}
      <Sequence from={0} durationInFrames={90}>
        <SchedulerFlow bubbleCount={7} />
      </Sequence>
      <Sequence from={90} durationInFrames={96}>
        <ZoomLens targetElement="input-box" zoomLevel={2.5} />
      </Sequence>
      <Sequence from={186} durationInFrames={120}>
        <DataVizChart chartType="bar" title="AIST2030 免费模型响应时间对比" />
      </Sequence>
      <Sequence from={306} durationInFrames={240}>
        <LiveScrollScene url="http://127.0.0.1:49952/static-html/60c11cdf257ce145/control-panel.html" scrollDuration={6000} />
      </Sequence>
    </AbsoluteFill>
  );
};

// 导出供 Remotion CLI 使用
export const compositions = [
  {
    id: 'WeiXinXiaoWei',
    component: Root,
    defaultProps: {
      input: 'AIST2030免费模型响应快、多模型自动调度、零成本使用'
    },
    durationInFrames: 540,
    fps: 30,
    width: 1080,
    height: 1920,
  },
];