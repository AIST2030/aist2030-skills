# AIST2030 头条草稿箱批量发布

仅操作你本人草稿箱中**已存在**的文章（不生成新内容），按 8 个高峰时段配额（3/2/3/2/4/5/6/4，共 29 条）自动发布，每次间隔 ≥15 分钟。内置去重、只读保护、登录态持久化与异常重试。首次人工登录后日常零介入。

## 适用场景
- 你已在 `mp.toutiao.com` 草稿箱备好若干待发文章。
- 希望按流量高峰错峰发布、规避限流、且不想每天手动点。

## 目录
```
AIST2030-post-toutiao-draft-v1.0/
├── SKILL.md            # 技能说明（RCTFC + 部署）
├── scripts/
│   ├── cli.py          # 入口：login / import-cookies / dry-run / run-day / run-forever / mock-smoke
│   ├── toutiao_publisher.py  # Playwright 发布核心
│   ├── scheduler.py    # 每日控制器 + 时段时间线
│   ├── state.py        # 状态文件读写（去重/暂停）
│   ├── mock_server.py  # 本地 mock 草稿箱（开发期冒烟）
│   └── auth.json.example
├── scheduler/
│   ├── crontab.linux.txt   # Linux/macOS cron 模板
│   ├── task-scheduler.xml  # Windows 任务计划程序模板
│   └── loop.dev.md         # CodeBuddy loop 开发期用法
├── references/
│   ├── selector-map.md  # 草稿箱 DOM 定位策略
│   └── slots.md         # 时段时间线推导
└── requirements.txt
```

## 快速开始（本机，需能访问 mp.toutiao.com）
1. 安装依赖：`pip install -r requirements.txt`，确认系统 Chromium 可用（`which google-chrome`）。
2. 准备登录态（二选一）：
   - **方式 A · 扫码登录**：`python3.11 scripts/cli.py login` → 浏览器弹出，扫码/凭证登录 → 自动保存 `auth.json`（权限 600）。
   - **方式 B · Cookie 登录**：从浏览器导出 cookie（见下方「用 Cookie 登录」），执行 `python3.11 scripts/cli.py import-cookies cookies.json` 生成 `auth.json`。
3. 只读预览（强烈建议先跑）：`python3.11 scripts/cli.py dry-run` → 真实进入草稿箱、按发布顺序列出候选队列，**绝不点发布**，据此确认选区/去重正确。
4. 部署调度：
   - Linux/mac：`crontab scheduler/crontab.linux.txt`（每日 07:55 启动）。
   - Windows：管理员 PowerShell `Register-ScheduledTask -Xml (Get-Content scheduler/task-scheduler.xml | Out-String) -TaskName AIST2030-ToutiaoDraft`。
   - 常驻无 cron：`nohup python3.11 scripts/cli.py run-forever &`。
5. 监控：`cat state.json`（published 进度）、`cat notify.log`（异常）、`tail -f run.log`。

## 用 Cookie 登录（方式 B）
1. 浏览器登录 `mp.toutiao.com` 并打开草稿箱。
2. 按 F12 → Application → Cookies → 选中 `mp.toutiao.com` → 复制为 **JSON 数组**（或装 EditThisCookie 一键导出；也可直接从控制台 `document.cookie` 复制 `name=value;...` 文本）。
3. 存为 `cookies.json`，执行：
   ```bash
   python3.11 scripts/cli.py import-cookies cookies.json
   # 支持三种格式：JSON 数组 / 含 "cookies" 键的 dict / document.cookie 文本
   # 可选：--domain .mp.toutiao.com（cookie 无 domain 时补）、--auth 自定义输出路径
   ```
4. `import-cookies` 会写出 `auth.json`（Playwright storage_state，权限 600）。cookie 含登录态，本地保存、不入 git。

## 开发期冒烟（沙箱/本机，不触真站）
```
python3.11 scripts/cli.py mock-smoke --fail-first 0   # 全成功：验证 29 条去重/状态写回
python3.11 scripts/cli.py mock-smoke --fail-first 2   # 每条第3次成功：验证重试可恢复
python3.11 scripts/cli.py mock-smoke --fail-first 9   # 首条耗尽重试：验证暂停 + notify.log
```
> mp.toutiao.com 在沙箱可解析且可达；真站登录态/发布建议在本机完成，沙箱可做只读校准（dry-run，绝不发布）。

## 安全与合规
- **只读**：脚本对标题/封面/正文只读取定位、零写入，仅点击「立即发布」。
- **去重**：以本地 `state.published` 为准，已发布永不二次点击。
- **凭证安全**：`auth.json` 含登录态，本地权限 600、不入 git、不进发布包。
- **外部调用仅限 `mp.toutiao.com`**，无数据外传。
- 平台 ToS / 反爬：自动化发布属你本人草稿；建议先小批量试跑观察，必要时人工介入验证码。
