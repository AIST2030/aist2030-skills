/*
 * 问题类型分类引擎
 * 根据用户提问内容自动识别问题类型，并推荐最匹配的模型
 *
 * ★ 2026-10-21 重要修订（配合网关 auto 路由修复）：
 *   1) 这里返回的 model 只是"偏好提示"，网关据此给渠道排序 + 选上游模型，
 *      不再像旧版那样把请求的 model 整个替换掉（旧版会让候选集塌缩成 1 家，
 *      该渠道一旦欠费就报"全部渠道失败"）。
 *   2) 旧版几乎所有类型都指向 qwen-plus / qwen-long，但这两个模型只挂在
 *      已欠费的阿里云百炼渠道上。
 *   3) ★ 2026-10-21 11:30 全渠道体检后再次修订：deepseek-chat 余额耗尽（402），
 *      业务类改指 LongCat-2.0。
 *
 * ★ 铁律：这里指派的模型必须挂在【当前实测可用】的渠道上。
 *   已确认可用（2026-10-21 11:30 实测）：
 *     硅基 THUDM/GLM-4-9B-0414  0.3s  综合最快
 *     硅基 Qwen/Qwen2.5-7B-Instruct  0.25s  代码强
 *     智谱 glm-4-flash  0.5~1.5s  中文通用
 *     智谱 glm-4v-flash  0.5s  视觉
 *     美团 LongCat-2.0  1.2~2s  长文本
 *     美团 LongCat-2.5-Preview  2~6s  推理
 */

function classifyQuestion(text) {
  // 清理文本
  const cleanText = text.toLowerCase().replace(/[^a-z0-9\u4e00-\u9fa5\s]/g, '');
  
  // 技术类问题：编程、代码、API、开发、调试、错误
  if (/\b(编程|代码|code|api|开发|debug|调试|错误|bug|exception|error|语法|编译|运行|部署|git|docker|node|python|javascript|java|c\+\+|rust|go|php|sql|数据库|mysql|postgresql|redis|mongodb|前端|后端|全栈|框架|vue|react|angular|spring|django|flask)\b/.test(cleanText)) {
    return { type: 'technical', model: 'Qwen/Qwen2.5-7B-Instruct', reason: '技术问题需要精准的代码理解能力，硅基 Qwen2.5-7B 实测 0.50s 且代码能力强' };
  }
  
  // 业务咨询类：公司、产品、市场、销售、客户、运营、管理
  // ★ 2026-10-21 再修：原指 deepseek-chat，但该账号 402 余额已耗尽（实测）。
  //   改指 LongCat-2.0（美团，12.5 万字超长上下文，业务长文分析最合适，实测可用 1.2~2s）。
  if (/\b(公司|产品|市场|销售|客户|运营|管理|商业|盈利|成本|收入|财务|合同|法律|政策|合规|政府|监管|行业|竞争|分析|策略|规划|目标|kpi|okr)\b/.test(cleanText)) {
    return { type: 'business', model: 'LongCat-2.0', reason: '业务咨询需要长文本分析与战略思维，美团 LongCat-2.0 实测 1.2s 且支持 12.5 万字长上下文' };
  }
  
  // 创意写作类：写作、文章、文案、诗歌、故事、小说、剧本、广告、营销、创意
  if (/\b(写作|文章|文案|诗歌|故事|小说|剧本|广告|营销|创意|设计|品牌|宣传|推广|标题|摘要|总结|报告|邮件|信件|公文|演讲|发言|口号|标语)\b/.test(cleanText)) {
    return { type: 'creative', model: 'glm-4-flash', reason: '创意写作需要中文语言表现力，智谱 glm-4-flash 实测 0.61s 可用' };
  }
  
  // 数据分析类：数据、统计、分析、图表、excel、表格、数字、量化、指标、报表
  if (/\b(数据|统计|分析|图表|excel|表格|数字|量化|指标|报表|可视化|bi|powerbi|tableau|spss|python|pandas|numpy|matlab)\b/.test(cleanText)) {
    return { type: 'data', model: 'THUDM/GLM-4-9B-0414', reason: '数据分析需要准确的数学与逻辑推理，硅基 GLM-4-9B 实测 0.28s 响应最快' };
  }
  
  // 日常对话类：通用问题、简单问答、常识、聊天
  if (text.length < 50 && !/\?$/i.test(text)) {
    return { type: 'casual', model: 'glm-4-flash', reason: '简短对话需要快速响应，智谱 glm-4-flash 实测 0.61s 可用' };
  }
  
  // 默认：通用最佳平衡
  return { type: 'general', model: 'THUDM/GLM-4-9B-0414', reason: '综合性能最优，硅基 GLM-4-9B 实测 0.28s 是当前最快可用渠道' };
}

// 导出函数供网关使用
module.exports = { classifyQuestion };
