---
id: aist2030-ai-paid-backend-v1
name: AIST2030 AI付费后端接入
displayName: AIST2030 AI付费后端接入
slug: aist2030-ai-paid-backend-v1
module: AI后端
version: 1.0.0
owner: AIST2030
source: 自建
author: 贵州省团之家智付科技有限公司
role: ai-paid-backend 执行助手，擅长在 AI后端 场景下按标准流程完成任务交付。
context: 用户输入与素材，经本技能流程处理后产出目标结果；已知约束见 constraint 与边界说明。
task: 将用户关于「ai-paid-backend」的需求转化为标准化交付物，遵循 quality_gate 与 constraint。
format: 结构化结果 + 必要的过程说明，可直接被下游技能或用户消费。
constraint: 仅处理本技能职责范围内的任务；涉及外部密钥/支付/合规时须显式向用户确认；不越权调用其他系统。
quality_gate: 交付前自检：必填字段完整、产出可用、边界清晰、无越权行为。
anti_dup: 与同类 AI后端 技能互斥，按语义匹配唯一触发，避免重复执行。
input_schema: 用户需求描述 / 必要素材（链接、文件、参数）。
output_schema: 标准化交付物 + 状态回显（成功 / 失败原因）。
capability: 提供「ai-paid-backend」能力：适用：任何前端工具想接"付费才用真AI"，且不想让前端持有大模型密钥、要防绕过。，按既定流程交付结果，适用
  AI后端 场景。
description: 输入：适用：任何前端工具想接"付费才用真AI"，且不想让前端持有大模型密钥、要防绕过。 相关需求或素材。 输出：按本技能流程产出的结果与可交付物。
  适用边界：仅当用户明确需要「ai-paid-backend」能力、且属于 AI后端 场景时调用；不属于本技能职责的需求应交由其他技能处理。
tags:
- ai
- paid
- backend
- saas
- monetization
pricing:
  model: per_call
  amount_fen: 1
---

# 真AI 按次付费后端（零依赖 Node）

适用：任何前端工具想接"付费才用真AI"，且不想让前端持有大模型密钥、要防绕过。
核心闭环：普通用户 = 前端本地模板（免费）；真AI = 服务端大模型生成，凭**付费令牌**调用。

## ⚠️ 决策门：先问"收费目的是什么"
- **只为控算力成本（非变现）→ 不要走本付费后端**。任何真支付通道（微信/支付宝商户、对公账户）都会触发**经营性 ICP 许可证 + 对公**要求，个体户/小公司合规成本高、且本类工具多为获客漏斗不靠它赚钱。退回已排除路线是浪费。
- 成本控 only 的正确做法 = **浏览器端免费配额 + 自备密钥（BYO）**，零后端、零托管、零合规风险：
  1. **方式一 BYO Key**：前端填用户自己的 API Key（OpenAI 兼容）→ 真 AI，成本在用户侧、不限额。复用 `aiGenerate(f,opts)` 思路，密钥不落地他人。
  2. **方式二 免费额度**：部署方在 HTML 常量 `BUILTIN_KEY` 粘贴一个模型密钥，`localStorage` 限制每浏览器每天 N 次（如 3）软上限。注意密钥写 HTML 会被源码看到、清缓存可绕过 = 仅挡普通刷量。
  3. 超限引导：关注公众号/加微信解锁（实质线索收集，无后端也能"解锁"提示）。
  - 阈值：日配额计数用 `localStorage` 的 `{date, used}`，跨日归零；`updateQuotaTag()` 显示剩余。
- **真要变现（收钱进账）→ 才用本 skill 的付费后端**，且需先确认用户有商户号 + HTTPS 备案域名。
- 关键合规点：已有 ICP 备案 = 非经营性；只要"不收费"就不触发经营性 ICP 许可证，可放心挂免费 AI 工具（如省团官网）。

## 架构（4 层）
1. 前端免费路径：本地模板即时出稿（不联网、无成本、引流）。
2. 前端付费入口：点"一键AI生成" → 若无令牌 → 调 `/api/order/create` 下单 → 支付 → 收令牌（存 localStorage）→ 凭令牌调 `/api/ai-profile`。
3. 服务端网关：每个真AI调用**必须**校验令牌有效 + 剩余次数>0，调用后 `remaining-=1`；无令牌/次数耗尽 → 403。
4. 大模型：OpenAI 兼容端点（`OPENAI_BASE_URL/API_KEY/MODEL`），密钥只放服务端 `.env`。

## 必建接口
- `GET /api/config` → `{pricePerCall, mode, packs[], byoEnabled}`（前端价格/套餐从服务端读，避免硬编码不一致）
- `POST /api/order/create` → `{pack}` → 建订单 `{id,amount,count,status:pending}`
- `POST /api/order/confirm`（dev）或 `POST /api/order/notify`（微信/支付宝异步回调）→ 校验后置 `status:paid` 并发令牌 `{remaining:count, expireAt?}`
- `GET /api/me?token=` → `{remaining, valid}`
- `POST /api/ai-profile` → `{token, form}` → 校验 → 调 LLM → `{profile, tags, remaining}`
- `GET /` 静态托管前端（生产同源，前端 `API_BASE=''`）

## 零依赖要点（Node 18+ 直接 node server.js）
- 用内置 `http`/`crypto`/`fs`，不引 Express（避免 npm install / 原生编译）。
- JSON 文件做存储（store.js），生产换 SQLite/Redis。
- 极简 `.env` 解析（不引 dotenv）。
- CORS：`Access-Control-Allow-Origin: *`（生产收紧到自有域名）。

## 本地跑通（无需真实密钥）
- `.env` 设 `PAY_MODE=dev` + `DEV_MOCK_LLM=1` → 支付走"模拟支付"按钮、LLM 走占位输出，可端到端验证下单/令牌/扣次链路。
- 配真实 `OPENAI_API_KEY` 后即真实模型。

## 上线硬门槛（交付前必须向用户确认）
1. **支付商户号**：微信支付需企业/个体户商户号 + APIv3 密钥 + 证书（回调验签）。用户是贵州省团之家智付科技有限公司（有限公司，可开）。
2. **HTTPS + 已备案域名**：微信/支付宝回调必须 HTTPS；用户已有 ICP 黔ICP备2026015841号-1、域名 省团.cn。
3. **部署**：宝塔/Nginx 反代 + `pm2` 守护；`.env` 填真实密钥；`/api/order/notify` 实现签名校验 + 幂等 + 发令牌。

## 定价建议（默认）
- 标准单次 ¥0.3（单次模型成本约 ¥0.02–0.05，毛利率>80%）；首单体验 ¥0.1；次数包 ¥1/5次、¥3/20次、¥9.9/月卡。
- 理由：本类工具多为获客漏斗非利润中心；¥0.3 是"随手付得起、不显廉价"甜点；小额每笔都走一次支付确认有摩擦，故配包量降支付次数、锁客单。

## 防绕过
- 真AI 一律服务端出，前端无法伪造（密钥不在前端）。
- 令牌一次性扣次 + 可设过期；订单幂等，回调重复不重复发令牌。
- 监控：单 IP/令牌异常高频调用加限流。

## 参考实现
`F:\Work_Buddy\门店AI档案生成器\server/`：server.js / store.js / .env.example / package.json（门店AI档案生成器已落地此模式并冒烟通过）。
