# AIST2030 知识检索标注 效果案例（case-template）

> 提供 3 个效果案例，供发布前核对与下游参考。

### 案例 1（核心场景）：给知识卡片建检索标注

**输入**
card 1：AI Agent 是能自主规划并完成任务的 AI（tags: AI Agent, 定义, 自主任务）

**预期输出要点**
- index_terms：3-8 个检索词（AI Agent / 智能体 / 自主AI / 自动完成任务 / agent定义）
- taxonomy：知识库整理/概念
- difficulty：入门
- usage_hint：发文/课程

### 案例 2（行业变体）：同类卡片差异化扩展

**输入**
一批"方法类"卡片（工作流、提示词、复盘）

**预期输出要点**
- 每张 index_terms 做差异化扩展，避免全部堆"AI"同一热词
- taxonomy 路径唯一可归
- 不改动上游原文与 credibility

### 案例 3（边界场景）：低可信卡片谨慎标注

**输入**
credibility=低 的产品对比卡片

**预期输出要点**
- index_terms 仍覆盖口语+书面多种问法
- 不臆造不存在于卡片的概念
- usage_hint 标注"引用时须提醒待核实"

