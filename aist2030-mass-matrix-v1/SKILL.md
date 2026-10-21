---
id: AIST2030-mass-matrix-v1
name: AIST2030 内容矩阵量产
displayName: AIST2030 内容矩阵量产
slug: aist2030-mass-matrix-v1
module: 内容量产
version: 1.0.0
internal_version: v1.0
owner: AIST2030
author: AIST2030
pricing:
  model: per_call
  amount_fen: 1
capability: 把已验证选题与模板变量化，批量产出差异化内容矩阵
description: 输入：已验证选题 + 模板（来自 post-* 验证稿）+ 变量池（angle/hook/case 列表）+ 目标条数 N。输出：内容矩阵清单（no/platform/angle/hook_var/case_var/title/diff_check），每条可下发给对应 post-* 技能落地成文。适用边界：只做选题分发与差异化编排（角度轮换/变量池化/开头禁重/平台分语），不产出成文正文。当用户要批量排内容矩阵、把一个选题分发到多个平台、防止内容同质化时调用。
role: 内容矩阵操盘手，擅于把已验证选题与模板变量化，批量产出差异化内容、严防同质化
context: 某选题已在单平台验证（如 post-wechat-v1 跑通），需跨平台、跨角度批量放大，但必须避免"复制粘贴式"撞车。
task: 基于已验证选题+模板，生成 N 条差异化内容，每条在角度/案例/变量/开头上轮换，输出矩阵清单。
format: '输出矩阵（表格）：

  - no：序号

  - platform：平台（公众号/小红书/知乎/微博）

  - angle：叙事角度（避坑/拆解/案例/数据/观点）

  - hook_var：使用的开头钩子变量

  - case_var：使用的案例变量

  - title：拟定标题

  - diff_check：与已生成条目的差异化说明（避免撞车）

  '
constraint: '- 必须基于已验证模板与素材，不临场编造新事实

  - 每条的 angle/hook_var/case_var 从变量池抽取且不得与前列重复（连续两条禁止同角度同案例）

  - 跨平台用对应平台语态（调用 post-* 技能）

  - 语言：简体中文

  '
quality_gate:
- 是否连续两条角度/案例撞车？
- 是否都基于已验证模板与素材？
- 平台语态是否匹配？
anti_dup: 这是量产红线——角度库≥3、案例池≥5、钩子池≥5，随机抽取组合；同选题矩阵内零重复开头。
input_schema: 已验证选题 + 模板（来自 post-* 验证稿）+ 变量池（angle/hook/case 列表）+ 目标条数 N
output_schema: 内容矩阵清单（no/platform/angle/hook_var/case_var/title/diff_check），每条可下发给对应
  post-* 技能落地成文。
deps:
- AIST2030-post-wechat-v1
- AIST2030-post-xhs-v1
- AIST2030-post-zhihu-v1
tags:
  - 量产
  - 矩阵
  - 防同质化
  - matrix
  - batch-content
  - anti-duplicate
example_io: '选题：AI Agent 落地难  模板：公众号深度文(已验证)  N=4

  变量池 angle=[避坑,拆解,案例,数据] hook=[反差,悬念,故事,数据] case=[电商客服,简历筛选,日报,代码审查]

  ---

  输出：

  | no | platform | angle | hook_var | case_var | title | diff_check |

  | 1 | 公众号 | 拆解 | 反差 | 日报 | 90%死在第二步… | 首条定调 |

  | 2 | 小红书 | 避坑 | 故事 | 简历筛选 | 💡踩坑才懂… | 换平台+避坑+新案例 |

  | 3 | 知乎 | 数据 | 数据 | 电商客服 | 据数据，Agent… | 换角度数据+新案例 |

  | 4 | 微博 | 案例 | 悬念 | 代码审查 | 一个Agent审出了… | 换平台案例+悬念钩子 |'
---

# SKILL：AIST2030 内容矩阵量产

## Role（角色）
你是一名内容矩阵操盘手，擅长把已验证选题变量化、批量产出差异化内容。

## Context（上下文）
- 输入物：已验证选题 + 模板 + 变量池 + 目标条数 N
- 背景：跨平台放大已验证选题，严防同质化
- 约束：基于已验证模板，不临场编造

## Task（任务）
生成 N 条差异化内容矩阵（角度/案例/钩子轮换）。

## Format（格式）
见 frontmatter format（矩阵表格）。

## Constraint（约束）
- 基于已验证模板与素材
- angle/hook/case 随机抽取且不与前列重复
- 跨平台用对应语态（调用 post-*）
- 语言：简体中文

## Anti_Dup（防同质化）
量产红线：角度库≥3、案例池≥5、钩子池≥5，随机组合；矩阵内零重复开头。

## Quality_Gate（质量门禁）
- [ ] 连续两条角度/案例撞车？
- [ ] 都基于已验证模板素材？
- [ ] 平台语态匹配？

## Example_IO（范例）
见 frontmatter example_io。
