# CodeBuddy loop 开发期触发（不触真站）

在沙箱/开发机上做逻辑冒烟时，用 CodeBuddy `loop` 技能按间隔重复跑 mock 冒烟，等效"每日调度"的开发期替身。

## 用法

```
/loop 1d python3.11 scripts/cli.py mock-smoke --fail-first 0
```

或更激进地每 10 分钟跑一次快速验证：

```
/loop 10m python3.11 scripts/cli.py mock-smoke --fail-first 2
```

## 说明

- `mock-smoke` 启动本地 `mock_server.py` 假草稿箱（35 篇），以 fast 模式按时间线发完 29 条，
  全程不连接 `mp.toutiao.com`。
- `--fail-first N`：前 N 次 `/publish` 返回失败，用于验证「重试 2 次后暂停并通知」逻辑。
  - N=0：全成功，验证 29 条去重/无改内容/状态写回。
  - N=2：每条第 3 次成功，验证重试可恢复。
  - N>=3：首条即耗尽重试，验证暂停 + notify.log 写入。
- 真实「每日执行一次」请改用 `scheduler/crontab.linux.txt` 或 `task-scheduler.xml` 部署到能出网的本机。
