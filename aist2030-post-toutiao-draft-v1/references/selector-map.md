# 草稿箱 DOM 定位策略（selector-map）

> 目标：在 `mp.toutiao.com` 草稿箱页面中，**只读**定位「未发布且未标记」首条，并点击其「立即发布」按钮。
> 原则：文本/Aria 优先（抗 class 重命名），CSS 兜底；绝不触碰标题/封面/正文输入框。

## 1. 进入草稿箱
- URL：`https://mp.toutiao.com/profile_v4/manage/draft`（命中跳登录页则触发重登）。
- 等待列表渲染：`wait_for_selector(".draft-item, [class*='draft'], [class*='article']")`。

## 2. 选区（首条未发布/未标记）
- 行容器：`.draft-item`（兜底 `[class*='draft']` / `[class*='article']`）。
- 去重键：`data-id`（兜底取标题文本哈希）；与本地 `state.published` 比对，命中即跳过。
- 标题：`row .title`（兜底 `[class*='title']`），**仅读取用于日志/对账，不写入**。

## 3. 发布按钮
- 首选：`button:has-text("立即发布")`（Playwright 文本匹配，抗 class 变化）。
- 兜底：`.publish-btn`。

## 4. 结果确认
- 轮询（对 toast 短时消失鲁棒）：出现 `.toast-success`，或任意「立即发布」按钮变为「已发布」（文本 `button:text('已发布')`）即判成功。
- 失败：`.toast-error` 出现 → 抛 PublishError 触发重试。
- 超时（15s 内无上述信号）→ 视为失败，进入重试。

## 5. 反爬/异常兜底
- 出现登录页（`passport` 域名或 `input[type=password]`）→ 抛 NeedsLogin，调度器置 paused 并通知。
- 滑块/验证码：首次人工登录阶段处理；日常零介入。若运行中弹出，重试 2 次仍失败则暂停。
- 元素未找到：选区返回 None → 当日提前结束（无更多草稿）。

## 6. 只读硬约束（代码层）
- 脚本只调用 `locator(...).inner_text()` / `get_attribute()`（读）与 `btn.click()`（点）。
- 绝对不调用 `fill()` / `type()` / `press()` 作用于标题/封面/正文，从代码上杜绝改内容。

## 7. 真实 DOM 提示（与 mock 的差异）
- mock 用 `.draft-item` / `.publish-btn` / `.title` 仅为冒烟占位；**真实草稿箱 class 名称可能不同**。
- 最稳的是文本匹配：`button:has-text("立即发布")`（抗 class 重命名）。
- 行容器与标题选择器若真站不符，用 `cli.py dry-run` 进入真实草稿箱、观察实际 class 后微调本文件第 1–3 节即可。
- 「未标记」判定一律以本地 `state.published` 为准（真站 UI 未必暴露我们的标记），与 DOM class 无关。
