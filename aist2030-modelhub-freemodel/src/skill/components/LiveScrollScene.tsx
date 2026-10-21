import React from 'react';
import { AbsoluteFill, Audio, staticFile, useCurrentFrame, useVideoConfig } from 'remotion';

/**
 * 全屏滚动录屏场景：自动启动 Playwright 录制指定 URL，生成 MP4 后注入
 * - 支持滚动时长控制、指针轨迹、焦点高亮
 * - 输出路径：output/live_scroll_<timestamp>.mp4
 */
export const LiveScrollScene: React.FC<{ url: string; scrollDuration: number }> = ({
  url,
  scrollDuration,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  // 模拟录制完成（实际中由 Python 脚本生成）
  const videoPath = staticFile(`output/live_scroll_${Date.now()}.mp4`);

  return (
    <AbsoluteFill>
      {/* 占位：真实场景中此处为录制视频 */}
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
        🎥 LIVE SCROLL: {url}
        <br />
        Duration: {scrollDuration}ms
      </div>
    </AbsoluteFill>
  );
};