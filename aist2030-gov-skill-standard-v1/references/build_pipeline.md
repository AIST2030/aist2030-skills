# 技能搭建流水线（5 步）+ 模板 + 命令

> 把"要造一个技能"从需求收敛到可发布标准件的固定步骤。配套 `factory.py` 自动化门禁。

---

## 1. 搭建流水线 5 步

```text
需求 → ① 定模块/定 id  → ② 填 RCTFC 模板  → ③ 写示例 I/O
     → ④ 过质量门禁     → ⑤ 入 Registry + 打 version
```

- ① **定模块/定 id**：明确它服务哪个模块（`kb`/`course`/`post`/`mass`/`gov`）、解决什么具体问题（避免造没人用的技能）；`id` 按 `AIST2030-<domain>-<slug>-vX.Y` 起名，`id`/目录名/`name` 三处一致。
- ② **填 RCTFC 模板**：用下方模板填充 frontmatter + 正文，14 个必填字段一个不留空。
- ③ **写示例 I/O**：附 1 个「输入 → 输出」范例（`example_io`），方便他人直接对标，也作为测试基准。
- ④ **过质量门禁**：逐项勾选 §3 内部门禁 +（对外）外部门禁；不过门禁不许发布。
- ⑤ **入 Registry + 打 version**：跑 `factory.py` 投产，版本号从 `v1.0` 起，迭代 `+0.1`。

---

## 2. 填空模板（SKILL.md）

```markdown
---
id: AIST2030-<kb|course|post|mass|gov>-<function>-v1.0
name: AIST2030 <技能名称>
module: <知识库整理|课程资料产出|AI发文|内容量产|治理审查>
version: v1.0
owner: AIOPC
capability: <一句话能力声明>
pricing: 免费/内部（对外发布到 SkillHub 时再填具体定价）
role: <角色设定>
context: <上下文/输入物说明>
task: <任务目标>
format: <输出格式规范>
constraint: <约束（含可信度标注要求）>
quality_gate:
  - <自检项1>
  - <自检项2>
anti_dup: <防同质化规则>
input_schema: <输入物结构化描述：字段/形态/约束>
output_schema: <输出物结构化描述：字段，且能直接作为下游输入>
deps: []
tags: []
example_io: |
  <输入示例>
  ---
  <输出示例>
---

# SKILL：<技能名称>

## Role（角色）
你是一名<角色设定>，擅长<核心能力>。

## Context（上下文）
- 输入物：<原始素材类型与形态>
- 背景：<业务目标/下游用途>
- 已知约束：<时间/平台/字数/风格等>

## Task（任务）
将输入物转化为<目标产物>，必须满足：
1. <关键要求1>
2. <关键要求2>
3. <关键要求3>

## Format（格式）
严格按以下结构输出：
- 字段A：<说明>
- 字段B：<说明>
- 字段C（可信度）：<高/中/低 + 来源>

## Constraint（约束）
- 所有事实必须<可溯源/标注来源>
- 对不确定的内容<显式标注「待核实」>
- 禁止<幻觉/编造数据/臆测引用>
- 输出语言：简体中文

## Anti_Dup（防同质化）
- 必须从<角度库>中切换叙事角度
- 案例/变量每次从<变量池>随机抽取组合
- 禁止连续两篇使用相同开头/案例

## Quality_Gate（质量门禁，发布前自检）
- [ ] <对应 quality_gate 项1>
- [ ] <对应 quality_gate 项2>

## Example_IO（范例）
<粘贴 example_io 内容，作为 few-shot>
```

---

## 3. factory.py 命令速查

| 命令 | 作用 |
|---|---|
| `python3.11 factory.py` | 内部门禁：处理 `drafts/` → 校验 → 投产到 `skills/` + 更新 `registry.json` |
| `python3.11 factory.py --check skills/AIST2030-kb-card-v1.md` | 单文件校验，不过则 `EXIT=1` |
| `python3.11 factory.py --publish governance/AIST2030-xxx-v1` | **外部门禁**：按 SkillHub 规范审查并出报告，有 ❌ 则 `EXIT=1` |
| `python3.11 factory.py --init AIST2030-kb-demo-v1.0 "示例" 知识库整理` | 按模板生成草稿脚手架 |

> 治理类技能（`gov-` 开头）以**文件夹**形态存放于 `governance/`，仅作人工发布前 checklist，不走 `factory.py` 自动门禁；但可对其运行 `--publish` 做外部门禁自检。

---

## 4. 内部门禁（factory.py 强制，必过）

- [ ] 所有 ✅ 字段存在且非空
- [ ] `id` 匹配 `^AIST2030-(kb|course|post|mass|gov)-[a-z0-9-]+-v\d+(\.\d+)?$`
- [ ] `id` 的 `domain` 段与 `module` 对应缩写一致
- [ ] `module` 在枚举内
- [ ] `quality_gate` 为非空 list

## 5. 外部门禁（SkillHub 发布，仅对外需要）

- [ ] 根目录含 `SKILL.md`
- [ ] 上传大小 ≤ 10MB
- [ ] 文件数 ≤ 200
- [ ] `name` 清晰
- [ ] `description` 首句含「输入 / 输出 / 适用边界」三段式
- [ ] `tags` 含中英文检索词
- [ ] `version` 已填（语义化）
- [ ] `capability` 已填
- [ ] `pricing` 已配（`model` + `amount_fen`）
- [ ] 定价合理（轻量类约 0.20 元/次）
- [ ] 企业认证已通过（用户侧自查）
- [ ] 商户入驻已完成（用户侧；按调用量计费需）
- [ ] 3 个效果案例已填（核心能力 / 行业场景 / 边界说明）
- [ ] 核心流程本地已跑通
