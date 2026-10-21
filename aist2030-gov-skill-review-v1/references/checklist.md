# 发布前检查清单（SkillHub Pay Skill）

对照 `skillhub-pay-skill-spec.md` 逐项勾选。本清单即 `AIST2030-gov-skill-review-v1` 的执行核对项。

## 必修项（❌ 不通过则不可发布）

- [ ] 根目录含 `SKILL.md`
- [ ] 上传大小 ≤ 10MB
- [ ] 文件数 ≤ 200
- [ ] `name` 清晰
- [ ] `description` 首句含「输入 / 输出 / 适用边界」三段式
- [ ] `tags` 含中英文检索词
- [ ] `version` 已填（语义化）
- [ ] `capability` 已填
- [ ] `pricing` 已配（`model` + `amount_fen`）

## 建议优化项（⚠️ 不阻塞，但建议补）

- [ ] 定价合理（不过高过低，轻量类约 0.20 元/次）
- [ ] 企业认证已通过（用户侧自查）
- [ ] 商户入驻已完成（用户侧；按调用量计费需）
- [ ] 3 个效果案例已填（核心能力 / 行业场景 / 边界说明）
- [ ] 核心流程本地已跑通（提交前用真实 skill 实跑）

## 内部规范（AIOPC，独立校验，见 `SKILL_SPEC.md §1.4`）

- [ ] 命名 `AIST2030-<domain>-<slug>-vX.Y`
- [ ] `id` / 目录名 / `name` 三处一致
- [ ] RCTFC 字段齐全（role/context/task/format/constraint）
- [ ] `quality_gate` 非空
