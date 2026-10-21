# SkillHub 对外发布 Pay Skill 规范（审查依据）

> 来源：SkillHub「对外发布 Pay Skill」官方规则。本文件由 `AIST2030-gov-skill-review-v1` 的审查报告反推整理，作为发布前审查的权威依据；若官方文档有更新，以官方为准。
> **仅当技能要对外发布到 SkillHub 时需要**；纯内部使用只需过 `inner_standard.md`。

---

## 1. 必填 frontmatter 字段（SKILL.md）

| 字段 | 要求 | 说明 |
|---|---|---|
| `name` | 必填 | 技能目录名/标识，清晰可读 |
| `description` | 必填 | 首句必须写「**输入：… 输出：… 适用边界：…**」三段式（对应内部 `context`/`task`/`format`） |
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

## 5. 与内部规范的关系

| 维度 | 内部规范（AIOPC） | 对外规范（SkillHub） |
|---|---|---|
| 触发 | 所有技能必过（factory.py 强制） | 仅对外发布需要 |
| 命名 | `AIST2030-<domain>-<slug>-vX.Y` 三处一致 | 无强制前缀，但 Slug 只能小写字母/数字/连字符 |
| 必填字段 | 14 个（见 inner_standard §1.1） | 6 个（name/description/tags/version/capability/pricing） |
| 案例 | 不强制 | 强制 3 个 |
| pricing | 内部填「免费/内部」 | 须填 `model + amount_fen` |
| 门禁工具 | `python3.11 factory.py` | `python3.11 factory.py --publish <dir>` |

> 内部使用只需过 §5 左列；对外发布需左右两列全过。验收流程见 `AIST2030-gov-skill-review-v1`。
