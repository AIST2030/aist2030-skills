# AIST2030 课程大纲生成 效果案例（case-template）

> 提供 3 个效果案例，供发布前核对与下游参考。

### 案例 1（核心场景）：AI Agent 入门课程体系

**输入**
候选卡片：1 AI Agent 定义(入门) 2 Agent 工作流(入门) 3 OpenAI/Anthropic 产品(低可信)

**预期输出要点**
- course_title：AI Agent 入门实战
- audience：想落地 Agent 的产品/运营同学，零代码基础可学
- learning_goals：学完能说出 Agent 与 chatbot 区别；能画出 Agent 工作流；能选型主流产品
- modules：认知篇 → 每节 source_cards 引用真实 card_id，难度从易到难递进

### 案例 2（行业变体）：电商运营实战课程

**输入**
候选卡片：电商客服话术拆解 / 复购提升方法 / 直播选品数据（均带 card_id 与可信度）

**预期输出要点**
- 按"方法论 → 案例 → 数据"切分模块，避免与案例 1 同角度
- 每节 objective 可衡量（如"能独立搭一套客服 SOP"）
- source_cards 全部对应真实 card_id，无虚构

### 案例 3（边界场景）：素材不足时的稳健大纲

**输入**
仅 2 张入门卡片，缺进阶素材

**预期输出要点**
- 大纲标注"进阶模块待补素材"，不臆造 card_id
- 仍保持难度递进与可衡量目标
- 输出明确提示上游先补 kb-card/kb-tag

