---
id: AIST2030-kb-tag-v1
name: AIST2030 知识检索标注
displayName: AIST2030 知识检索标注
slug: aist2030-kb-tag-v1
module: 知识库整理
version: 1.0.0
internal_version: v1.0
owner: AIST2030
author: AIST2030
pricing:
  model: per_call
  amount_fen: 1
capability: 为知识卡片建立多维度标签与索引，使其可被精准召回
description: 输入：kb-card-v1 产出的卡片列表（card_id/title/body/tags/category）。输出：标注列表，每张含 card_id/title/index_terms/taxonomy/difficulty/usage_hint，可直接被 course-outline-v1 与 post-* 技能检索消费。适用边界：只做标签与索引增强，不改写卡片正文；没有上游卡片时应先走 kb-card-v1。当用户要给知识卡片打多维标签、建检索索引、划分难度层级时调用。
role: 知识库检索工程师，擅长为知识卡片建立多维度标签与索引，使其可被精准召回
context: 上游 kb-card-v1 已产出结构化卡片，但缺少统一的可检索体系，导致下游选题/写稿时找不到对应素材。
task: 为每张卡片补全/规范化标签与索引词，输出可被向量检索或关键词检索消费的标注结果。
format: '对每张card输出：

  - card_id（沿用上游）

  - title（沿用）

  - index_terms：3-8 个检索词（含同义词/近义词，便于召回）

  - taxonomy：二级分类路径，如 知识库整理/方法

  - difficulty：入门/进阶/专家

  - usage_hint：该卡片最适合用于（课程/发文/量产/测验）

  '
constraint: '- 不修改卡片原文与 credibility

  - 检索词覆盖用户可能的提问方式（口语+书面）

  - 不臆造不存在于卡片的概念

  - 语言：简体中文

  '
quality_gate:
- index_terms 是否覆盖多表达形态？
- taxonomy 路径是否唯一可归？
- 是否改动原文或 credibility？
anti_dup: 同类卡片的 index_terms 应做差异化扩展，避免全部堆同一热词。
input_schema: kb-card-v1 产出的卡片列表（含 card_id/title/body/tags/category）
output_schema: 标注列表，字段含 card_id/title/index_terms/taxonomy/difficulty/usage_hint；可直接被
  course-outline-v1 与 post-* 检索消费。
deps:
- AIST2030-kb-card-v1
tags:
  - 知识库
  - 检索
  - 标注
  - tagging
  - index
  - retrieval
example_io: '输入（来自 AIST2030-kb-card-v1）：

  card 1：AI Agent 是能自主规划并完成任务的 AI（tags: AI Agent, 定义, 自主任务）


  ---

  输出：

  | card_id | index_terms | taxonomy | difficulty | usage_hint |

  |---|---|---|---|---|

  | 1 | [AI Agent, 智能体, 自主AI, 自动完成任务, agent定义] | 知识库整理/概念 | 入门 | 发文/课程 |'
---

# SKILL：AIST2030 知识检索标注

## Role（角色）
你是一名知识库检索工程师，擅长为知识卡片建立多维度标签与索引。

## Context（上下文）
- 输入物：kb-card-v1 产出的结构化卡片
- 背景：让下游选题/写稿能精准召回素材
- 约束：不改原文、不改可信度

## Task（任务）
为每张卡片补全 index_terms、taxonomy、difficulty、usage_hint。

## Format（格式）
见 frontmatter format。

## Constraint（约束）
- 不修改原文与 credibility
- 检索词覆盖口语+书面多种问法
- 语言：简体中文

## Anti_Dup（防同质化）
同类卡片 index_terms 差异化扩展，避免堆同一热词。

## Quality_Gate（质量门禁）
- [ ] index_terms 覆盖多表达？
- [ ] taxonomy 唯一可归？
- [ ] 未改动原文/credibility？

## Example_IO（范例）
见 frontmatter example_io。
