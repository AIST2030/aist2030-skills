import { parse } from 'node-html-parser';

/**
 * 智能内容分析器：从任意输入（文案/HTML/截图路径）中提取结构化语义
 * - 识别核心实体（模型名、URL、痛点词、数字指标）
 * - 判定输入类型（纯文案 / 含截图 / 含 URL / 含 PDF/docx）
 * - 提取可视觉化的关键断言（如 "响应快" → ZoomLens；"多模型调度" → SchedulerFlow）
 */
export class ContentAnalyzer {
  static async analyze(input: string): Promise<ContentAnalysis> {
    // Step 1: 检测是否为本地文件路径（含 .png/.jpg/.html/.pdf/.docx）
    if (input.match(/\.(png|jpg|jpeg|gif|bmp|html|htm|pdf|docx|pptx)$/i)) {
      const ext = input.split('.').pop()?.toLowerCase() || '';
      if (['png', 'jpg', 'jpeg', 'gif', 'bmp'].includes(ext)) {
        return { type: 'screenshot', screenshotPath: input, entities: [] };
      }
      if (['html', 'htm'].includes(ext)) {
        try {
          const html = await Bun.file(input).text();
          const root = parse(html);
          const title = root.querySelector('title')?.innerText || '未命名页面';
          return { 
            type: 'html_page', 
            url: input, 
            title,
            entities: [title] 
          };
        } catch (e) {
          return { type: 'plain_text', text: input, entities: [] };
        }
      }
      if (['pdf', 'docx', 'pptx'].includes(ext)) {
        return { type: 'document', path: input, entities: [] };
      }
    }

    // Step 2: 检测是否为 URL（支持 http/https）
    if (input.match(/^https?:\/\//)) {
      return { type: 'url', url: input, entities: [input] };
    }

    // Step 3: 纯文本分析（关键词 + 断言提取）
    const entities: string[] = [];
    const assertions: string[] = [];

    // 常见模型能力关键词
    const modelKeywords = ['响应快', '低延迟', '秒级', '毫秒级', '实时', '流畅', '不卡顿'];
    const schedulerKeywords = ['调度', '自动切换', '多模型', '负载均衡', '优先级', 'fallback', '赛马'];
    const securityKeywords = ['安全', '私有', '本地', '不上传', '端到端加密'];
    const costKeywords = ['免费', '零成本', '免密钥', '免积分', '无订阅'];

    modelKeywords.forEach(k => {
      if (input.includes(k)) {
        entities.push(k);
        assertions.push(`突出${k}体验`);
      }
    });

    schedulerKeywords.forEach(k => {
      if (input.includes(k)) {
        entities.push(k);
        assertions.push(`可视化${k}机制`);
      }
    });

    securityKeywords.forEach(k => {
      if (input.includes(k)) {
        entities.push(k);
        assertions.push(`强调${k}保障`);
      }
    });

    costKeywords.forEach(k => {
      if (input.includes(k)) {
        entities.push(k);
        assertions.push(`强化${k}价值`);
      }
    });

    // 检测数字指标（如 "429ms", "<500ms", "200RPM"）
    const numberMetrics = input.match(/\d+(?:\.\d+)?\s*(?:ms|ms|ms|RPM|次\/天|次\/分钟)/g) || [];
    numberMetrics.forEach(m => entities.push(m));

    return {
      type: 'plain_text',
      text: input,
      entities,
      assertions
    };
  }
}

type ContentAnalysis = 
  | { type: 'plain_text'; text: string; entities: string[]; assertions: string[] }
  | { type: 'screenshot'; screenshotPath: string; entities: string[] }
  | { type: 'html_page'; url: string; title: string; entities: string[] }
  | { type: 'url'; url: string; entities: string[] }
  | { type: 'document'; path: string; entities: string[] };