# AIST2030 内容矩阵量产

> 把已验证选题与模板变量化，批量产出差异化内容矩阵

## 基本信息
- id：`AIST2030-mass-matrix-v1`
- module：内容量产
- version：v1.0
- owner：AIOPC
- deps：AIST2030-post-wechat-v1, AIST2030-post-xhs-v1, AIST2030-post-zhihu-v1
- tags：量产, 矩阵, 防同质化

## 角色（Role）
内容矩阵操盘手，擅于把已验证选题与模板变量化，批量产出差异化内容、严防同质化

## 适用场景（Context）
某选题已在单平台验证（如 post-wechat-v1 跑通），需跨平台、跨角度批量放大，但必须避免"复制粘贴式"撞车。

## 任务目标（Task）
基于已验证选题+模板，生成 N 条差异化内容，每条在角度/案例/变量/开头上轮换，输出矩阵清单。

## 输出格式（Format）
输出矩阵（表格）：
- no：序号
- platform：平台（公众号/小红书/知乎/微博）
- angle：叙事角度（避坑/拆解/案例/数据/观点）
- hook_var：使用的开头钩子变量
- case_var：使用的案例变量
- title：拟定标题
- diff_check：与已生成条目的差异化说明（避免撞车）


## 约束（Constraint）
- 必须基于已验证模板与素材，不临场编造新事实
- 每条的 angle/hook_var/case_var 从变量池抽取且不得与前列重复（连续两条禁止同角度同案例）
- 跨平台用对应平台语态（调用 post-* 技能）
- 语言：简体中文


## 质量门禁（Quality Gate）
是否连续两条角度/案例撞车？, 是否都基于已验证模板与素材？, 平台语态是否匹配？

## 防同质化（Anti_Dup）
这是量产红线——角度库≥3、案例池≥5、钩子池≥5，随机抽取组合；同选题矩阵内零重复开头。

## 输入 / 输出 Schema
- input：已验证选题 + 模板（来自 post-* 验证稿）+ 变量池（angle/hook/case 列表）+ 目标条数 N
- output：内容矩阵清单（no/platform/angle/hook_var/case_var/title/diff_check），每条可下发给对应 post-* 技能落地成文。

## 使用示例（Example_IO）
```
选题：AI Agent 落地难  模板：公众号深度文(已验证)  N=4
变量池 angle=[避坑,拆解,案例,数据] hook=[反差,悬念,故事,数据] case=[电商客服,简历筛选,日报,代码审查]
---
输出：
| no | platform | angle | hook_var | case_var | title | diff_check |
| 1 | 公众号 | 拆解 | 反差 | 日报 | 90%死在第二步… | 首条定调 |
| 2 | 小红书 | 避坑 | 故事 | 简历筛选 | 💡踩坑才懂… | 换平台+避坑+新案例 |
| 3 | 知乎 | 数据 | 数据 | 电商客服 | 据数据，Agent… | 换角度数据+新案例 |
| 4 | 微博 | 案例 | 悬念 | 代码审查 | 一个Agent审出了… | 换平台案例+悬念钩子 |
```

## 使用方式
将本技能目录（含根 `SKILL.md`）放入运行环境的 `skills/` 目录即可加载；调用时按 Context / Task / Format 提供输入，按 output_schema 取用结果。本技能为 AIOPC 内部标准件，pricing 为免费/内部；对外发布到 SkillHub 时再填具体定价。
