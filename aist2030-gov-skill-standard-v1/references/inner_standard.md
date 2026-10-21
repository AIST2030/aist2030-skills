# AIOPC 内部技能标准（SKILL_SPEC v2）

> 适用范围：所有 AIOPC 内部技能（无论是否对外发布）。由 `factory.py` 内部门禁强制执行。
> 对外发布还需叠加 `skillhub_publish_spec.md` 的规范。

---

## 1. 字段总表

### 1.1 元信息字段（YAML frontmatter，脚本解析）

| 字段 | 必填 | 类型 | 说明 |
|---|---|---|---|
| `id` | ✅ | string | 唯一标识，统一命名 `AIST2030-<domain>-<slug>-v<版本号>`，如 `AIST2030-kb-card-v1` |
| `name` | ✅ | string | 技能中文名 |
| `module` | ✅ | enum | 知识库整理 / 课程资料产出 / AI发文 / 内容量产 / 治理审查 |
| `version` | ✅ | string | 语义化版本，从 `v1.0` 起，迭代 `+0.1` |
| `owner` | ✅ | string | 维护方，默认 `AIOPC` |
| `role` | ✅ | string | 角色设定（RCTFC 的 R） |
| `context` | ✅ | string | 上下文/输入物说明（C） |
| `task` | ✅ | string | 任务目标（T） |
| `format` | ✅ | string | 输出格式规范（F） |
| `constraint` | ✅ | string | 约束，含可信度标注要求（C） |
| `quality_gate` | ✅ | list | 发布前自检项（list of string） |
| `anti_dup` | ✅ | string | 防同质化规则 |
| `input_schema` | ✅ | string | 输入物的结构化描述（字段/形态/约束） |
| `output_schema` | ✅ | string | 输出物的结构化描述（可直接作为下游输入） |
| `deps` | ⬜ | list | 依赖的其它技能 id（上游），默认空 |
| `example_io` | ⬜ | string | 一段「输入 → 输出」范例，便于对标 |
| `tags` | ⬜ | list | 检索标签，便于 Registry 筛选 |
| `capability` | ⬜ | string | 能力声明（一句话说明本技能能干什么） |
| `pricing` | ⬜ | string | 定价/获取方式；内部体系默认填「免费/内部」，对外发布到 SkillHub 时再填具体定价 |

> **14 个必填**（factory.py `REQUIRED`）：`id, name, module, version, owner, role, context, task, format, constraint, quality_gate, anti_dup, input_schema, output_schema`。

### 1.2 正文（markdown body）

正文为**可直接调用的完整 RCTFC 指令体**，即该技能被调用时实际喂给模型的 prompt。frontmatter 中的 RCTFC 字段是正文的「摘要索引」，正文可展开细节、示例与 few-shot。

### 1.3 模块缩写映射

| module | 缩写 |
|---|---|
| 知识库整理 | `kb` |
| 课程资料产出 | `course` |
| AI发文 | `post` |
| 内容量产 | `mass` |
| 治理审查 | `gov` |

### 1.4 统一命名规范（含品牌 AIST2030）

所有技能**三处命名强一致**：`id`（frontmatter）/ 目录名 / `name`（展示名）都遵循同一规则。

**规则：** `AIST2030-<domain>-<slug>-v<major>.<minor>`

| 段 | 说明 | 约束 |
|---|---|---|
| `AIST2030` | 品牌前缀 | 固定大写，必带 |
| `<domain>` | 领域代码 | `kb`知识库 / `course`课程 / `post`发文 / `mass`量产 / `gov`治理审查 |
| `<slug>` | 功能名 | kebab-case，建议英文（机读），中文拼音亦可 |
| `-v<major>.<minor>` | 语义版本 | 次版本可省（`v1` 或 `v1.0` 均合法） |

> 说明：`domain` 是**命名领域**，与 `module`（4 大业务模块 + 治理）是两个维度。`gov` 为治理/审查类技能的命名领域，其 `module` 字段填「治理审查」，且不经过 `factory.py` 自动门禁（仅作人工发布前 checklist）。

**三处一致示例：**
- 目录名：`AIST2030-kb-card-v1/`
- id：`AIST2030-kb-card-v1`
- name：`AIST2030 知识卡片整理`

---

## 2. 内部门禁规则（factory.py 强制）

1. 所有 ✅ 字段必须存在且非空（空值/空 list/空 dict 视为缺失）；
2. `id` 必须匹配正则 `^AIST2030-(kb|course|post|mass|gov)-[a-z0-9-]+-v\d+(\.\d+)?$`；
3. `id` 的 `domain` 段必须与 `module` 对应缩写一致（如 `module=AI发文` → domain 必须是 `post`）；
4. `module` 必须在枚举内；
5. `quality_gate` 必须是非空 list，且每项以可勾选形式存在；
6. `deps` 中引用的 id 若在 Registry 中不存在仅**告警**，不阻塞（便于并行开发）；
7. `output_schema` 描述的字段必须能在 `format` 中找到对应（人工核对，脚本仅做存在性提示）。

> 任一必填缺失 → 内部门禁报错 `EXIT=1`，残次技能不会进 Registry。

---

## 3. 质量门禁（通用自检清单，每个技能都要 built-in）

- [ ] **可溯源**：关键事实/数据标注来源或「待核实」
- [ ] **无幻觉**：未编造引用、未臆测不存在的数据
- [ ] **格式合规**：严格匹配该技能的 `format`
- [ ] **防同质化**：未连续撞车角度/案例/开头
- [ ] **下游可用**：输出字段能直接喂给下一个模块
- [ ] **边界清晰**：明确「不做什么」，避免越界

---

## 4. 防同质化规则（量产红线）

1. **角度轮换**：同选题至少准备 3 个叙事角度（如「避坑向 / 拆解向 / 案例向」）。
2. **变量池化**：标题钩子、案例、数据、行业统统入变量池，随机组合。
3. **开头禁重**：连续内容不得复用同一句开场白或同一案例。
4. **平台分语**：同一选题在公众号/小红书/知乎用不同语态与结构。

---

## 5. 目录约定

```text
skill-factory/
├── SKILL_SPEC.md          # 标准规格 v2
├── SKILL_TEMPLATE.md      # 填空模板
├── factory.py             # 投产引擎（门禁）
├── registry.json          # 已注册技能目录（自动生成 + 治理技能手工登记）
├── skills/                # 已投产的标准化 SKILL 单文件（factory 生成）
│   └── <id>.md
├── drafts/                # 草稿区（作者在此写，再跑 factory）
├── governance/            # 治理类技能（文件夹形态，含 references/ assets/，不经 factory 自动门禁）
│   ├── AIST2030-gov-skill-review-v1/
│   └── AIST2030-gov-skill-standard-v1/
└── samples/               # 试跑素材与产出
```
