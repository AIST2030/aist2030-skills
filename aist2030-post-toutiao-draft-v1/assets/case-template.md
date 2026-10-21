# 效果案例（case-template）

> 以下为三种典型运行场景。场景一/二可在沙箱用 `mock-smoke` 复现（不触真站）；场景三需在能出网的本机真实运行。

### 案例 1：单日全量发布（常规成功路径）
- **场景**：草稿箱已备 35 篇待发文章，首次登录后部署 cron 每日 07:55 启动。
- **输入**：`state.published` 为空；`SLOT_PLAN` = 8 时段配额（3/2/3/2/4/5/6/4，共 29）。
- **执行**：`python3.11 scripts/cli.py run-day` → 进程按 29 个绝对时刻、≥15min 间隔依次发布。
- **结果**：一天结束 `state.published` 记录 29 条（08:00×3 / 10:00×2 / 12:00×3 / 14:00×2 / 17:00×4 / 19:00×5 / 21:00×6 / 23:00×4），`paused=false`，`notify.log` 为空；剩余 6 篇未被动改动。

### 案例 2：发布异常 → 重试恢复（fail-first=2）
- **场景**：某时段前 2 次点击因网络抖动被平台拒绝（mock 注入前 2 次 /publish 失败）。
- **输入**：`python3.11 scripts/cli.py mock-smoke --fail-first 2`。
- **执行**：`publish_one` 内置 1+2 次尝试；第 3 次成功。
- **结果**：该条仍成功发布，`state.published` 累计 29 条，`notify.log` 为空（重试内恢复，不触发暂停）。

### 案例 3：重试耗尽 → 暂停并通知（fail-first=9）
- **场景**：登录态过期或页面长时间异常，首条即连续失败。
- **输入**：`python3.11 scripts/cli.py mock-smoke --fail-first 9`。
- **执行**：`publish_one` 1+2 次尝试全部失败 → 抛 PublishError → `run-day` 置 `paused=true` 并写 `notify.log`（可选 `TOUTIAO_NOTIFY_HOOK` webhook）。
- **结果**：当日停止，不静默续跑；运维排查后清除 `paused` 标志、重跑 `login` 刷新 `auth.json` 即可续跑剩余配额。
