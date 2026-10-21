---
id: aist2030-post-toutiao-draft-v1
name: AIST2030 头条草稿箱批量发布
displayName: AIST2030 头条草稿箱批量发布
slug: aist2030-post-toutiao-draft-v1
module: AI发文
version: 1.0.0
internal_version: v1.0
owner: AIST2030
author: AIST2030
pricing:
  model: per_call
  amount_fen: 1
capability: 登录 mp.toutiao.com 草稿箱，按高峰时段配额自动发布已存在草稿，带去重/只读/重试保护，并持久化发布状态。
description: 输入：你本人 mp.toutiao.com 草稿箱中已存在的文章（不生产任何新内容）+ 运行参数（AUTH_STATE=auth.json、STATE_FILE=state.json、SLOT_PLAN 高峰时段配额）。输出：逐条发布执行结果与持久化状态文件（state.json 的 published 列表 / paused 标志、notify.log），可作为次日定时重跑的续跑依据与运营对账凭证。适用边界：只发布草稿箱里已有的草稿，不生成也不修改文章内容；带去重/只读/重试三重保护，受平台配额与登录态限制。当用户要一键批量发头条草稿箱、按高峰时段配额发布头条文章、做定时重跑发布时调用。
role: 头条草稿箱自动发布操作员，擅长用 Playwright 以拟人节奏安全地把草稿箱文章按排期发出，绝不改内容、绝不重复发。
context: 你的草稿箱（mp.toutiao.com → 草稿箱）里已经准备好若干篇待发布文章；本技能只读取并点击「立即发布」，不撰写、不修改任何正文/标题/封面。
task: '1. 加载本地登录态 auth.json；若无则引导首次扫码/凭证登录并持久化。

  2. 打开 mp.toutiao.com 并进入「草稿箱」页面，等待列表渲染。

  3. 选取「未发布且未标记」的首条草稿（以本地 state.published 为准去重）。

  4. 严格只读：仅定位并点击该行「立即发布」按钮，绝不编辑标题/封面/正文。

  5. 轮询确认发布成功，将本条写入本地状态文件标记为「已发布」。

  6. 按日控制器在 8 个高峰时段、对应配额、≥15min 间隔内循环执行上述发布周期。

  7. 遇登录失败或页面异常：自动重试 2 次（重登/刷新），仍失败则置暂停并通知，当日停止、不静默续跑。

  8. 发布结束保持浏览器进程存活，不关闭，以备次日 cron 重新拉起。

  '
format: '输出/产物：

  - 状态文件 state.json：{ last_run, paused, auth_state_file, published:[{draft_id,title,published_at}],
  failed:[] }

  - 通知日志 notify.log：异常暂停时写入（可选 TOUTIAO_NOTIFY_HOOK webhook）

  - 控制台运行日志：每次发布打印「[OK] 已发布 <title> @ <time>」或「[RETRY] 第N次」「[PAUSE] 已暂停并通知」

  '
constraint: '- 禁止生成新内容：本技能不撰写、不拼接、不改写任何文章。

  - 禁止修改内容：对标题、封面、正文只读取用于定位，零写入；发布按钮之外不做任何编辑操作（代码层硬约束）。

  - 禁止重复发布：每次选区前查 state.published，命中即跳过；同日重跑自动续跑剩余配额。

  - 节流拟人：相邻两次发布间隔固定 ≥15 分钟；点击走 Playwright 默认 human-like 节奏。

  - 登录态安全：auth.json 含敏感凭证，本地权限 600、不入 git、不进发布包。

  - 外部调用仅限 mp.toutiao.com；不访问任何其他站点，不发起任何数据外传。

  - 优雅失败：重试 2 次后必须暂停并通知，禁止无提示地反复重试或跳过已发布内容。

  '
quality_gate:
- 本次发布是否确实命中「未标记」首条（去重校验通过）？
- 发布过程是否零修改内容（仅点击「立即发布」）？
- 失败时是否按规则重试 2 次并最终暂停通知（未静默吞错）？
- 状态文件是否准确记录了本条 published（draft_id/title/published_at）？
anti_dup: 以本地 state.published 作为唯一去重源；每次发布前查重，已发布 id 永不二次点击。日控制器跳过当日已完成的时段配额，支持断点续跑。
input_schema: 草稿箱已存在文章（无新内容输入）；运行参数：AUTH_STATE=auth.json、STATE_FILE=state.json、BASE_URL=https://mp.toutiao.com、SLOT_PLAN=内置
  8 时段配额。
output_schema: 状态文件 state.json（published 列表 + paused 标志）+ notify.log；可直接作为次日 cron
  重跑的续跑依据与运营对账凭证。
secrets: []
deps: []
tags:
  - 今日头条
  - 草稿箱
  - 批量发布
  - 浏览器自动化
  - 定时任务
  - toutiao
  - draft
  - batch-publish
  - automation
example_io: '输入：草稿箱现有 35 篇待发布文章，state.published 为空。

  ---

  输出（运行一天后）：

  state.json.published 含 29 条（08:00×3 / 10:00×2 / 12:00×3 / 14:00×2 / 17:00×4 / 19:00×5
  / 21:00×6 / 23:00×4），paused=false；

  notify.log 为空（无异常）；剩余 6 篇留待后续按需发布，未被动改动。'
---

# SKILL：AIST2030 头条草稿箱批量发布

## Role（角色）
你是头条草稿箱自动发布操作员，擅长用 Playwright 以拟人节奏安全地把草稿箱文章按排期发出。你的铁律是：**只发不写、只点不改、去重不断、失败必报**。

## Context（上下文）
- 输入物：mp.toutiao.com「草稿箱」中**已存在**的文章。本技能不生产内容，只操作既有草稿。
- 运行前提：设备已唤醒并联网、浏览器可加载头条页面；首次运行需人工完成一次登录以生成 auth.json。

## Task（任务）
1. **登录态**：加载 `auth.json`（Playwright storage state）。不存在则启动有头浏览器引导扫码/凭证登录，登录成功后 `state_save` 持久化，后续复用。
2. **进入草稿箱**：打开 `BASE_URL` → 进入「草稿箱」页 → 等待列表渲染（snapshot 取草稿行）。
3. **选区**：取 DOM 首行且 `data-id`/标题 **不在** `state.published` 中的草稿，即「未发布且未标记」首条。
4. **只读发布**：仅定位并点击该行「立即发布」按钮。严禁改标题/封面/正文。
5. **确认与落库**：轮询发布结果（toast/列表消失），成功后写 `state.published: {draft_id, title, published_at}`。
6. **日调度**：`scheduler.py` 在 8 个高峰时段按配额（3/2/3/2/4/5/6/4，共 29）以 ≥15min 间隔自调度发布周期。
7. **异常处理**：登录失败/页面异常 → 重试 2 次（重登或刷新）→ 仍失败 → `paused=true` + 写 notify.log（+ 可选 webhook）→ 当日停止。
8. **保活**：发布结束不关闭浏览器，进程留驻，等待次日 cron 重新拉起。

## Format（格式）
- **状态文件** `state.json`：`{ last_run, paused, auth_state_file, published:[{draft_id,title,published_at}], failed:[] }`
- **通知日志** `notify.log`：异常暂停时追加记录；可选 `TOUTIAO_NOTIFY_HOOK` 环境变量指向 webhook 做外部推送。
- **控制台**：每次发布打印 `[OK] 已发布 <title> @ <time>`；重试打印 `[RETRY] 第N次`；暂停打印 `[PAUSE] 已暂停并通知`。

## Constraint（约束）
- **禁止生成新内容**：不撰写、不拼接、不改写任何文章。
- **禁止修改内容**：标题/封面/正文只读取定位、零写入；发布按钮之外零编辑（代码层硬约束）。
- **禁止重复发布**：每次选区前查 `state.published` 去重；同日重跑自动续跑剩余配额。
- **节流拟人**：相邻发布间隔固定 ≥15 分钟；点击走 Playwright 默认 human-like 节奏。
- **登录态安全**：`auth.json` 本地权限 600、不入 git、不进发布包。
- **外部调用仅限 `mp.toutiao.com`**；不访问其他站点，不做任何数据外传。
- **优雅失败**：重试 2 次后必须暂停并通知，禁止无提示反复重试或跳过已发布内容。

## Anti_Dup（防同质化）
- 以 `state.published` 为唯一去重源；每次发布前查重，已发布 id 永不二次点击。
- 日控制器跳过当日已完成时段配额，支持中断后续跑。

## Quality_Gate（质量门禁）
- [ ] 本次发布是否命中「未标记」首条（去重校验通过）？
- [ ] 发布过程是否零修改内容（仅点击「立即发布」）？
- [ ] 失败时是否重试 2 次并最终暂停通知（未静默吞错）？
- [ ] 状态文件是否准确记录本条 published（draft_id/title/published_at）？

## Example_IO（范例）
输入：草稿箱现有 35 篇待发布文章，state.published 为空。
输出（运行一天后）：state.json.published 含 29 条（08:00×3 / 10:00×2 / 12:00×3 / 14:00×2 / 17:00×4 / 19:00×5 / 21:00×6 / 23:00×4），paused=false；notify.log 为空；剩余 6 篇未被动改动。

## 外部调用与依赖声明
- **唯一外部站点**：`https://mp.toutiao.com`（草稿箱发布）。不发起任何其他网络请求。
- **密钥**：`secrets: []`。登录态经本地 `auth.json`（storage state）注入，不写死、不入库。
- **依赖**：`deps: []`。运行需 Python 3.11 + Playwright + 系统 Chromium（见 `requirements.txt`）。
- **不生成内容**：本技能零内容生产，仅浏览器操作，无 LLM 调用、无第三方 API。

## 部署与运行（落到本机）
1. 安装：`pip install -r requirements.txt`；确保系统 Chromium 可用（`which google-chrome`）。
2. 准备登录态（二选一）：
   - 扫码：`python3.11 scripts/cli.py login` → 有头浏览器弹出，扫码/凭证登录 → 自动保存 `auth.json`。
   - Cookie：`python3.11 scripts/cli.py import-cookies cookies.json`（支持 JSON 数组 / dict / document.cookie 文本）→ 生成 `auth.json`。
3. 只读预览（强烈建议）：`python3.11 scripts/cli.py dry-run` → 真实进草稿箱列出候选队列，绝不发布。
4. 试跑验证（不触真站）：`python3.11 scripts/mock_server.py &` 后 `python3.11 scripts/cli.py mock-smoke`。
5. 日常发布：`python3.11 scripts/cli.py run-day`（建议由 cron 每日 07:55 拉起）。
6. 调度模板见 `scheduler/`：Linux/mac 用 `crontab.linux.txt`，Windows 用 `task-scheduler.xml`，开发期用 `loop.dev.md`。
7. 监控：`cat state.json` 看 published 进度；异常看 `notify.log`。

> 说明：mp.toutiao.com 在沙箱可解析且可达；但真站登录态/发布仍建议在你本机完成，沙箱可做只读校准（dry-run，绝不发布，需你授权使用 cookie）。脚本开发与逻辑冒烟已在沙箱用 mock 完成。
