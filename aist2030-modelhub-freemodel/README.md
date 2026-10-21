# 全网免费自定义模型 · 网关配置

> 调研与配置日期：2026-10-18 ｜ 最后更新：2026-10-21 ｜ 品牌标识：AIST2030
> 一句话：把智谱、硅基流动、OpenRouter、Gemini、Groq 等 11 家免费渠道，聚合成**一个** OpenAI 兼容接口。你的工具只填一次地址，`model` 写 `auto`，哪家限流/挂了自动切下一家，全程 0 元。

## 📖 只想知道"怎么用"？看这里

| 你想做的事 | 去哪 |
|---|---|
| 知道该用哪个模型、请求怎么写、报错了怎么办 | **[`调用规则.md`](调用规则.md)**（人读） 或 `curl http://127.0.0.1:8787/usage-rules`（AI 读，同一真源） |
| 填 Key、开停渠道、看熔断状态、在线试聊 | 双击 **`control-panel.html`**（面板里也有「调用规则」区，展开即读） |
| 一键看清所有渠道能不能用、为什么不能用 | `python health_check.py` |

> **一句话原则**：绝大多数情况 `model="auto"` 就够；只有要识图、要超长文、要固定模型做对比时才点名指定。
> **当前真正可用的只有 3 家**：硅基流动（0.3s 最快）｜智谱 GLM（0.5~1.5s，`glm-4v-flash` 可识图）｜美团 LongCat（1.2~2s，12.5 万字长文）。其余 7 家是账号额度问题，**已自动沉底，充值后无需改配置**。

---

## 一、这堆文件是干嘛的

| 文件 | 作用 | 要不要改 |
|---|---|---|
| `gateway.js` | 网关本体（零依赖 Node，18+ 直接跑） | 不用改 |
| `models.json` | 全网免费模型路由表（11 家渠道 + 优先级） | 按需改 `enabled` |
| **`usage-rules.json`** | **调用规则真源**：选型决策树 / 请求写法 / 报错对照 / 代码示例 | 改规则改这里 |
| **`调用规则.md`** | **给人看的调用规则**（人读版，与上面同一份数据） | 不用改 |
| `.env.example` | 密钥模板（备查） | 一般不用——直接在面板里填 Key |
| **`start-gateway.bat`** | **双击启动网关**（黑窗口保持开着 = 运行中，关了 = 停止） | 不用改 |
| **`control-panel.html`** | **双击打开控制面板**：网关状态灯 / **在线填 Key（保存即生效）** / 渠道就绪表 / **调用规则区** / 测试对话 | 不用改 |
| `health_check.py` | 一键体检所有渠道，看清哪几家能用、为什么不能用 | 不用改 |
| `smoke_test.sh` | 一键冒烟（不用真 Key 也能验证链路） | 不用改 |

架构就一句话：

```
你的工具（CourseRec/PDFToolbox/官网/ Cherry Studio……）
   │  POST http://127.0.0.1:8787/v1/chat/completions   model=auto
   ▼
免费模型网关 gateway.js
   │ 按 priority 依次试：智谱 → 硅基流动 → 百炼 → 方舟 → ……
   │ 429/401/超时 → 自动切下一家（冒烟实测通过）
   ▼
各家免费大模型（密钥只在网关 .env 里，前端永远看不到）
```

---

## 二、三步跑起来（技术小白版）

### 第 1 步：注册领 Key（只领前两家就够用）

按「注册地址 → 免费额度」表操作，**手机号注册即可，都不用绑卡**：

| 优先级 | 平台 | 注册地址 | 免费拿到什么 | 耗时 |
|---|---|---|---|---|
| 1 | 智谱 BigModel | open.bigmodel.cn | 新户 2000 万 Token + GLM-4.7-Flash **永久免费**（200K 上下文） | 3 分钟 |
| 2 | 硅基流动 | cloud.siliconflow.cn | 新户 2000 万 Token + 9B 以下模型**永久免费** | 5 分钟（要实名） |
| 3 | 阿里云百炼 | bailian.console.aliyun.com | 每个模型 100 万 Token（90 天） | 3 分钟 |
| 4 | 火山方舟 | console.volcengine.com/ark | 每天 200 万 Token，次日重置 | 5 分钟 |
| 5 | 百度千帆 | console.bce.baidu.com/qianfan | ERNIE-Speed 永久免费（50 QPS） | 3 分钟 |
| 6 | DeepSeek | platform.deepseek.com | 新户约 100 万 Token（30 天） | 2 分钟 |
| 7 | OpenRouter | openrouter.ai | 17+ 个 `:free` 模型，50 次/天 | 2 分钟 |
| 8 | Google AI Studio | aistudio.google.com | Gemini 免费层（需海外网络） | 2 分钟 |
| 9 | Groq | console.groq.com | 每天约 6000 次，极速（需海外网络） | 2 分钟 |
| 10 | GitHub Models | github.com/marketplace/models | PAT 即可，每天 150+ 次 | 3 分钟 |
| 11 | Ollama（本地） | ollama.com 下载安装 | 完全免费无限流，数据不出本机 | 10 分钟 |

> 智谱注册后在「API Keys」页创建密钥；硅基流动在「账户 → AccessKey」创建。Key 形如 `xxx.yyy` 的一长串，复制下来。

### 第 2 步：填 Key（推荐在面板里填，保存即生效）

1. 双击 `start-gateway.bat` 启动网关（先启动，面板才连得上）
2. 双击 `control-panel.html` 打开面板，找到「Key 管理台」
3. 每家渠道一行：粘贴 Key → 点「保存」→ 按钮变绿、状态变「就绪」，**立即生效不用重启**
4. 没领的平台留空即可，网关自动跳过

> 备选：也可以把 `.env.example` 复制成 `.env` 用记事本编辑（效果相同，但改完要重启网关才生效）。

### 第 3 步：启动 + 自检（推荐鼠标操作，零命令）

**日常使用（推荐）**：双击文件夹里的 `start-gateway.bat`，弹出黑窗口、显示「免费模型网关已启动」即可，窗口保持开着。

**想看状态 / 测对话**：双击 `control-panel.html`，全部按钮操作。

**命令行方式（备选）**：

```bash
# 一键冒烟（不用真 Key，先验证网关本身没坏）
bash smoke_test.sh

# 正式启动（真实调用）
node gateway.js
```

看到 `已就绪渠道: bigmodel, siliconflow, ...` 就成功了。然后任何工具把下面三项指过来就行：

| 配置项 | 值 |
|---|---|
| Base URL / 接口地址 | `http://127.0.0.1:8787/v1` |
| API Key | 随便填，如 `sk-free`（网关自己管真 Key） |
| 模型 | `auto`（自动调度）或具体模型名如 `glm-4.7-flash` |

** curl 快速验证：**

```bash
curl -X POST http://127.0.0.1:8787/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer sk-free" \
  -d '{"model":"auto","messages":[{"role":"user","content":"用一句话介绍省团之家"}]}'
```

---

## 三、三种用法（按需选）

1. **`model: "auto"`** —— 什么都不想管，网关按优先级自动挑，限流自动换。日常首选。
2. **`model: "glm-4.7-flash"`** —— 锁定某个模型（跑固定文案、保证输出风格一致时用）。
3. **`model: "bigmodel:glm-4.7-flash"`** —— 锁定某家渠道（测试某家是否还活着时用）。

**流式输出**：请求体加 `"stream": true`，网关 SSE 透传，前端可直接用 EventSource 那套接。

---

## 三-B、接入 WorkBuddy 本体（本机已配好）

WorkBuddy 客户端支持「自定义模型（OpenAI 兼容）」，本机 `~/.workbuddy/models.json` 已追加两条网关入口（详见同目录《WorkBuddy接入.md》）：

| 下拉显示名 | model 填 | 说明 |
|---|---|---|
| AIST2030免费模型(auto自动调度) | `auto` | 日常对话，自动调度 |
| 免费GLM-4.7-Flash(智谱) | `glm-4.7-flash` | Agent 重活（支持工具调用） |

前提：网关起着（双击 `start-gateway.bat`），已在面板「Key 管理台」填了至少一个 Key。

---

## 四、接入你自己的工具

### Cherry Studio / LobeChat / ChatBox 等客户端
- 设置 → 模型服务商 → 选「OpenAI」→ API 地址填 `http://127.0.0.1:8787/v1`，Key 随便填，模型填 `auto`。

### 自己的 Python 工具（CourseRec / PDFToolbox 等）
```python
from openai import OpenAI
client = OpenAI(base_url="http://127.0.0.1:8787/v1", api_key="sk-free")
r = client.chat.completions.create(
    model="auto",
    messages=[{"role": "user", "content": "把这段文字改成小红书风格：……"}]
)
print(r.choices[0].message.content)
```

### 想给线上产品用（不止本机）
把 `.env` 里 `PORT=8787` 留着，用 Nginx 反代 + HTTPS，前端 `API_BASE` 指向你的域名即可——密钥始终只在服务端 `.env`，和现有「AI 付费后端」的防绕过思路一致。

### 已有 one-api / new-api？
`models.json` 就是渠道导入素材：每家一条渠道（类型选 OpenAI，Base URL 填表里的 `baseUrl`，模型名填 `models` 数组），网关方案可与之二选一，也可网关挂在一角做兜底。

---

## 五、避坑清单（2026-10 实测口径）

| 坑 | 说明 |
|---|---|
| 智谱旧模型 ID | `glm-4.5-flash` 已下线，勿用；统一用 `glm-4.7-flash` |
| 硅基流动必须实名 | 2026 年 5 月起不实名拿不到额度 |
| 火山方舟要手动开通模型 | 注册后不在控制台点开通，调用直接失败 |
| OpenRouter 免费名单会轮换 | 7 月的 `gpt-oss-120b`、`GLM-4.5-Air` 已转付费；构建前先查官网 live 列表 |
| 免费层数据可能被用于训练 | OpenRouter 部分提供方、Google（欧盟外）会拿 prompts 改进产品；**涉及客户数据/密码的活别走免费渠道** |
| 免费层限流是硬卡 | 个人工具/原型随便用；要上生产流量，该付费还是付费（DeepSeek 约 ¥1/百万 Token 是便宜的兜底） |
| Key 安全 | Key 只进 `.env`，别提交 git、别写进前端、别发群 |
| 百度千帆非标路径 | 若 404，说明该渠道要走官方 SDK 而非 OpenAI 兼容路径，把 `models.json` 里它的 `enabled` 改 false 即可 |

---

## 六、常见问题

**Q：一家都没领，能跑吗？**
能。`bash smoke_test.sh` 走 MOCK 模式验证链路；再把 Ollama 装上（`enabled` 改 true、`OLLAMA_API_KEY=ollama`），就得到一个永远可用的本地兜底。

**Q：auto 会把敏感数据发给海外吗？**
会按优先级先走国内渠道。介意的话把 `models.json` 里海外渠道 `enabled` 设 `false`，只留国内 + Ollama。

**Q：想加新渠道？**
在 `models.json` 的 `providers` 数组里加一条：`{id, label, baseUrl, apiKeyEnv, priority, models[]}`，重启网关即可，代码不用动。

**Q：两台电脑要用？**
网关跑在一台常开机的电脑上，另一台把 Base URL 从 `127.0.0.1` 改成那台的局域网 IP（如 `http://192.168.1.5:8787/v1`）。

---

*配置快照日期 2026-10-18，各平台免费政策随时可能调整，以官网最新公告为准。*
