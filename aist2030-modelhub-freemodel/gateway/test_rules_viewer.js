// 控制面板「调用规则」区渲染自检（不依赖浏览器）
// 目的：确保 loadUsageRules() 在真实接口返回下不会抛异常，且能生成非空 HTML。
// 做法：抽出渲染函数，用真实的 /usage-rules 响应喂进去，检查输出里包含关键内容。
const fs = require('fs');
const path = require('path');
const http = require('http');

const PANEL = path.join(__dirname, 'control-panel.html');
const src = fs.readFileSync(PANEL, 'utf8');

// 1) 结构完整性
const mustHave = [
  ['规则挂载点', 'id="rulesBox"'],
  ['加载函数', 'function loadUsageRules'],
  ['触发调用', 'loadUsageRules();'],
  ['请求接口', "BASE + '/usage-rules'"],
  ['复制按钮绑定', 'function bindCopyButtons'],
  ['剪贴板兜底', 'function fallbackCopy'],
  ['转义函数', 'function esc'],
];
let pass = 0, fail = 0;
console.log('=== A. 面板结构 ===');
for (const [name, needle] of mustHave) {
  const ok = src.includes(needle);
  ok ? pass++ : fail++;
  console.log((ok ? '  OK  ' : '  ERR ') + name);
}

// 2) 下拉选项必须是实测可用模型（不能出现臆造名）
const opts = [...src.matchAll(/<option value="([^"]+)">/g)].map((m) => m[1]);
console.log('\n=== B. 下拉选项 ===');
console.log('  ' + opts.join(', '));
const banned = ['qwen-plus', 'qwen-long', 'moma-model', 'longcat-model', 'mimo-model',
  'nim-model', 'anthropic-claude', 'cohere-command', 'perplexity-sonnet',
  'huggingface-llama', 'replicate-llama', 'tencent-hunyuan', 'minimax-abab',
  'gemini-2.5-flash', 'deepseek-chat', 'Qwen/Qwen3-8B', 'openrouter/free'];
const bad = opts.filter((o) => banned.includes(o));
const okB = bad.length === 0;
okB ? pass++ : fail++;
console.log((okB ? '  OK   无臆造/失效模型名' : '  ERR  残留: ' + bad.join(', ')));

// 3) 用真实接口数据跑一遍渲染逻辑
function extractFn(name) {
  const i = src.indexOf('function ' + name);
  if (i < 0) throw new Error('未找到函数 ' + name);
  const start = src.indexOf('{', i);
  let d = 0;
  for (let k = start; k < src.length; k++) {
    if (src[k] === '{') d++;
    else if (src[k] === '}') { d--; if (d === 0) return src.slice(i, k + 1); }
  }
  throw new Error('函数 ' + name + ' 括号不配对');
}

function render(rules) {
  // 模拟浏览器最小环境。注意：getElementById 必须返回【同一个】对象，
  // 否则 setter 写进去的值在 getter 读不到（曾因此误判为渲染失败）。
  const node = { _html: '' };
  Object.defineProperty(node, 'innerHTML', {
    get() { return this._html; },
    set(v) { this._html = v; },
  });
  // 面板里是 innerHTML 字符串，浏览器会自动把 button 变成元素；
  // 这里用正则从 HTML 里抽出「复制」按钮，模拟浏览器解析后的结果。
  node.querySelectorAll = function (sel) {
    if (sel !== '.copyRulesBtn') return [];
    const out = [];
    const re = /class="copyRulesBtn" data-code="([^"]*)"/g;
    let m;
    while ((m = re.exec(this._html)) !== null) {
      const code = m[1].replace(/&quot;/g, '"').replace(/&amp;/g, '&')
        .replace(/&lt;/g, '<').replace(/&gt;/g, '>');
      out.push({
        _h: null,
        get textContent() { return this._h; },
        set textContent(v) { this._h = v; },
        getAttribute: () => code,
        addEventListener: () => {},
      });
    }
    return out;
  };
  const fakeDoc = {
    getElementById(id) { return id === 'rulesBox' ? node : null; },
  };
  const fetchStub = () => Promise.resolve({ json: () => Promise.resolve(rules) });
  // eslint-disable-next-line no-new-func
  const fn = new Function('document', 'fetch', 'BASE', 'navigator', 'setTimeout',
    extractFn('esc') + '\n' + extractFn('loadUsageRules') + '\n' +
    extractFn('bindCopyButtons') + '\n' + extractFn('fallbackCopy') +
    '\nloadUsageRules();');
  fn(fakeDoc, fetchStub, 'http://127.0.0.1:8787', {}, setTimeout);
  return new Promise((resolve) => setTimeout(() => resolve(node.innerHTML), 900));
}

function getRules() {
  return new Promise((resolve, reject) => {
    http.get('http://127.0.0.1:8787/usage-rules', (res) => {
      let b = '';
      res.on('data', (c) => (b += c));
      res.on('end', () => { try { resolve(JSON.parse(b)); } catch (e) { reject(e); } });
    }).on('error', reject);
  });
}

getRules()
  .then(async (rules) => {
    const html = await render(rules);
    console.log('\n=== C. 真实数据渲染 ===');
    console.log('  生成 HTML 长度:', html.length);
    const checks = [
      ['决策树渲染', html.includes('怎么选')],
      ['模型表格', html.includes('THUDM/GLM-4-9B-0414')],
      ['推荐徽章', html.includes('推荐')],
      ['请求规则区', html.includes('请求怎么写')],
      ['代码示例区', html.includes('代码示例')],
      ['复制按钮', html.includes('copyRulesBtn')],
      ['报错对照区', html.includes('报错了怎么办')],
      ['自检命令区', html.includes('自检命令')],
      ['渠道现状区', html.includes('渠道真能用')],
    ];
    for (const [n, ok] of checks) { ok ? pass++ : fail++; console.log((ok ? '  OK  ' : '  ERR ') + n); }

    const okLen = html.length > 2000;
    okLen ? pass++ : fail++;
    console.log((okLen ? '  OK  ' : '  ERR ') + '输出非空（>2000 字符）');

    // 4) 转义正确性：XSS 与引号注入
    console.log('\n=== D. 转义安全 ===');
    const evil = JSON.parse(JSON.stringify(rules));
    evil.modelPicker[0].useWhen = '<img src=x onerror=alert(1)>"引号测试';
    const evilHtml = await render(evil);
    const safe = !evilHtml.includes('<img src=x') && evilHtml.includes('&lt;img');
    safe ? pass++ : fail++;
    console.log((safe ? '  OK  ' : '  ERR ') + '恶意标签被转义（无裸 <img）');

    // 5) 数据为空时不能崩
    console.log('\n=== E. 降级 ===');
    const emptyHtml = await render({});
    const noCrash = typeof emptyHtml === 'string';
    noCrash ? pass++ : fail++;
    console.log((noCrash ? '  OK  ' : '  ERR ') + '空规则不崩（返回字符串）');
    const errHtml = await render({ error: 'usage-rules.json 不存在' });
    const showsErr = errHtml.includes('规则文件未配置');
    showsErr ? pass++ : fail++;
    console.log((showsErr ? '  OK  ' : '  ERR ') + '规则缺失时给出明确提示');

    console.log('\n' + '='.repeat(50));
    console.log(`通过 ${pass} / ${pass + fail}`);
    process.exit(fail ? 1 : 0);
  })
  .catch((e) => {
    console.log('  ERR 无法读取 /usage-rules：', (e && e.message) || String(e));
    console.log(e && e.stack ? e.stack.split('\n').slice(0, 6).join('\n') : '');
    console.log('（网关是否在跑？请确认 http://127.0.0.1:8787/health 返回 ok）');
    process.exit(1);
  });