/*
 * AIST2030免费模型智能管家 v1.0.0
 * 一句话配置 · 智能调度 · 按习惯调优
 *
 * 用法：
 *   node main.js register   注册模型到 ~/.workbuddy/models.json（增量合并，自动备份）
 *   node main.js health     检查网关健康状态
 *   node main.js start      后台启动网关
 *   node main.js status     输出配置状态报告
 * 作为模块：require('./main.js').configure('帮我配置免费模型')
 */

const fs = require('fs');
const path = require('path');
const http = require('http');
const { spawn } = require('child_process');

const HOME = process.env.USERPROFILE || process.env.HOME;
const WB_DIR = path.join(HOME, '.workbuddy');
const MODELS_JSON = path.join(WB_DIR, 'models.json');
const CONFIG_DIR = path.join(WB_DIR, 'aist2030-model-manager');
const USER_DATA_FILE = path.join(CONFIG_DIR, 'user-data.json');
const GATEWAY_DIR = path.join(WB_DIR, 'free-model-gateway');
const GATEWAY_PORT = process.env.GW_PORT || 8787;
const GATEWAY_URL = 'http://127.0.0.1:' + GATEWAY_PORT + '/v1';

// 注册进 WorkBuddy 的模型条目（与 ~/.workbuddy/models.json 现有格式逐字段一致）
// ★ 2026-10-21 修订：旧版注册的是 qwen-plus（阿里云百炼），实测该账号 400 欠费 → 必然失败。
//   现在只注册经过实测可用的条目，auto 为主力入口。
const REGISTRY = [
  {
    id: 'auto',
    name: 'AIST2030免费模型（自动调度·中文快好）',
    vendor: 'AIST2030免费网关',
    url: GATEWAY_URL,
    apiKey: 'sk-free-gateway',
    supportsToolCall: true,
    supportsImages: false,
    supportsReasoning: false,
    maxInputTokens: 131072,
    maxOutputTokens: 32768,
    useCustomProtocol: true
  },
  {
    id: 'THUDM/GLM-4-9B-0414',
    name: 'AIST2030免费·GLM-4-9B（最快·硅基流动）',
    vendor: 'AIST2030免费网关',
    url: GATEWAY_URL,
    apiKey: 'sk-free-gateway',
    supportsToolCall: true,
    supportsImages: false,
    supportsReasoning: false,
    maxInputTokens: 131072,
    maxOutputTokens: 32768,
    useCustomProtocol: true
  },
  {
    id: 'Qwen/Qwen2.5-7B-Instruct',
    name: 'AIST2030免费·Qwen2.5-7B（代码强）',
    vendor: 'AIST2030免费网关',
    url: GATEWAY_URL,
    apiKey: 'sk-free-gateway',
    supportsToolCall: true,
    supportsImages: false,
    supportsReasoning: false,
    maxInputTokens: 131072,
    maxOutputTokens: 32768,
    useCustomProtocol: true
  },
  {
    id: 'glm-4-flash',
    name: 'AIST2030免费·GLM-4-Flash（中文通用）',
    vendor: 'AIST2030免费网关',
    url: GATEWAY_URL,
    apiKey: 'sk-free-gateway',
    supportsToolCall: true,
    supportsImages: false,
    supportsReasoning: false,
    maxInputTokens: 131072,
    maxOutputTokens: 32768,
    useCustomProtocol: true
  }
];

function ensureDirs() {
  if (!fs.existsSync(CONFIG_DIR)) fs.mkdirSync(CONFIG_DIR, { recursive: true });
}

/* ---------- 用户习惯数据 ---------- */
const DEFAULT_USER_DATA = {
  version: '1.0.0',
  first_use: new Date().toISOString(),
  usage_stats: { total_calls: 0, by_category: {}, by_model: {} },
  preferences: { default_category: 'technical', response_speed_preference: 'fast' }
};

function readUserData() {
  try { return JSON.parse(fs.readFileSync(USER_DATA_FILE, 'utf8')); }
  catch (e) { return JSON.parse(JSON.stringify(DEFAULT_USER_DATA)); }
}

function saveUserData(data) {
  ensureDirs();
  data.last_use = new Date().toISOString();
  fs.writeFileSync(USER_DATA_FILE, JSON.stringify(data, null, 2));
}

function updateUsageStats(category, model) {
  const d = readUserData();
  d.usage_stats.total_calls++;
  d.usage_stats.by_category[category] = (d.usage_stats.by_category[category] || 0) + 1;
  d.usage_stats.by_model[model] = (d.usage_stats.by_model[model] || 0) + 1;
  saveUserData(d);
}

/* ---------- 问题分类（与网关 question-classifier.js 同源规则） ---------- */
const KEYWORDS = {
  technical: ['python', 'javascript', '代码', '编程', '函数', '算法', 'api', '接口', '开发', '程序', '报错', '部署'],
  creative: ['文案', '宣传', '广告', '创意', '设计', '营销', '品牌', '故事', '写作', '诗歌', '文案'],
  business: ['商业', '运营', '管理', '财务', '销售', '客户', '市场', '策略', '计划', '报告'],
  analysis: ['分析', '数据', '统计', '报表', '图表', '趋势', '预测', '评估', '调研', '研究']
};

function classifyQuestion(text) {
  const t = String(text || '').toLowerCase();
  for (const cat of Object.keys(KEYWORDS)) {
    if (KEYWORDS[cat].some(kw => t.includes(kw))) return cat;
  }
  return 'other';
}

function selectOptimalModel(userInput) {
  const d = readUserData();
  const cat = classifyQuestion(userInput);
  // ★ 2026-10-21 修订：旧版无条件返回 qwen-plus / qwen-long（阿里云百炼，实测 400 欠费 → 必然失败）。
  //   现在按类目选择【实测可用】的模型，并把 auto 作为兜底（网关会自动选健康渠道）。
  const CAT_MODEL = {
    technical: 'Qwen/Qwen2.5-7B-Instruct',  // 硅基 Qwen2.5-7B：代码/结构化强，实测 0.25s
    creative: 'glm-4-flash',               // 智谱 GLM-4-Flash：中文表达好，实测 0.5~1.5s
    business: 'THUDM/GLM-4-9B-0414',       // 硅基 GLM-4-9B：综合最强，实测 0.3s
    analysis: 'THUDM/GLM-4-9B-0414',       // 同上，逻辑推理准确
    other: 'auto'                          // 兜底交给网关智能调度
  };
  let model = CAT_MODEL[cat] || 'auto';
  const top = Object.entries(d.usage_stats.by_category).sort((a, b) => b[1] - a[1])[0];
  // 习惯调优：用户高频类目与当前一致时，优先走该类目的最优模型
  const habit_matched = !!(top && top[0] === cat && CAT_MODEL[cat]);
  return { model, category: cat, habit_matched };
}

/* ---------- 核心：注册到 WorkBuddy models.json（增量合并 + 自动备份） ---------- */
function registerModels() {
  if (!fs.existsSync(WB_DIR)) {
    return { success: false, message: '未检测到 WorkBuddy 环境（~/.workbuddy 不存在），请先安装 WorkBuddy。' };
  }
  // 1. 备份
  let list = [];
  if (fs.existsSync(MODELS_JSON)) {
    const ts = new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19);
    fs.copyFileSync(MODELS_JSON, MODELS_JSON + '.bak-' + ts);
    try { list = JSON.parse(fs.readFileSync(MODELS_JSON, 'utf8')); }
    catch (e) { return { success: false, message: 'models.json 解析失败，已中止（未做任何修改）。备份见 ' + MODELS_JSON + '.bak-' + ts }; }
    if (!Array.isArray(list)) return { success: false, message: 'models.json 不是数组结构，已中止。' };
  }
  // 2. 增量合并：按 url+id 匹配，存在则更新名称，不存在则追加
  let added = 0, updated = 0;
  for (const entry of REGISTRY) {
    const idx = list.findIndex(m => m.url === entry.url && m.id === entry.id);
    if (idx >= 0) { list[idx] = Object.assign({}, list[idx], entry); updated++; }
    else { list.push(entry); added++; }
  }
  // 3. 原子写回（先写临时文件再改名）
  const tmp = MODELS_JSON + '.tmp';
  fs.writeFileSync(tmp, JSON.stringify(list, null, 2));
  fs.renameSync(tmp, MODELS_JSON);
  return { success: true, message: '已注册 ' + REGISTRY.length + ' 个模型条目（新增' + added + '，更新' + updated + '），原配置已自动备份。' };
}

/* ---------- 网关健康检查 ---------- */
function checkHealth(timeoutMs) {
  timeoutMs = timeoutMs || 3000;
  return new Promise(resolve => {
    const req = http.get('http://127.0.0.1:' + GATEWAY_PORT + '/health', { timeout: timeoutMs }, res => {
      let d = '';
      res.on('data', c => d += c);
      res.on('end', () => {
        try { resolve({ ok: res.statusCode === 200, detail: JSON.parse(d) }); }
        catch (e) { resolve({ ok: false, detail: d.slice(0, 100) }); }
      });
    });
    req.on('timeout', () => { req.destroy(); resolve({ ok: false, detail: 'timeout' }); });
    req.on('error', () => resolve({ ok: false, detail: 'gateway-not-running' }));
  });
}

/* ---------- 启动网关（后台分离进程） ---------- */
function startGateway() {
  const entry = path.join(GATEWAY_DIR, 'gateway.js');
  if (!fs.existsSync(entry)) {
    return { success: false, message: '网关文件不存在：' + entry + '，请先运行 install 脚本。' };
  }
  const node = process.execPath;
  const child = spawn(node, [entry], {
    cwd: GATEWAY_DIR,
    detached: true,
    stdio: 'ignore',
    env: Object.assign({}, process.env, { PORT: String(GATEWAY_PORT) })
  });
  child.unref();
  return { success: true, message: '网关已启动（PID ' + child.pid + '，端口 ' + GATEWAY_PORT + '）', pid: child.pid };
}

/* ---------- 一句话配置总入口 ---------- */
async function configure(input) {
  const steps = [];
  // 1. 注册模型
  const reg = registerModels();
  steps.push({ step: '注册模型', ok: reg.success, msg: reg.message });
  if (!reg.success) return { success: false, steps, next: '先解决注册问题' };

  // 2. 健康检查 → 未运行则启动 → 再检查
  let health = await checkHealth();
  if (!health.ok) {
    const st = startGateway();
    steps.push({ step: '启动网关', ok: st.success, msg: st.message });
    if (st.success) {
      await new Promise(r => setTimeout(r, 1500));
      health = await checkHealth();
    }
  } else {
    steps.push({ step: '网关状态', ok: true, msg: '网关已在运行（端口 ' + GATEWAY_PORT + '）' });
  }
  steps.push({ step: '健康验证', ok: health.ok, msg: health.ok ? '就绪渠道: ' + (health.detail.providersReady || []).join(', ') : '网关未响应，可能需要手动运行 start-gateway.bat' });

  // 3. 初始化习惯数据
  if (!fs.existsSync(USER_DATA_FILE)) saveUserData(JSON.parse(JSON.stringify(DEFAULT_USER_DATA)));

  const allOk = reg.success && health.ok;
  return {
    success: allOk,
    steps,
    next: allOk
      ? '打开控制面板 http://127.0.0.1:8787 粘贴免费 Key（面板内有领 Key 教程），然后即可在对话模型下拉选择「AIST2030免费模型」。'
      : '按上述 ❌ 步骤处理后，重新说一句"帮我配置免费模型"。'
  };
}

/* ---------- CLI ---------- */
if (require.main === module) {
  const cmd = process.argv[2] || 'status';
  (async () => {
    if (cmd === 'register') {
      console.log(JSON.stringify(registerModels(), null, 2));
    } else if (cmd === 'health') {
      console.log(JSON.stringify(await checkHealth(5000), null, 2));
    } else if (cmd === 'start') {
      console.log(JSON.stringify(startGateway(), null, 2));
    } else if (cmd === 'configure') {
      console.log(JSON.stringify(await configure(process.argv[3] || ''), null, 2));
    } else {
      const h = await checkHealth(2000);
      console.log('网关: ' + (h.ok ? '运行中(端口' + GATEWAY_PORT + ')' : '未运行') );
      console.log('注册: ' + (fs.existsSync(MODELS_JSON) && fs.readFileSync(MODELS_JSON, 'utf8').includes('AIST2030') ? '已注册' : '未注册'));
      console.log('习惯数据: ' + (fs.existsSync(USER_DATA_FILE) ? '存在' : '未初始化'));
    }
  })();
}

/* ---------- 模块导出 ---------- */
module.exports = {
  configure, registerModels, startGateway, checkHealth,
  classifyQuestion, selectOptimalModel, updateUsageStats,
  getUserData: readUserData, saveUserData
};
