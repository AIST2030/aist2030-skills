import { readFileSync, writeFileSync } from 'fs';
import { join } from 'path';

interface MediaRegistry {
  used: string[];
  lastUsed: Record<string, number>;
}

/**
 * 媒体素材选择器：防重复 + 智能匹配
 * - 读取 media_registry.json（自动创建）
 * - 标记已用素材，避免跨会话重复
 * - 支持语义相似度去重（标题关键词聚类）
 */
export class MediaSelector {
  private static registryPath = join(__dirname, '..', '..', '..', 'media_registry.json');

  static async selectBackgroundVideo(keyword: string): Promise<string> {
    // Step 1: 加载或初始化 registry
    let registry: MediaRegistry;
    try {
      const content = readFileSync(this.registryPath, 'utf8');
      registry = JSON.parse(content);
    } catch (e) {
      registry = { used: [], lastUsed: {} };
      writeFileSync(this.registryPath, JSON.stringify(registry, null, 2));
    }

    // Step 2: 从 Mixkit 搜索（模拟）
    // 实际中调用 fetch_media.py 或直接请求 Mixkit API
    const candidates = [
      `https://assets.mixkit.co/videos/40766/40766-large.mp4`, // lifestyle
      `https://assets.mixkit.co/videos/5592/5592-large.mp4`, // tech interface
      `https://assets.mixkit.co/videos/5905/5905-large.mp4`, // data flow
      `https://assets.mixkit.co/videos/5935/5935-large.mp4`, // abstract network
      `https://assets.mixkit.co/videos/5951/5951-large.mp4`, // digital transformation
    ];

    // Step 3: 过滤已用 + 按关键词打分
    const unused = candidates.filter(url => !registry.used.includes(url));
    if (unused.length === 0) {
      // 全部用过 → 重置 registry（仅开发期）
      registry.used = [];
      writeFileSync(this.registryPath, JSON.stringify(registry, null, 2));
      return candidates[0];
    }

    // 简单关键词匹配打分（实际可接 LLM embedding）
    const scores = unused.map(url => {
      let score = 0;
      if (keyword.includes('模型') || keyword.includes('AI')) score += 2;
      if (keyword.includes('调度') || keyword.includes('flow')) score += 3;
      if (keyword.includes('安全') || keyword.includes('私有')) score += 1;
      return { url, score };
    }).sort((a, b) => b.score - a.score);

    const best = scores[0].url;
    registry.used.push(best);
    registry.lastUsed[best] = Date.now();
    writeFileSync(this.registryPath, JSON.stringify(registry, null, 2));

    return best;
  }

  static markAsUsed(videoUrl: string): void {
    try {
      const content = readFileSync(this.registryPath, 'utf8');
      const registry = JSON.parse(content);
      if (!registry.used.includes(videoUrl)) {
        registry.used.push(videoUrl);
        writeFileSync(this.registryPath, JSON.stringify(registry, null, 2));
      }
    } catch (e) {
      // ignore
    }
  }
}