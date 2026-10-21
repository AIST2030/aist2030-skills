# AIST2030免费模型 渠道目录（2026-10-21 全渠道体检版）

> 本表由 `gateway/health_check.py` 一次并发体检全部渠道得出，直接反映各渠道当前真实状态。
> 想随时复核：跑 `python gateway/health_check.py`。

## ✅ 当前真正可用（3 家）

| 渠道 | 端点 | 推荐模型 | 实测延迟 | 免费额度 | 领Key地址 |
|---|---|---|---|---|---|
| 硅基流动 siliconflow | api.siliconflow.cn/v1 | THUDM/GLM-4-9B-0414 | 0.3s | 9B 以下免费（需实名） | siliconflow.cn |
| 智谱 bigmodel | open.bigmodel.cn/api/paas/v4 | glm-4-flash / glm-4v-flash | 0.5~1.5s | glm-4-flash 免费 | open.bigmodel.cn |
| 美团 LongCat | api.longcat.chat/openai/v1 | LongCat-2.0 | 1.2~2s | 新用户千万 Token | longcat.chat |

> 智谱与美团 LongCat 都**必须**带 `thinking:{"type":"disabled"}`，否则思考会吃光 max_tokens 导致正文为空。网关已默认带上。

## ⚠️ 当前不可用（8 家 · 恢复条件见下表）

| 渠道 | 当前状态 | 恢复条件 |
|---|---|---|
| OpenRouter | 每日 50 次额度已用尽（429） | 次日 08:00 自动恢复；网关已冷却到重置时刻 |
| DeepSeek | 402 余额不足 | 充值后自动归队（优先级 8） |
| 阿里云百炼 dashscope | 400 账号状态异常/欠费 | 充值后自动归队（优先级 40） |
| 阿里云百炼 dashscope-long | 同上 | 同上（优先级 41） |
| 中国移动 MoMA | 402 无可用套餐 | 控制台「订购模型管理」订阅免费套餐（优先级 42） |
| 小米 MiMo | 402 余额不足 | 试用额度耗尽，需充值（优先级 43） |
| 百度千帆 qianfan | 403 账号逾期 | 充值后自动归队（优先级 44） |
| 火山 volcengine | 404 模型名无效 | 需修正 defaultModel 的模型名（优先级 45） |

**熔断策略说明**
- 账号级错误（欠费/余额/额度用尽）→ 长冷却（默认 30 分钟），到期自动归队，无需手动干预
- 每日额度型限流（OpenRouter）→ 冷却到当天重置时刻，不会每 5 分钟空刷
- 瞬时错误（超时/网络抖动）→ 只软降权、不熔断，避免误伤主力渠道

## 🖼️ 视觉模型

当前**唯一稳定可用**的是 `glm-4v-flash`（智谱，实测识图准确、响应 0.5s）。

OpenRouter 的 `nvidia/nemotron-3.5-super-vl:free` 也能识图，但受每日 50 次额度限制，仅作备用。

## 📊 问题分类 → 模型映射（与网关同源）

| 问题类型 | 首选模型 | 说明 |
|---|---|---|
| 技术 / 代码 | Qwen/Qwen2.5-7B-Instruct | 硅基，代码与结构化输出强，0.25s |
| 创意 / 文案 | glm-4-flash | 智谱，中文语言表现力好 |
| 业务 / 长文 | LongCat-2.0 | 美团，12.5 万字长上下文 |
| 数据 / 分析 | THUDM/GLM-4-9B-0414 | 硅基，综合最快，逻辑准确 |
| 闲聊 / 通用 | auto（网关智能调度） | 自动挑最快可用渠道 |

> ★ 分类结果只用于**排序偏好**，绝不收窄候选集——首选渠道欠费/限流时自动退到下一家健康的。
> ★ 偏好只在健康主池（priority ≤ 10）内部提升，避免把已欠费的沉底渠道顶到第一位。

## 调度参数（已调优）

- `GW_RACE_TOP=2`：并发赛马前 2 家，谁快用谁
- `bigmodel.timeoutMs=20000` / `siliconflow=20000` / `deepseek=20000` / `longcat=40000`：放宽超时，避免排队时误判失败
- `GW_CB_ACCOUNT_COOLDOWN_MS=1800000`：账号级错误冷却 30 分钟
- `GW_CB_DAILY_COOLDOWN_MS=72000000`：每日额度型限流冷却 20 小时

## 💀 已确认失效/臆造端点（勿用）

| 渠道 | 原因 |
|---|---|
| moma.10086.cn | DNS 无法解析（端点写错） |
| mimo.xiaomi.com | 返回 HTML 网页，非 API 端点 |
| longcat.meituan.com | DNS 无法解析（端点写错） |
| github-models | 假通道（200 返回 "OK"） |
| tencent-hunyuan (tencent-hunyuan.api) | 端点不存在 |
