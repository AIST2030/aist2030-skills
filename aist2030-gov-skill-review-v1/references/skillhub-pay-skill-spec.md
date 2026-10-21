# SkillHub 对外发布 Pay Skill 规范（审查依据）

> 来源：SkillHub「对外发布 Pay Skill」官方规则。本文件由 `AIST2030-gov-skill-review-v1`
> 的审查报告反推整理，作为发布前审查的权威依据；若官方文档有更新，以官方为准。

## 1. 必填 frontmatter 字段（SKILL.md）

| 字段 | 要求 | 说明 |
|---|---|---|
| `name` | 必填 | 技能目录名/标识，清晰可读 |
| `description` | 必填 | 首句必须写「**输入：… 输出：… 适用边界：…**」三段式 |
| `tags` | 必填 | 含中英文检索词，便于召回 |
| `version` | 必填 | 语义化版本（如 `1.0.0`） |
| `capability` | 必填 | 能力标识（如 `skill_publish_review`） |
| `pricing` | 必填 | 计费配置：`model: per_call` 或 `free`；`amount_fen: <分>`（如 `20` = 0.20 元/次） |

## 2. 资源约束

- 根目录必须含 `SKILL.md`
- 上传总大小 **≤ 10MB**
- 文件总数 **≤ 200**

## 3. 计费与资质

- 计费模式：`per_call`（按调用量）等；免费用 `model: free`
- 定价合理性：轻量审查/生成类服务建议 **0.20 元/次** 量级，不过高过低
- 企业认证：发布前需通过（用户侧自查，文件无法验证）
- 商户入驻：按调用量计费需入驻（用户侧自查）

## 4. 内容要求

- **3 个效果案例**：核心能力 / 典型行业场景 / 边界说明（见 `assets/case-template.md`）
- 核心流程本地跑通：提交前用任一真实 skill 实跑一遍本 skill 流程

## 5. 内部规范（AIOPC 体系，独立校验）

见 `SKILL_SPEC.md §1.4`：命名 `AIST2030-<domain>-<slug>-vX.Y`、`id`/`目录名`/`name` 三处一致、
RCTFC 字段齐全、`quality_gate` 非空。内部使用只需过本部分；对外发布需 §1–§4 全过。
