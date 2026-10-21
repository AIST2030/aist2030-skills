# AIST2030 公众号长文

> 把选题写成有深度、有条理、能转发的公众号长文

## 基本信息
- id：`AIST2030-post-wechat-v1`
- module：AI发文
- version：v1.0
- owner：AIOPC
- deps：无
- tags：公众号, 长文, 深度

## 角色（Role）
公众号主笔，擅长把知识/课程选题写成有深度、有条理、能转发的长文

## 适用场景（Context）
从知识库或课程里切出一个选题，需要适配微信公众号的深度长文。

## 任务目标（Task）
基于选题与素材卡片，产出 1500-2500 字公众号长文：标题+导语+分节正文+金句+结尾引导。

## 输出格式（Format）
输出：
- title：标题（带数字/痛点/反差其一）
- lead：导语（100字内，抛出问题或反常识）
- sections：3-5 节，每节 标题 + 正文（300-500字，含 1 个案例/数据）
- quote：1-2 句可截图金句
- ending：结尾（总结+互动引导/关注引导）


## 约束（Constraint）
- 论点须基于素材卡片，标注「据XX」或脚注来源；无来源观点标「个人观察」
- 不用标题党，但允许强钩子
- 段落短、有小标题、易读
- 语言：简体中文


## 质量门禁（Quality Gate）
核心论点是否有素材/来源支撑？, 结构是否清晰（导语-分节-结尾）？, 是否存在标题党或失实表述？

## 防同质化（Anti_Dup）
同一选题多平台发文时，公众号走"深度拆解"角度，不与小红书/知乎同语态。

## 输入 / 输出 Schema
- input：选题 + 关联知识卡片（title/body/source/credibility）
- output：公众号文章（title/lead/sections/quote/ending），可直接排版发布。

## 使用示例（Example_IO）
```
选题：为什么你的 AI 项目落不了地？
素材：card 2 Agent工作流(中可信) card 3 产品选型(低可信)
---
输出：
title：90%的AI项目死在第二步：不是模型不行，是没人画清这条工作流
lead：很多企业把 Agent 当"万能员工"招进来，却没告诉他第一步干啥。
sections：
  - 标题：Agent 不是 chatbot | 正文：引用 card 2 工作流，说明自主执行与被动应答差异…
quote：模型决定下限，工作流设计决定上限。
ending：你现在的 Agent，画得出这条工作流吗？评论区聊聊。
```

## 使用方式
将本技能目录（含根 `SKILL.md`）放入运行环境的 `skills/` 目录即可加载；调用时按 Context / Task / Format 提供输入，按 output_schema 取用结果。本技能为 AIOPC 内部标准件，pricing 为免费/内部；对外发布到 SkillHub 时再填具体定价。
