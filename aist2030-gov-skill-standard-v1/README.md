# AIST2030 技能搭建标准（`AIST2030-gov-skill-standard-v1`）

> AIOPC 技能的**统一搭建标准总纲**。无论新建还是验收，都以本 skill 为唯一权威依据。

## 一句话
把"造一个技能"的需求，收敛成**符合统一规格、可过门禁、可被下游消费**的标准件，并对照标准逐项验收。

## 它能做什么
1. 给 **RCTFC 字段规格**（14 必填 + 可选字段）；
2. 给 **命名规范**（`AIST2030-<domain>-<slug>-vX.Y`，id/目录名/name 三处一致）；
3. 给 **搭建流水线 5 步**（定模块/定 id → 填 RCTFC → 写 example_io → 过门禁 → 入 Registry）；
4. 给 **内部门禁**（factory.py 强制）与 **外部门禁**（SkillHub 发布）两份可勾选清单；
5. 给 **防同质化红线**（角度轮换 / 变量池化 / 开头禁重 / 平台分语）；
6. 对照标准 **验收草稿**，结论定位到具体字段/文件。

## 包结构
```text
AIST2030-gov-skill-standard-v1/
├── SKILL.md                      # 根指令体（RCTFC）
├── README.md                     # 本文件
├── references/
│   ├── inner_standard.md         # AIOPC 内部标准：字段表 + 命名 + 内部门禁
│   ├── skillhub_publish_spec.md  # SkillHub 对外发布规范
│   └── build_pipeline.md         # 5 步流水线 + 模板 + factory 命令
└── assets/
    └── case-template.md          # 3 个效果案例（核心/行业/边界）
```

## 元信息
| 字段 | 值 |
|---|---|
| id | `AIST2030-gov-skill-standard-v1` |
| module | 治理审查 |
| version | v1.0 |
| owner | AIOPC |
| pricing | 免费/内部（对外 SkillHub：per_call，0.20 元/次） |
| tags | 治理, 标准, 规范, 搭建, AIST2030, SkillHub |

## 速查
- 内部规格与字段表：`references/inner_standard.md`
- 对外发布规则：`references/skillhub_publish_spec.md`
- 流水线 5 步 + 模板 + 命令：`references/build_pipeline.md`
- 验收他人 skill：`AIST2030-gov-skill-review-v1`
- 投产门禁：`python3.11 factory.py`（内部） / `python3.11 factory.py --publish <dir>`（对外）
