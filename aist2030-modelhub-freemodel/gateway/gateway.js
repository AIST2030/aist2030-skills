#!/usr/bin/env node
/**
 * 免费模型网关 gateway.js —— 零依赖 Node 18+ 直接运行
 * 作用：把 models.json 里全网免费模型聚合成一个 OpenAI 兼容端点。
 *   - model 填 "auto"（或缺省）→ 按 priority 依次尝试，429/401/超时自动切下一家
 *   - model 填具体模型名（如 glm-4.7-flash）→ 只路由到提供该模型的渠道
 *   - model 填 "渠道id:模型名"（如 bigmodel:glm-4.7-flash）→ 锁定渠道
 *   - stream:true 时 SSE 透传
 * 冒烟：MOCK_MODE=1 node gateway.js（不发任何上游请求，本地占位返回）
 */
'use strict';

const http = require('http');
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');
const { classifyQuestion } = require('./question-classifier');

const DIR = __dirname;
// .env 路径：默认本目录 .env；GW_ENV_FILE 可指定别处（冒烟测试隔离用，不碰真实 .env）
const ENV_FILE = process.env.GW_ENV_FILE || path.join(DIR, '.env');
// 环境变量优先级：shell/系统环境变量打底，.env 文件覆盖（便于本地固定配置）
const ENV = { ...process.env, ...loadEnv(ENV_FILE) };
const PORT = parseInt(ENV.PORT || '8787', 10);
const CFG = JSON.parse(fs.readFileSync(path.join(DIR, 'models.json'), 'utf8'));
// 调用规则（怎么选模型 / 怎么写请求 / 报错怎么办）：独立文件，供 GET /usage-rules 与控制面板读取。
// 规则与渠道配置分离——换血改 usage-rules.json，加渠道改 models.json。
// 文件缺失或解析失败都不影响网关启动（规则只是给人看的）。
let USAGE_RULES = null;
try {
  USAGE_RULES = JSON.parse(fs.readFileSync(path.join(DIR, 'usage-rules.json'), 'utf8'));
} catch (e) {
  console.warn('[gateway] usage-rules.json 读取失败（不影响运行）:', e.message);
}
const MOCK_MODE = ENV.MOCK_MODE === '1';
const MOCK_FAIL_FIRST = parseInt(ENV.MOCK_FAIL_FIRST || '0', 10); // 冒烟用：前 N 个候选渠道模拟 429
const UPSTREAM_TIMEOUT_MS = parseInt(ENV.UPSTREAM_TIMEOUT_MS || '60000', 10);
// 赛马模式：auto 时并发打前 N 家，谁先成功用谁（默认 2 家）。设 0 或 1 关闭。
const RACE_TOP = parseInt(ENV.GW_RACE_TOP || '2', 10);
// 健康主池的 priority 上限：priority > 此值的渠道视为"沉底/待充值"，不参与偏好提升
const ACTIVE_POOL_MAX = parseInt(ENV.GW_ACTIVE_POOL_MAX || '10', 10);
// 每日额度型限流（OpenRouter free-models-per-day）的兜底冷却：默认 20 小时
const CB_DAILY_COOLDOWN_MS = parseInt(ENV.GW_CB_DAILY_COOLDOWN_MS || '72000000', 10);
// 瞬时错误状态码：超时/限流之外的抖动，只记失败不开熔断
const TRANSIENT_STATUS = new Set([408, 500, 502, 503, 504]);
// 小 max_tokens 补救阈值：客户端给的 max_tokens 低于此值且正文为空时，自动放大重试
const MIN_TOKENS_FOR_RETRY = parseInt(ENV.GW_MIN_TOKENS_RETRY || '512', 10);
const VERBOSE = ENV.VERBOSE === '1';

// ---------- 工具 ----------

function loadEnv(file) {
  const out = {};
  if (!fs.existsSync(file)) return out;
  for (const line of fs.readFileSync(file, 'utf8').split(/\r?\n/)) {
    const m = line.match(/^\s*([A-Z0-9_]+)\s*=\s*(.*)\s*$/);
    if (m && !line.trim().startsWith('#')) out[m[1]] = m[2].replace(/^["']|["']$/g, '');
  }
  return out;
}

/** Key 脱敏：保留前 6 后 4，中间打码（面板展示用，绝不回传完整 Key） */
function maskKey(v) {
  if (!v) return '';
  if (v.length <= 10) return v.slice(0, 2) + '****' + v.slice(-2);
  return v.slice(0, 6) + '****' + v.slice(-4);
}

/** 写操作只允许本地面板发起：file:// 页面 Origin 为 null，其余（恶意网页）一律 403 */
function isLocalOrigin(req) {
  const o = req.headers.origin;
  if (!o || o === 'null') return true; // file:// 双击打开的面板
  return /^https?:\/\/(127\.0\.0\.1|localhost)(:\d+)?$/i.test(o);
}

/** 把 KEY=value 原子写入 .env（存在则改行，不存在则追加），返回写入后的值 */
function upsertEnvFile(envName, value) {
  const lines = fs.existsSync(ENV_FILE)
    ? fs.readFileSync(ENV_FILE, 'utf8').split(/\r?\n/)
    : ['# ===== 免费模型网关 .env（由控制面板自动生成，也可用记事本编辑）====='];
  const re = new RegExp('^\\s*' + envName.replace(/[.*+?^${}()|[\]\\]/g, '\\$&') + '\\s*=');
  let found = false;
  const next = lines.map((l) => {
    if (re.test(l) && !l.trim().startsWith('#')) { found = true; return envName + '=' + value; }
    return l;
  });
  if (!found) {
    while (next.length && next[next.length - 1].trim() === '') next.pop();
    next.push(envName + '=' + value);
  }
  const tmp = ENV_FILE + '.tmp';
  fs.writeFileSync(tmp, next.join('\r\n') + '\r\n', 'utf8');
  fs.renameSync(tmp, ENV_FILE); // 原子替换，防止写一半损坏
  return value;
}

/** 渠道启停：改 models.json 的 enabled 字段并热更新内存 CFG，用于控制面板勾选 */
function setProviderEnabled(providerId, enabled) {
  const p = CFG.providers.find((x) => x.id === providerId);
  if (!p) return { ok: false, error: '未知渠道: ' + providerId };
  p.enabled = !!enabled;                      // ① 内存热更新，立即生效，无需重启
  try {
    const tmp = path.join(DIR, 'models.json') + '.tmp';
    fs.writeFileSync(tmp, JSON.stringify(CFG, null, 2), 'utf8'); // ② 落盘持久化
    fs.renameSync(tmp, path.join(DIR, 'models.json'));
  } catch (e) {
    return { ok: false, error: '写入 models.json 失败: ' + String(e.message || e) };
  }
  return { ok: true, id: p.id, enabled: p.enabled, defaultModel: p.defaultModel };
}

function log(...a) { if (VERBOSE) console.log('[gw]', new Date().toISOString(), ...a); }

// CORS：WorkBuddy/CodeBuddy 等 Electron 客户端以浏览器安全策略发起请求，必须放行
const CORS = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
  'Access-Control-Allow-Headers': '*',
  'Access-Control-Max-Age': '86400',
};

function jsonRes(res, status, obj) {
  const body = JSON.stringify(obj);
  res.writeHead(status, { 'Content-Type': 'application/json; charset=utf-8', ...CORS });
  res.end(body);
}

function readBody(req) {
  return new Promise((resolve, reject) => {
    let data = '';
    req.on('data', (c) => {
      data += c;
      if (data.length > 10 * 1024 * 1024) { reject(new Error('body too large')); req.destroy(); }
    });
    req.on('end', () => resolve(data));
    req.on('error', reject);
  });
}

function mockChatCompletion(body) {
  return {
    id: 'chatcmpl-mock-' + crypto.randomBytes(6).toString('hex'),
    object: 'chat.completion',
    created: Math.floor(Date.now() / 1000),
    model: body.model || 'mock',
    choices: [{
      index: 0,
      message: { role: 'assistant', content: `【MOCK】收到 ${(body.messages || []).length} 条消息，模型 ${body.model}。这是本地占位输出，用于验证网关路由链路。` },
      finish_reason: 'stop',
    }],
    usage: { prompt_tokens: 0, completion_tokens: 0, total_tokens: 0 },
  };
}

// ---------- 熔断（Circuit Breaker）----------
/**
 * 为什么需要：免费渠道天然不可控 —— Key 过期、额度耗尽、限流、偶发 5xx、
 * 甚至有渠道 HTTP 200 但返回 "OK" 假成功。没有熔断时，一个死渠道会被
 * 每句话都试一遍，把整体响应拖到几秒；有熔断后它会被临时摘除，冷却结束再自动归队。
 */
const CB_THRESHOLD = parseInt(ENV.GW_CB_THRESHOLD || '3', 10);          // 连续失败几次触发
const CB_COOLDOWN_MS = parseInt(ENV.GW_CB_COOLDOWN_MS || '60000', 10);  // 常规冷却
const CB_RATE_COOLDOWN_MS = parseInt(ENV.GW_CB_RATE_COOLDOWN_MS || '300000', 10); // 429 限流冷却更久
// 账号级错误（欠费/余额不足/订阅过期）冷却更久：这些靠重试是治不好的，
// 必须等用户充值/订购。若只用 60s 冷却，每分钟都会白打一次必然失败的请求。
const CB_ACCOUNT_COOLDOWN_MS = parseInt(ENV.GW_CB_ACCOUNT_COOLDOWN_MS || '1800000', 10); // 30 分钟
const ACCOUNT_ERR_STATUS = new Set([400, 402, 403]); // 欠费 Arrearage / 余额不足 / 账号异常
const breaker = new Map(); // id -> { fails, until, lastError, calls, totalFails, lastOk }

function cbState(id) {
  let s = breaker.get(id);
  if (!s) {
    s = { fails: 0, until: 0, lastError: '', calls: 0, totalFails: 0, lastOk: 0 };
    breaker.set(id, s);
  }
  return s;
}
/** 是否处于熔断冷却中 */
function isOpen(id) {
  const s = breaker.get(id);
  return !!(s && s.until && Date.now() < s.until);
}
/** 剩余冷却秒数 */
function cbRemaining(id) {
  const s = breaker.get(id);
  return s && s.until > Date.now() ? Math.ceil((s.until - Date.now()) / 1000) : 0;
}
function recordOk(id) {
  const s = cbState(id);
  s.calls++; s.fails = 0; s.until = 0; s.lastError = ''; s.lastOk = Date.now();
}
function recordFail(id, status, err) {
  const s = cbState(id);
  s.calls++; s.fails++; s.totalFails++;
  s.lastError = String(err || status || '').slice(0, 200);
  // ★ 错误分级：瞬时错误（超时/网络抖动/5xx）不该把渠道硬熔断。
  //   实测教训：bigmodel timeoutMs=6000 太紧，智谱排队时正常响应被误判为失败，
  //   连续 3 次就把主力渠道熔断 60 秒 → 用户点名的 glm-4-flash 直接 503 用不了。
  //   正确做法：瞬时错误只记失败（软降权，不开熔断），下次照常再试；
  //   只有"确定性失败"（欠费/余额不足/模型下线/额度用尽）才开熔断。
  const transient = TRANSIENT_STATUS.has(status) || /timeout|ECONNRESET|ECONNREFUSED|socket hang up|fetch failed|network/i.test(s.lastError);
  if (transient) {
    s.softFails = (s.softFails || 0) + 1;
    log('soft fail (no circuit)', { provider: id, status, reason: s.lastError });
    return; // 不开熔断
  }
  if (s.fails >= CB_THRESHOLD) {
    let cd = CB_COOLDOWN_MS;
    if (status === 429) cd = CB_RATE_COOLDOWN_MS;
    else if (ACCOUNT_ERR_STATUS.has(status)) cd = CB_ACCOUNT_COOLDOWN_MS;
    // ★ 每日额度耗尽（OpenRouter free-models-per-day）→ 冷却到当天重置时刻，
    //   而不是每 5 分钟重试一次（那样只是白刷 429，还会让熔断反复开关）。
    if (status === 429 && /free-models-per-day|daily|per_day|quota.*day/i.test(s.lastError)) {
      const resetAt = parseDailyReset(s.lastError);
      cd = resetAt ? Math.max(cd, resetAt - Date.now()) : CB_DAILY_COOLDOWN_MS;
    }
    s.until = Date.now() + cd;
    s.fails = 0; // 重置连续计数：冷却结束后重新累计
    s.softFails = 0;
    log('circuit open', { provider: id, cooldownSec: Math.round(cd / 1000), reason: s.lastError });
  }
}

/**
 * 从 429 错误体里解析"每日额度重置时刻"（毫秒时间戳）。
 * OpenRouter 的错误体里带 X-RateLimit-Reset 头（毫秒），形如 1792627200000。
 * 解析不到就返回 0，交由调用方用默认长冷却。
 */
function parseDailyReset(errText) {
  const m = /X-RateLimit-Reset"?\s*[:=]\s*"?(\d{10,13})"?/i.exec(errText || '');
  if (!m) return 0;
  let ts = parseInt(m[1], 10);
  if (ts < 1e12) ts *= 1000; // 秒 → 毫秒
  return ts > Date.now() ? ts : 0;
}

/**
 * 统计 SSE 分片里"用户能看见的正文"字符数（工厂函数：每个流独立缓冲，避免并发串流）。
 * 目标：识别"流式跑完了但一个字都没吐"的空回复。
 * 实现要点：
 *  - SSE 每行形如 data: {...}，一行可能跨 TCP 分片，所以按 \n 切分，
 *    把不完整的尾行留到下一片再解析。
 *  - 只取 choices[0].delta.content 的长度；reasoning / reasoning_content 不算
 *    （那是模型的思考过程，用户看不见，客户端也不会显示）。
 *  - 解析失败（分片截断在 JSON 中间）就跳过该行，不影响计数正确性。
 */
function makeStreamTextCounter() {
  let buf = '';
  return function count(bufChunk) {
    let visible = 0;
    buf += bufChunk.toString('utf8');
    const lines = buf.split('\n');
    buf = lines.pop() || ''; // 最后一行可能不完整，留到下一片
    for (const line of lines) {
      const t = line.trim();
      if (!t.startsWith('data:')) continue;
      const payload = t.slice(5).trim();
      if (!payload || payload === '[DONE]') continue;
      try {
        const j = JSON.parse(payload);
        const ch = j && j.choices && j.choices[0];
        if (!ch) continue;
        const d = ch.delta || {};
        const c = d.content;
        if (typeof c === 'string') visible += c.trim().length;
        else if (Array.isArray(c)) {
          for (const seg of c) {
            const s = typeof seg === 'string' ? seg : (seg && (seg.text || seg.content)) || '';
            visible += String(s).trim().length;
          }
        }
      } catch (e) {
        // 分片截断导致的 JSON 解析失败：忽略这一行
      }
    }
    return visible;
  };
}

/**
 * 把熔断原因翻译成一句人话。
 * 目的：用户点名某个模型却拿到 502 的时候，要能一眼看懂"为什么不能用、什么时候能用、能换成什么"。
 */
function buildCoolingMessage(model, info) {
  const parts = [];
  for (const it of info) {
    const err = it.lastError || '';
    let why;
    if (/free-models-per-day|per_day|quota.*day/i.test(err)) {
      const h = Math.round((it.remainingSec || 0) / 3600);
      why = `每日免费额度已用尽（约 ${h} 小时后恢复）`;
    } else if (/Arrearage|overdue|欠费|Insufficient Balance|余额不足|1113/i.test(err)) {
      why = '账号余额/资源包不足（需充值或订购套餐）';
    } else if (/429|访问量过大|Rate limit/i.test(err)) {
      why = `上游限流（${Math.ceil((it.remainingSec || 0) / 60)} 分钟后重试）`;
    } else if (/Model disabled|30003/i.test(err)) {
      why = '该模型已被上游下线';
    } else if (err) {
      why = '上游暂时不可用：' + err.slice(0, 80);
    } else {
      why = '上游暂时不可用';
    }
    parts.push(`${it.provider}：${why}`);
  }
  return `模型 ${model} 当前不可用 —— ${parts.join('；')}。`;
}

/**
 * 检测请求体里的中文是否被错误编码（UTF-8 被按 GBK/Latin-1 解读）。
 * 真实场景：某些 Windows 终端用 curl 发中文 JSON 时按 GBK 编码，
 * 上游收到乱码会"认真地回答乱码"（实测出现过答非所问的回复）。
 * 这里做一次启发式检测：出现大量"孤立高位字节转出的拉丁扩展字符"就判定为乱码。
 * 只在检测到疑似乱码时给出提示，不阻断请求（纯 ASCII 请求一律不误判）。
 */
function detectMojibake(text) {
  if (typeof text !== 'string' || !text) return false;
  // 统计"高位异常字符"密度：U+0080~U+1FFF（Latin-1 扩展、希腊/西里尔字母、
  // 修饰字母、箭头等）都是 UTF-8 被按单字节编码后的典型产物。
  // 正常中文都在 U+4E00~U+9FFF，不落在这个区间。
  let sus = 0, total = 0;
  for (const ch of text) {
    const cp = ch.codePointAt(0);
    if (cp < 0x80) continue;      // ASCII 不计入
    total++;
    if (cp <= 0x1fff) sus++;     // 落在可疑区间
    else if (cp >= 0x4e00 && cp <= 0x9fff) continue; // 正常中文，忽略
    else return false;           // 出现正常中文 → 整段大概率不是乱码
  }
  if (total === 0) return false;
  // 密度超过 12% 且至少 3 个可疑字符 → 判定乱码
  return sus >= 3 && sus / total > 0.12;
}

/**
 * 提取正文内容。
 * ★ 不能用 `a || b || c` 串起来取：空字符串 '' 是 falsy，会被短路成 undefined，
 *   于是「content 为空」的错误形态被误判成"字段缺失但有 finish_reason → 合法"，
 *   校验放行 → 用户拿到空回复（2026-10-21 亲历：OpenRouter 免费模型偶发返回空 content）。
 * 这里改为逐字段显式判定，并且把「数组型 content」（部分多模态网关）也拼成字符串。
 */
function extractContent(c) {
  const m = c.message || {};
  const d = c.delta || {};
  let raw;
  if (m.content !== undefined && m.content !== null) raw = m.content;
  else if (d.content !== undefined && d.content !== null) raw = d.content;
  else if (c.text !== undefined && c.text !== null) raw = c.text;
  else return undefined;
  if (Array.isArray(raw)) {
    return raw
      .map((x) => (typeof x === 'string' ? x : (x && (x.text || x.content)) || ''))
      .join('');
  }
  return raw;
}

/**
 * 校验上游响应是否"真可用"（不能只看 HTTP 200）。
 * 血泪教训：①github-models 类假通道返回 200 + 正文 "OK"；
 * ②智谱 glm-4.5-air 默认开深度思考，content 会是空串；
 * ③OpenRouter 免费模型偶发返回空 content（2026-10-21）。
 * 这三种只看 r.ok 都会被当成成功，用户拿到的是空回复。
 */
function validateCompletion(data) {
  if (!data || typeof data !== 'object') return { ok: false, reason: '响应不是对象' };
  if (!Array.isArray(data.choices) || data.choices.length === 0) {
    return { ok: false, reason: '缺少 choices（疑似假通道 200/OK）' };
  }
  const c = data.choices[0] || {};
  const content = extractContent(c);
  if (content === undefined || content === null) {
    return { ok: false, reason: 'choices[0] 无 content 字段（可能开了深度思考，模型只回了 reasoning）' };
  }
  if (typeof content !== 'string') {
    return { ok: false, reason: 'content 类型异常：' + typeof content };
  }
  if (content.trim().length === 0) {
    return { ok: false, reason: 'content 为空串（可能开了深度思考或参数不兼容）' };
  }
  return { ok: true };
}

// ---------- 路由 ----------

/** 返回候选渠道数组（已过滤 enabled + 有 key + 模型匹配 + 未熔断），按 priority 升序 */
function pickCandidates(model, opts) {
  const skipBreaker = !opts || opts.skipBreaker !== false;
  const enabled = CFG.providers.filter((p) => {
    if (p.enabled === false) return false;
    if (!MOCK_MODE && !ENV[p.apiKeyEnv]) return false; // MOCK 冒烟模式不要求 Key
    if (skipBreaker && isOpen(p.id)) return false; // 熔断冷却中：本轮不参与
    return true;
  }).sort((a, b) => (a.priority || 99) - (b.priority || 99));

  if (!model || model === 'auto' || model === 'free') return enabled;

  // "渠道id:模型名" → 锁定渠道
  // ★ 注意：OpenRouter 的模型名自带 ":free" 后缀（如 nvidia/nemotron-3.5-super-vl:free），
  //   不能只凭"含冒号"就当渠道锁 —— 必须确认冒号前缀确实是一个已知渠道 id，
  //   否则 OpenRouter 免费模型会被误判为"锁了一个不存在的渠道"→ 候选为空 → 全部失败。
  if (model.includes(':')) {
    const [pid, mname] = model.split(/:(.+)/);
    const p = enabled.find((x) => x.id === pid);
    if (p) return [p];
    // 前缀不是已知渠道 → 当作普通模型名继续走模型匹配（OpenRouter :free 走这条）
  }

  // 普通模型名 → 找 models 列表包含它的渠道（OpenRouter 的 :free 后缀也按子串兜底匹配）
  return enabled.filter((p) => (p.models || []).some((m) => m === model || model.endsWith(':' + m) || m.endsWith(':' + model)));
}

/**
 * 调一家上游，返回 { ok:true, status, response, provider } 或 { ok:false, status, error, provider }
 * @param {AbortController} [externalAc] 赛马模式由外部统一控制中断
 */
async function callUpstream(p, body, externalAc, preferModel) {
  // 解析发往上游的真实模型名：
  // 1) "渠道id:模型名"（锁定渠道）→ 剥掉渠道前缀
  // 2) auto / free / 空 → 用该渠道的 defaultModel（无则 models[0]），绝不把 "auto" 透传给上游
  // 3) auto + 分类器偏好 → 若该渠道支持偏好模型，优先用偏好模型（更贴合问题类型）
  // 4) 其他具体模型名 → 原样透传（兼容 OpenRouter 动态模型名等场景）
  let upstreamModel = body.model;
  if (typeof upstreamModel === 'string' && upstreamModel.startsWith(p.id + ':')) {
    upstreamModel = upstreamModel.slice(p.id.length + 1);
  } else if (preferModel && Array.isArray(p.models) && p.models.includes(preferModel)) {
    upstreamModel = preferModel;
  } else if (!upstreamModel || upstreamModel === 'auto' || upstreamModel === 'free') {
    upstreamModel = p.defaultModel || (Array.isArray(p.models) && p.models[0]) || 'auto';
  }

  // extraBody = 渠道默认参数（如智谱关深度思考），客户端显式传的字段优先
  const payload = { ...(p.extraBody || {}), ...body, model: upstreamModel };
  if (p.requestStyle === 'plain') delete payload.stream; // 个别渠道不支持流式时按需扩展

  const ac = externalAc || new AbortController();
  const perTimeout = parseInt(p.timeoutMs || UPSTREAM_TIMEOUT_MS, 10);

  const doFetch = async (payload) => {
    const timer = setTimeout(() => ac.abort(), perTimeout);
    try {
      const r = await fetch(p.baseUrl.replace(/\/+$/, '') + '/chat/completions', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': 'Bearer ' + ENV[p.apiKeyEnv],
        },
        body: JSON.stringify(payload),
        signal: ac.signal,
      });
      if (!r.ok) {
        const text = await r.text().catch(() => '');
        return { ok: false, status: r.status, error: text.slice(0, 300) || r.statusText, provider: p.id };
      }
      return { ok: true, status: 200, response: r, provider: p.id };
    } catch (e) {
      const aborted = e.name === 'AbortError';
      return { ok: false, status: aborted ? 504 : 502, error: aborted ? 'upstream timeout' : String(e.message || e), provider: p.id };
    } finally {
      clearTimeout(timer);
    }
  };

  const r = await doFetch(payload);
  if (!r.ok) return r;

  // ★ 空正文自动补救：客户端传了很小的 max_tokens 时，思考型模型（LongCat / 智谱 / Nemotron）
  //   会把预算全花在 reasoning 上，正文为空、finish_reason=length。
  //   实测：LongCat max_tokens=20 → content=null；不传或给足 → 正常。
  //   这里预读一次响应，若判定为"被 max_tokens 截断导致的空正文"，就放大 max_tokens 重打一次。
  if (payload.stream !== true && payload.max_tokens && payload.max_tokens < MIN_TOKENS_FOR_RETRY) {
    try {
      const clone = r.response.clone();
      const data = await clone.json().catch(() => null);
      const v0 = validateCompletion(data);
      const ch0 = data && data.choices && data.choices[0];
      if (!v0.ok && ch0 && (ch0.finish_reason === 'length' || ch0.native_finish_reason === 'length')) {
        const bigger = { ...payload, max_tokens: Math.max(MIN_TOKENS_FOR_RETRY, payload.max_tokens * 8) };
        log('retry with larger max_tokens', { provider: p.id, from: payload.max_tokens, to: bigger.max_tokens });
        const r2 = await doFetch(bigger);
        if (r2.ok) return r2;
      }
    } catch (e) {
      // 预读失败不影响主流程
    }
  }
  return r;
}

/**
 * 赛马模式：并发打前 n 家，第一个成功的采纳，其余立刻中断。
 * 目的：真实网络下"谁快用谁"，而不是死等 priority 第一的慢渠道。
 * 返回 { p, r } 或 null（前 n 家全败）
 */
async function raceCall(cands, body, n, preferModel) {
  const racers = cands.slice(0, n);
  return new Promise((resolve) => {
    let finished = 0;
    let won = false;
    const ctrls = new Map();
    for (const p of racers) {
      const ac = new AbortController();
      ctrls.set(p.id, ac);
      callUpstream(p, body, ac, preferModel)
        .then((r) => {
          if (won) {
            // 已经有人赢了：把自己拿到的响应体丢弃，避免悬挂连接占资源
            if (r.ok && r.response && r.response.body && r.response.body.cancel) {
              try { r.response.body.cancel(); } catch {}
            }
            return;
          }
          if (r.ok) {
            won = true;
            for (const [id, c] of ctrls) if (id !== p.id) { try { c.abort(); } catch {} }
            log('race won', { provider: p.id });
            resolve({ p, r });
          } else {
            // 只有"真的失败"才记；被 abort 的输家走 catch 分支，不算失败
            recordFail(p.id, r.status, r.error);
            finished += 1;
            if (finished === racers.length) resolve(null);
          }
        })
        .catch(() => {
          finished += 1;
          if (!won && finished === racers.length) resolve(null);
        });
    }
  });
}

// ---------- 服务 ----------

const server = http.createServer(async (req, res) => {
  // CORS 预检直接放行（Electron 客户端调用前会先发 OPTIONS）
  if (req.method === 'OPTIONS') {
    res.writeHead(204, CORS);
    return res.end();
  }
  const url = new URL(req.url, 'http://x');
  try {
    if (req.method === 'GET' && (url.pathname === '/health' || url.pathname === '/')) {
      const ready = CFG.providers.filter((p) => p.enabled !== false && (MOCK_MODE || ENV[p.apiKeyEnv])).map((p) => p.id);
      return jsonRes(res, 200, {
        ok: true, mock: MOCK_MODE, port: PORT,
        providersReady: ready,
        providersMissingKey: CFG.providers.filter((p) => !ENV[p.apiKeyEnv]).map((p) => p.id),
        raceTop: RACE_TOP,
        // 熔断状态：面板可据此显示"xx 渠道冷却中（剩余 Ns）"
        circuit: {
          threshold: CB_THRESHOLD,
          cooldownSec: Math.round(CB_COOLDOWN_MS / 1000),
          rateCooldownSec: Math.round(CB_RATE_COOLDOWN_MS / 1000),
          open: [...breaker.entries()].filter(([, s]) => s.until > Date.now())
            .map(([id, s]) => ({ id, remainingSec: Math.ceil((s.until - Date.now()) / 1000), lastError: s.lastError })),
          stats: [...breaker.entries()].map(([id, s]) => ({ id, calls: s.calls, totalFails: s.totalFails, lastError: s.lastError })),
        },
        hint: 'POST /v1/chat/completions  {model:"auto", messages:[...]}',
        // 明确告诉调用方去哪查"该用哪个模型、请求怎么写"——不然只能靠猜
        usageRules: USAGE_RULES
          ? { available: true, endpoint: 'GET /usage-rules', version: USAGE_RULES.version, updated: USAGE_RULES.updated }
          : { available: false, endpoint: 'GET /usage-rules', note: 'usage-rules.json 未配置' },
      });
    }

    if (req.method === 'GET' && url.pathname === '/v1/models') {
      const list = CFG.providers
        .filter((p) => p.enabled !== false && (MOCK_MODE || ENV[p.apiKeyEnv]))
        .flatMap((p) => (p.models || []).map((m) => ({ id: m, object: 'model', owned_by: p.id })));
      return jsonRes(res, 200, { object: 'list', data: [{ id: 'auto', object: 'model', owned_by: 'gateway' }, ...list] });
    }

    // ---- 调用规则：让调用方（人和 AI）能直接查到"该用哪个模型、请求怎么写" ----
    if (req.method === 'GET' && url.pathname === '/usage-rules') {
      if (!USAGE_RULES) {
        return jsonRes(res, 404, {
          error: 'usage-rules.json 不存在或格式错误',
          hint: '规则文件应与 models.json 同目录；修好后重启网关。网关本身不依赖它运行。',
        });
      }
      // 只列真正可路由的模型（配置里写了但渠道没启用的，对调用方是误导）
      const routable = new Set(
        CFG.providers
          .filter((p) => p.enabled !== false && (MOCK_MODE || ENV[p.apiKeyEnv]))
          .flatMap((p) => [p.defaultModel, ...(p.models || [])])
          .filter(Boolean)
      );
      return jsonRes(res, 200, {
        ...USAGE_RULES,
        _gateway: {
          generatedAt: new Date().toISOString(),
          modelsEndpoint: 'GET /v1/models',
          healthEndpoint: 'GET /health',
          // 规则里提到但当前路由不到的模型，明确标出来，避免用户点名后 503
          unavailableModels: (USAGE_RULES.modelPicker || [])
            .map((m) => m.id)
            .filter((id) => id !== 'auto' && !routable.has(id)),
        },
      });
    }

    // ---- Key 管理（控制面板填 Key 用；写操作限本地面板）----
    if (req.method === 'GET' && url.pathname === '/api/keys') {
      const keys = CFG.providers.map((p) => {
        const v = ENV[p.apiKeyEnv];
        return {
          id: p.id, label: p.label, env: p.apiKeyEnv,
          priority: p.priority, enabled: p.enabled !== false,
          tier: p.tier || 'unverified', // core/weak/paid/slow/dead/unverified，面板据此分组打标签
          defaultModel: p.defaultModel,
          configured: !!v, masked: maskKey(v),
          supportsTools: p.supportsTools === true,
        };
      });
      return jsonRes(res, 200, { ok: true, envFile: ENV_FILE, mock: MOCK_MODE, keys });
    }

    // ---- 渠道启停（面板勾选：傻模型/付费/慢/失效渠道默认关，按需开）----
    if (req.method === 'POST' && url.pathname === '/api/providers') {
      if (!isLocalOrigin(req)) {
        return jsonRes(res, 403, { ok: false, error: '仅允许本机控制面板修改渠道开关（Origin 校验未通过）' });
      }
      const raw = await readBody(req);
      let body;
      try { body = JSON.parse(raw || '{}'); } catch { return jsonRes(res, 400, { ok: false, error: 'invalid JSON body' }); }
      const pid = String(body.id || '').trim();
      const want = body.enabled === true || body.enabled === 'true';
      const r = setProviderEnabled(pid, want);
      if (!r.ok) return jsonRes(res, 400, r);
      console.log(`[gw] 渠道已${want ? '启用' : '关闭'}: ${pid}（来自控制面板，已热更新生效）`);
      return jsonRes(res, 200, r);
    }

    if (req.method === 'POST' && url.pathname === '/api/keys') {
      if (!isLocalOrigin(req)) {
        return jsonRes(res, 403, { ok: false, error: '仅允许本机控制面板修改 Key（Origin 校验未通过）' });
      }
      const raw = await readBody(req);
      let body;
      try { body = JSON.parse(raw || '{}'); } catch { return jsonRes(res, 400, { ok: false, error: 'invalid JSON body' }); }
      const envName = String(body.env || '').trim();
      const value = String(body.value || '').trim();
      const allowed = new Set(CFG.providers.map((p) => p.apiKeyEnv));
      if (!allowed.has(envName)) return jsonRes(res, 400, { ok: false, error: `未知的 Key 名称: ${envName}（可用: ${[...allowed].join(', ')}）` });
      if (!value || value.length < 8 || value.length > 500 || /[\r\n]/.test(value)) {
        return jsonRes(res, 400, { ok: false, error: 'Key 长度应在 8-500 字符之间，且不能含换行（注意别粘进了空格/换行）' });
      }
      try {
        upsertEnvFile(envName, value);
      } catch (e) {
        return jsonRes(res, 500, { ok: false, error: '写入 .env 失败: ' + String(e.message || e) });
      }
      ENV[envName] = value; // 热更新：填完 Key 立即生效，无需重启网关
      console.log(`[gw] Key 已保存: ${envName}（来自控制面板，已热更新生效）`);
      return jsonRes(res, 200, { ok: true, env: envName, configured: true, masked: maskKey(value) });
    }

    if (req.method === 'DELETE' && url.pathname === '/api/keys') {
      if (!isLocalOrigin(req)) {
        return jsonRes(res, 403, { ok: false, error: '仅允许本机控制面板修改 Key（Origin 校验未通过）' });
      }
      const envName = String(url.searchParams.get('env') || '').trim();
      const allowed = new Set(CFG.providers.map((p) => p.apiKeyEnv));
      if (!allowed.has(envName)) return jsonRes(res, 400, { ok: false, error: `未知的 Key 名称: ${envName}` });
      try {
        upsertEnvFile(envName, ''); // 清空该行而非删行，保留注释结构
      } catch (e) {
        return jsonRes(res, 500, { ok: false, error: '写入 .env 失败: ' + String(e.message || e) });
      }
      delete ENV[envName];
      console.log(`[gw] Key 已清除: ${envName}（来自控制面板）`);
      return jsonRes(res, 200, { ok: true, env: envName, configured: false });
    }

    if (req.method === 'POST' && url.pathname === '/v1/chat/completions') {
      const raw = await readBody(req);
      let body;
      try { body = JSON.parse(raw || '{}'); } catch { return jsonRes(res, 400, { error: { message: 'invalid JSON body' } }); }

      // 智能调度：根据问题内容自动选择最优模型
      // ★ 关键修复（2026-10-21）：分类结果只是"偏好"，绝不能覆盖用户请求的 model。
      //   旧逻辑 `model = classification.model` 把 auto 降级成具体模型（如 qwen-plus），
      //   连锁后果：isAuto 变 false → pickCandidates 只剩 1 家 → 该家欠费(400)时
      //   直接 break → 硅基/DeepSeek/LongCat 等健康渠道永远轮不到 → 报"全部渠道失败"。
      const requestedModel = body.model || CFG.defaultModel || 'auto';
      const isAutoReq = ['auto', 'free', '', null, undefined].includes(requestedModel);
      let model = requestedModel;
      let preferModel = null;   // 分类器偏好：只影响渠道排序与该渠道的模型名，不收窄候选集
      const wantStream = body.stream === true;

      // ★ 乱码自检：Windows 终端用 curl 发中文 JSON 时常按 GBK 编码，
      //   上游会"认真地回答乱码"。检测到就带上明确警告，便于调用方定位。
      let mojibakeWarn = null;
      try {
        const _probe = (body.messages || []).filter((m) => m && m.role === 'user')
          .map((m) => {
            const c = m.content;
            if (typeof c === 'string') return c;
            if (Array.isArray(c)) return c.filter((x) => x && x.type === 'text').map((x) => x.text || '').join(' ');
            return '';
          }).join('\n');
        if (detectMojibake(_probe)) {
          mojibakeWarn = '检测到请求中的中文疑似编码错误（UTF-8 被按 GBK/Latin-1 解读）。上游会收到乱码，回答可能答非所问。请用 UTF-8 发送 JSON（Python 用 json.dumps(..., ensure_ascii=False).encode("utf-8")）。';
          log('mojibake detected', { sample: _probe.slice(0, 60) });
        }
      } catch (e) { /* 自检失败不影响主流程 */ }

      // 如果是 auto 模式且有用户输入内容，尝试智能分类
      if (isAutoReq && body.messages && body.messages.length > 0) {
        const userMessage = body.messages.find(m => m.role === 'user');
        // 多模态兼容：content 可能是数组([{type:text},{type:image_url}])，提取纯文本再分类
        const _rc = userMessage && userMessage.content;
        const classifyText = typeof _rc === 'string' ? _rc
          : (Array.isArray(_rc) ? _rc.filter(p => p && p.type === 'text').map(p => p.text || '').join(' ') : '');
        if (userMessage && classifyText.trim()) {
          try {
            const classification = classifyQuestion(classifyText);
            preferModel = classification.model;   // ★ 只记偏好，不覆盖 model
            log('smart route', { 
              content: classifyText.substring(0, 50) + (classifyText.length > 50 ? '...' : ''), 
              type: classification.type, 
              model: preferModel, 
              reason: classification.reason 
            });
          } catch (e) {
            log('smart route fail', { error: String(e.message || e), fallback: 'auto' });
          }
        }
      }
      
      let candidates = pickCandidates(model);
      // 记录"因熔断被排除"的渠道（用于给用户一句人话提示，而不是干巴巴的 502）
      let cooledOut = [];
      if (!candidates.length) {
        // 兜底：若所有可用渠道都处于熔断冷却
        const all = pickCandidates(model, { skipBreaker: false });
        if (all.length) {
          cooledOut = all.filter((p) => isOpen(p.id));
          if (isAutoReq) {
            // auto 模式：降级放行（慢总比全灭好），让网关去试一次
            log('breaker bypass', { reason: '全部渠道冷却中，本轮降级放行' });
            candidates = all;
          } else {
            // ★ 用户点名了具体模型：不要偷偷降级到别的模型（那会答非所问），
            //   也不要去空刷已耗尽额度的上游（如 OpenRouter 每日 50 次），
            //   直接如实告知"额度用尽、什么时候恢复、可以改用哪个模型"。
            const info = cooledOut.map((p) => ({
              provider: p.id,
              remainingSec: cbRemaining(p.id),
              lastError: (breaker.get(p.id) || {}).lastError || '',
            }));
            return jsonRes(res, 503, {
              error: {
                code: 'provider_cooling_down',
                message: buildCoolingMessage(model, info),
                providers: info,
                hint: '可用替代：把 model 改成 "auto"（自动选健康渠道），或改用 /v1/models 列表中的其他模型。',
              },
            });
          }
        }
      }
      // ★ 关键修复：auto 模式下，分类器偏好只用来"排序"候选渠道，绝不收窄候选集。
      //   支持偏好模型的渠道排前面（最贴合），其余渠道全部保留作为兜底。
      //   这样即使首选渠道欠费/限流，也能自动退到下一家健康的。
      //   ★ 但只允许在"健康主池"（priority <= ACTIVE_POOL_MAX）内部做提升：
      //   否则偏好模型恰好只挂在已欠费的沉底渠道上（如 qwen-plus→dashscope），
      //   反而会把死渠道顶到第一位，每次调用都先浪费一次。
      if (isAutoReq && preferModel && candidates.length > 1) {
        const supports = (p) => Array.isArray(p.models) && p.models.some((m) => m === preferModel);
        const hit = candidates.filter((p) => supports(p) && (p.priority || 99) <= ACTIVE_POOL_MAX);
        if (hit.length && hit.length < candidates.length) {
          const rest = candidates.filter((p) => !hit.includes(p));
          candidates = [...hit, ...rest];
          log('prefer reorder', { prefer: preferModel, front: hit.map((p) => p.id) });
        }
      }
      if (!candidates.length && !MOCK_MODE) {
        return jsonRes(res, 400, {
          error: {
            message: `无可用渠道：model=${model}。请检查 models.json 的 enabled 与 .env 中的 API Key；GET /v1/models 查看当前可用模型。`,
          },
        });
      }

      // MOCK 冒烟模式（无真实 Key 也返回，用于验证路由链路）
      if (MOCK_MODE) {
        if (!candidates.length) {
          return jsonRes(res, 200, { ...mockChatCompletion(body), _mock: { routed: 'none', note: 'MOCK 模式：models.json 中没有启用的渠道' } });
        }
        const firstFail = candidates.slice(0, MOCK_FAIL_FIRST).map((p) => p.id);
        const chosen = candidates[Math.min(MOCK_FAIL_FIRST, candidates.length - 1)];
        log('mock route', { model, tried: firstFail, chosen: chosen.id });
        return jsonRes(res, 200, { ...mockChatCompletion(body), _mock: { routed: chosen.id, skipped429: firstFail } });
      }

      // 真实路由：依次尝试，可重试错误码自动 fallback
      // 400/402 也纳入可重试：它们在上游语义里是"欠费/余额不足"（账号级问题），
      // 换一家渠道仍可能成功，所以必须继续 fallback 而不是直接放弃。
      const RETRYABLE = new Set([400, 401, 402, 403, 404, 408, 429, 500, 502, 503, 504]);
      const attempts = [];
      // ★ 用"用户原始请求"的语义判定 auto，而不是被分类器改写后的 model
      const isAuto = isAutoReq;

      // 赛马：auto 模式下并发打前 N 家，谁先成功用谁（真正"选最快的"）
      let raced = null;
      let raceLosers = [];
      if (isAuto && RACE_TOP > 1 && candidates.length > 1) {
        raced = await raceCall(candidates, body, RACE_TOP, preferModel);
        if (!raced) {
          // 前 N 家全败：把它们的错误记进 attempts，继续顺序尝试剩余的
          raceLosers = candidates.slice(0, RACE_TOP);
          for (const p of raceLosers) {
            attempts.push({ provider: p.id, status: 'race-lost', error: '赛马未胜出或失败' });
          }
        }
      }
      // ★ 赛马已试过的渠道不再重复调用（避免同一渠道被打两次，浪费时间与配额）
      const rest = raced
        ? candidates.filter((p) => p.id !== raced.p.id)
        : candidates.filter((p) => !raceLosers.includes(p));
      const queue = raced ? [raced.p, ...rest] : rest;
      const preResolved = raced ? raced.r : null;

      for (const p of queue) {
        const r = (preResolved && p === raced.p) ? preResolved : await callUpstream(p, body, null, preferModel);
        if (r.ok) {
          log('routed', { model, to: p.id });
            if (wantStream) {
            // ★ 流式无法预读正文，但可以"边转发边统计"：
            //   统计所有 delta.content 的可见字符数（剥掉 reasoning 字段与 JSON 噪声）。
            //   若整条流下来一个可见字符都没有 → 判定为"空回复"，记失败并让渠道进熔断，
            //   下次调用自动 fallback 到下一家（响应头已发出，无法回退，只能靠熔断兜底）。
            res.writeHead(200, {
              'Content-Type': 'text/event-stream',
              'Cache-Control': 'no-cache',
              'Connection': 'keep-alive',
              'X-Gateway-Provider': p.id,
              ...CORS,
            });
            const reader = r.response.body.getReader();
            let visible = 0;
            const countText = makeStreamTextCounter();
            const pump = async () => {
              while (true) {
                const { done, value } = await reader.read();
                if (done) break;
                const buf = Buffer.from(value);
                visible += countText(buf);
                res.write(buf);
              }
              res.end();
            };
            await pump();
            if (visible === 0) {
              recordFail(p.id, 200, '流式响应无可见正文（空回复）');
              attempts.push({ provider: p.id, status: 200, error: '响应不合法: 流式无可见正文' });
              log('invalid response', { provider: p.id, reason: '流式无可见正文' });
              return; // 已发出响应体，无法再改状态码；靠熔断让下次自动换渠道
            }
            recordOk(p.id);
            return;
          }
          // 非流式：先校验正文再返回（流式无法预读，只能靠健康检查兜底）
          const data = await r.response.json().catch(() => null);
          const v = validateCompletion(data);
          if (!v.ok) {
            // 假成功：HTTP 200 但内容不可用 → 计入熔断，继续试下一家
            recordFail(p.id, 200, v.reason);
            attempts.push({ provider: p.id, status: 200, error: '响应不合法: ' + v.reason });
            log('invalid response', { provider: p.id, reason: v.reason });
            continue;
          }
          recordOk(p.id);
          log('routed', { model, to: p.id });
          if (mojibakeWarn) {
            // 附在响应里（非破坏性），让调用方能一眼看出"回答跑偏是编码问题不是模型问题"
            data._gateway_warnings = [mojibakeWarn];
            data._gateway_provider = p.id;
          }
          return jsonRes(res, 200, data);
        }
        recordFail(p.id, r.status, r.error);
        attempts.push({ provider: p.id, status: r.status, error: r.error });
        log('failover skip', { provider: p.id, status: r.status });
        // 用户锁定了具体模型 → 不可重试错误直接失败（快速反馈）；
        // auto 自动调度 → 无论什么错误都继续试下一家
        if (!isAuto && !RETRYABLE.has(r.status)) break;
      }
      return jsonRes(res, 502, { error: { message: '全部渠道失败', attempts } });
    }

    return jsonRes(res, 404, { error: { message: 'not found' } });
  } catch (e) {
    return jsonRes(res, 500, { error: { message: String(e.message || e) } });
  }
});

server.listen(PORT, () => {
  const ready = CFG.providers.filter((p) => p.enabled !== false && (MOCK_MODE || ENV[p.apiKeyEnv])).map((p) => p.id);
  console.log(`[gw] 免费模型网关已启动: http://127.0.0.1:${PORT}  (mock=${MOCK_MODE ? 'ON' : 'OFF'})`);
  console.log(`[gw] 已就绪渠道: ${ready.length ? ready.join(', ') : '（无——双击 control-panel.html 在面板里填 Key，或编辑 .env）'}`);
  console.log(`[gw] 用法: POST http://127.0.0.1:${PORT}/v1/chat/completions  body={"model":"auto","messages":[{"role":"user","content":"你好"}]}`);
  console.log(`[gw] auto 调度: ${RACE_TOP > 1 ? `赛马模式（并发打前 ${RACE_TOP} 家，谁快用谁；.env 设 GW_RACE_TOP=1 可关闭）` : '顺序模式（按 priority 依次 fallback）'}`);
  console.log(`[gw] 熔断保护: 连续失败 ${CB_THRESHOLD} 次 → 冷却 ${Math.round(CB_COOLDOWN_MS/1000)}s（429 限流 ${Math.round(CB_RATE_COOLDOWN_MS/1000)}s）；HTTP 200 但正文非法（假通道/空 content）同样计入失败`);
  console.log(`[gw] 填 Key: 面板保存后立即生效，无需重启本窗口`);
});
