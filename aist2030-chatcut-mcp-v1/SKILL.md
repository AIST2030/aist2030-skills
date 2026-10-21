---
id: aist2030-chatcut-mcp-v1
name: AIST2030 ChatCut-Lite MCP 接入
displayName: AIST2030 ChatCut-Lite MCP 接入（自定义剪辑引擎）
slug: aist2030-chatcut-mcp-v1
module: 开发类
version: 1.0.0
internal_version: v1.0
owner: AIST2030
author: 贵州省团之家智付科技有限公司
source: 自建
pricing:
  model: free
  amount_fen: 0
capability: 把本地 ChatCut-Lite 剪辑引擎以 stdio MCP 服务暴露给任意智能体：chatcut_status（健康检查）/ chatcut_scenarios（场景列表）/ chatcut_compose（按导演配方一键出片）/ chatcut_render_plan（自由排版渲染完整 Plan JSON）。已注册到 ~/.workbuddy/mcp.json 的 chatcut-lite 服务。
description: 输入：无（接入型 skill）。输出：MCP 工具调用指导 + 参数模板 + 故障排查。适用：任何想通过 MCP 调用本地混剪能力的智能体会话；直接在对话里用 vmix-* skill 也可（内部走同一引擎 CLI）。
role: ChatCut-Lite MCP 接入与调用顾问。
context: |
  - MCP 服务已写入 %USERPROFILE%\.workbuddy\mcp.json（键名 chatcut-lite，stdio）：
    command = ${CHATCUT_HOME}\.venv\Scripts\python.exe
    args    = ${CHATCUT_HOME}\engine\mcp_server.py
  - 修改 mcp.json 后需在连接器管理里「信任」新服务并重启会话才会生效。
  - 引擎场景：event / local(探店) / product / course / recruit / festival / comprehensive。
  - 全链路零积分、素材不出本机；产物默认落在引擎缓存目录，建议调用时显式传 out_dir 到任务文件夹。
task: |
  1. 确认服务可用：调用 chatcut_status，期待 {"ok": true, "scenarios": [...7 个...]}。
  2. 场景选择：调用 chatcut_scenarios 看说明；需求明确就直接选，模糊时用 comprehensive 自动路由。
  3. 出片：调 chatcut_compose，传 scenario + params(JSON 字符串，字段模板见对应 vmix-* skill) + out_dir。
  4. 自由排版（高级）：先让对应导演模块生成 Plan，或手写 Plan JSON，再调 chatcut_render_plan。
  5. 故障排查：报「Invalid file index 0」检查 params 里素材路径是否存在；报「需要完整版 ffmpeg」检查 vendor/node_modules/ffmpeg-static；渲染卡住看引擎缓存目录下 *.log 尾部。
---
## 首次使用准备（引擎路径自适配）

出片依赖本地 ChatCut-Lite 引擎（约 1.8G，含运行环境与 ffmpeg，**不随本技能分发**）。
执行正式任务前，先确定引擎位置 `CHATCUT_HOME`：

1. 若已设置环境变量 `CHATCUT_HOME`，直接使用。
2. 否则依次探测以下常见位置，第一个存在即用：
   - 当前技能同级目录的 `ChatCut-Lite`
   - `%USERPROFILE%\ChatCut-Lite`
   - `%USERPROFILE%\AIST2030\ChatCut-Lite`
   - 本机其他盘符下的 `视频创作\AIST2030\ChatCut-Lite`
3. 找到后记下路径；Python 解释器取该目录下的 `.venv\Scripts\python.exe`（macOS/Linux 为 `.venv/bin/python`），
   下文统一称 `${CHATCUT_PY}`。
4. 若都找不到：本技能无法单独出片，需先安装 ChatCut-Lite 引擎，再回填上述路径后重试。

统一入口用法：`"${CHATCUT_PY}" "${CHATCUT_HOME}/engine/cli.py" compose <scenario> <params.json> -o <输出目录>`
（Windows 用反斜杠，macOS/Linux 用正斜杠）。

