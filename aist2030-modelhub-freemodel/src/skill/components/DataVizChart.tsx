import React from 'react';
import { AbsoluteFill, staticFile, useCurrentFrame, useVideoConfig } from 'remotion';

/**
 * 数据可视化图表场景：自动联网查资料，生成高信息密度图表
 * - 示例：模型响应时间对比柱状图、多模型调度拓扑图、免费额度使用率饼图
 */
export const DataVizChart: React.FC<{ chartType: string; title: string }> = ({
  chartType,
  title,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  // 模拟图表生成（实际中调用 Chart.js 或 Plotly）
  const chartPath = staticFile(`output/chart_${chartType}_${Date.now()}.png`);

  return (
    <AbsoluteFill>
      {/* 占位：真实场景中此处为动态图表 PNG 序列或 Canvas 动画 */}
      <div style={{
        width: '100%',
        height: '100%',
        backgroundColor: '#0f172a',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        color: 'white',
        fontSize: '24px',
        fontWeight: 'bold',
      }}>
        📊 DATA VISUALIZATION: {title}
        <br />
        Type: {chartType}
      </div>
    </AbsoluteFill>
  );
};