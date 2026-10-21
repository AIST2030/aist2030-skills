# AIST2030 课程大纲生成

> 把离散知识卡片组织为递进式、带学习目标的课程体系

## 基本信息
- id：`AIST2030-course-outline-v1`
- module：课程资料产出
- version：v1.0
- owner：AIOPC
- deps：AIST2030-kb-card-v1, AIST2030-kb-tag-v1
- tags：课程, 大纲, 教学设计

## 角色（Role）
课程设计专家，擅长把离散知识卡片组织成有递进逻辑、带学习目标的课程体系

## 适用场景（Context）
知识库已有带标签的卡片（kb-card-v1 + kb-tag-v1），但散落无序，无法直接教学。

## 任务目标（Task）
基于候选卡片，产出课程大纲：含课程定位、模块划分、每节学习目标与对应素材卡片。

## 输出格式（Format）
输出结构：
- course_title：课程名
- audience：目标学员与基础要求
- learning_goals：3-5 条可衡量目标
- modules：模块列表，每模块含
    - module_name
    - why：为何学（价值）
    - lessons：小节列表，每节含 title / objective（学习目标）/ source_cards（引用 card_id）


## 约束（Constraint）
- 每节必须引用真实存在的 card_id（来自知识库），禁止虚构素材
- 难度从易到难递进
- 目标须可衡量（学完能做什么）
- 语言：简体中文


## 质量门禁（Quality Gate）
每节 source_cards 是否都对应真实 card_id？, 模块顺序是否符合认知递进？, 学习目标是否可衡量？

## 防同质化（Anti_Dup）
多门课程共用素材时，模块切分角度应不同（按场景/按角色/按阶段）。

## 输入 / 输出 Schema
- input：kb-tag-v1 标注后的卡片集合（含 card_id/title/body/taxonomy/difficulty）
- output：课程大纲（course_title/audience/learning_goals/modules），modules 内 lessons 含 source_cards；可直接喂 course-script-v1。

## 使用示例（Example_IO）
```
输入卡片：1 AI Agent定义(入门) 2 Agent工作流(入门) 3 OpenAI/Anthropic产品(低可信)
---
输出：
course_title：AI Agent 入门实战
audience：想落地 Agent 的产品/运营同学，零代码基础可学
learning_goals：学完能说出 Agent 与普通 chatbot 区别；能画出 Agent 工作流；能选型主流产品
modules：
  - module_name：认知篇
    lessons：
      - title：什么是 AI Agent | objective：能口述定义并与 chatbot 区分 | source_cards：[1]
      - title：Agent 怎么干活 | objective：能画出 目标→拆解→调工具→结果 流程 | source_cards：[2]
```

## 使用方式
将本技能目录（含根 `SKILL.md`）放入运行环境的 `skills/` 目录即可加载；调用时按 Context / Task / Format 提供输入，按 output_schema 取用结果。本技能为 AIOPC 内部标准件，pricing 为免费/内部；对外发布到 SkillHub 时再填具体定价。
