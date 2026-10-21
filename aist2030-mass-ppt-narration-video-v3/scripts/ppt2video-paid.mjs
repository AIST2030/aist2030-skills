/**
 * PPT 备注转讲解视频 · 付费调用脚本（买家侧）
 * ===============================================
 * 四步链路（本地出片模式）：
 *   probe    → 请求资源接口，未付款时取得 HTTP 402 账单
 *   pay      → 把账单交给支付宝官方 CLI（alipay-bot），用户扫码授权
 *   complete → 用户付款后查询原订单，确认支付成功（服务端仅返回授权凭据）
 *   render   → 在**买家本机**运行 scripts/pipeline.py，用本地 PPTX 出片
 *
 * 设计红线（官方规范）：
 *   · 本脚本只做编排，不接触支付密钥，也不自行实现付款或签名
 *   · 支付与回执一律交给官方 CLI（alipay-bot），成功路径不追加独立回执
 *   · 支付后复用**同一订单**，不重新下单、不重复付款
 *   · 状态不明时先查单，不重新付款
 *   · 服务端只收款、不收 PPT、不在云端渲染；成片在买家本机生成
 *
 * 支付宝 402（AI 按量付费）协议对齐点：
 *   ① 402 账单：probe 请求资源接口，未付款时服务端返回 402 + Payment-Needed 账单；
 *      服务端在**返回账单之前**已把订单持久化落库（先有单、后有账）。
 *   ② 凭证重试：支付完成后 complete 携带 Payment-Proof 重新请求**同一 URL、
 *      同一请求方法、同一参数**，复用同一订单，不重新下单。
 *   ③ 服务端验付：服务端调用 alipay.aipay.agent.payment.verify，并交叉核对
 *      active / trade_no / out_trade_no / resource_id / amount 五项，任一不符即不交付。
 *   ④ 履约确认：资源就绪后由服务端调用 alipay.aipay.agent.fulfillment.confirm
 *      上报回执，回执成功才把订单推进为 FULFILLED；回执失败可用同一 Payment-Proof
 *      重试，重试命中同一订单，不产生第二次扣费。
 *   ⑤ 订单持久化与幂等：订单以唯一 out_trade_no 落库并可跨重启恢复，写操作经串行锁
 *      原子推进 UNFULFILLED → PENDING_CONFIRM → FULFILLED；命中 FULFILLED 时
 *      直接复用已保存结果返回，同一订单只履约一次。
 *
 * 用法：
 *   node ppt2video-paid.mjs probe    --ppt "F:/x.pptx" --state-dir .state/s1
 *   node ppt2video-paid.mjs pay      --state-dir .state/s1 --session-id s1
 *   node ppt2video-paid.mjs complete --state-dir .state/s1 --out-shake-no <NO>
 *   node ppt2video-paid.mjs render   --state-dir .state/s1 -o 输出.mp4
 */

import { execFile } from 'node:child_process';
import { promisify } from 'node:util';
import { writeFile, mkdir, readFile, stat } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

const execFileAsync = promisify(execFile);

/** 本脚本所在目录（ESM 无 __dirname，须由 import.meta.url 推导） */
const __dirname = path.dirname(fileURLToPath(import.meta.url));

// ==================== 配置 ====================

/** 资源接口：部署在公网 HTTPS；未部署时可用本地地址联调 */
const CONFIG = {
  resourceUrl: process.env.PPT2VIDEO_RESOURCE_URL || 'http://127.0.0.1:3000/api/ppt2video/render',
  method: 'GET',
  timeoutMs: 30_000,
  /** 单次价格（元），与支付宝服务登记价、SkillHub 展示价一致 */
  priceYuan: '0.10',
};

// ==================== 状态 ====================

const statePaths = (stateDir) => ({
  paymentNeeded: path.join(stateDir, 'payment-needed.b64'),
  meta: path.join(stateDir, 'meta.json'),
});

async function saveMeta(stateDir, meta) {
  await mkdir(stateDir, { recursive: true });
  await writeFile(statePaths(stateDir).meta, JSON.stringify(meta, null, 2), { encoding: 'utf8', mode: 0o600 });
}

async function loadMeta(stateDir) {
  return JSON.parse(await readFile(statePaths(stateDir).meta, 'utf8'));
}

async function fileExists(p) {
  try {
    await stat(p);
    return true;
  } catch {
    return false;
  }
}

// ==================== probe：取 402 账单 ====================

export async function probe({ ppt, stateDir }) {
  if (!ppt) throw new Error('缺少 --ppt（本地 PPTX 绝对路径）');
  await mkdir(stateDir, { recursive: true });

  // 资源请求：GET 携带 PPT 路径
  const url = `${CONFIG.resourceUrl}?ppt=${encodeURIComponent(ppt)}`;
  const { stdout } = await execFileAsync(
    'curl',
    ['-s', '-D', path.join(stateDir, 'headers.txt'),
     '--connect-timeout', '10', '-o', path.join(stateDir, 'body.txt'),
     '-w', 'HTTP_STATUS:%{http_code}', url],
    { timeout: CONFIG.timeoutMs }
  );

  const status = Number(stdout.match(/HTTP_STATUS:(\d+)/)?.[1] ?? 0);
  if (status === 200) {
    // 已付费过或资源可直接访问
    return { kind: 'resource', status, stateDir };
  }
  if (status !== 402) throw new Error(`资源请求返回 HTTP ${status}（预期 402 或 200）`);

  // 提取账单
  const headers = await readFile(path.join(stateDir, 'headers.txt'), 'utf8');
  const paymentNeeded = headers.match(/payment-needed:\s*([^\r\n]+)/i)?.[1]?.trim();
  if (!paymentNeeded) throw new Error('HTTP 402 缺少 Payment-Needed 响应头');

  await writeFile(statePaths(stateDir).paymentNeeded, paymentNeeded, { encoding: 'utf8', mode: 0o600 });
  await saveMeta(stateDir, { resourceUrl: url, ppt, priceYuan: CONFIG.priceYuan, createdAt: new Date().toISOString() });

  return { kind: 'payment-needed', status: 402, stateDir, paymentNeededFile: statePaths(stateDir).paymentNeeded };
}

// ==================== pay：交官方 CLI 收款 ====================

export function buildBuyerPayArgs(state, sessionId) {
  return [
    '402-buyer-pay',
    '--session-id', sessionId,
    '--file', state.paymentNeededFile,
    '--resource-url', state.resourceUrl,
    '--method', state.method || 'GET',
    '--intent-summary', `原始请求：PPT 备注转讲解视频（${state.ppt || ''}）`,
  ];
}

export async function pay({ stateDir, sessionId }) {
  const meta = await loadMeta(stateDir);
  const state = {
    ...meta,
    method: CONFIG.method,
    paymentNeededFile: statePaths(stateDir).paymentNeeded,
  };
  // 官方 CLI 负责支付与回执，本脚本原样转发其输出
  const { stdout, stderr } = await execFileAsync('alipay-bot', buildBuyerPayArgs(state, sessionId), {
    timeout: 10 * 60_000,
  });
  return { stdout, stderr };
}

// ==================== complete：查单取资源 ====================

export async function complete({ stateDir, outShakeNo }) {
  const meta = await loadMeta(stateDir);
  // 官方 CLI 取得非空资源后会按当前流程发送买家回执，成功路径不再调独立回执
  const { stdout, stderr } = await execFileAsync('alipay-bot', [
    '402-query-payment-status',
    '--out-shake-no', outShakeNo,
    '--resource-url', meta.resourceUrl,
    '--method', CONFIG.method,
  ], { timeout: CONFIG.timeoutMs });
  return { stdout, stderr };
}

// ==================== render：本机出片 ====================

/**
 * 第四步：支付确认后，在**买家本机**运行 scripts/pipeline.py 出片。
 * PPTX 在买家电脑上，服务端只收款、不收文件、不在云端渲染。
 */
export async function render({ stateDir, out, o }) {
  const meta = await loadMeta(stateDir);
  if (!meta.ppt) throw new Error('状态文件缺少 ppt 路径；请先用 probe 传入 --ppt <本地.pptx>');

  const ppt = meta.ppt;
  // -o 与 --out 都支持（parseArgs 会把 --out 转 out、-o 转 o）
  const output = out || o || path.join(stateDir, 'output.mp4');
  const scriptDir = __dirname;
  const pipeline = path.join(scriptDir, 'pipeline.py');

  if (!(await fileExists(pipeline))) {
    throw new Error(`未找到出片脚本：${pipeline}（本 Skill 应随附 scripts/pipeline.py）`);
  }

  console.error(`[render] 本机出片：${ppt} -> ${output}`);
  const { stdout, stderr } = await execFileAsync(
    process.env.PYTHON_BIN || 'python',
    [pipeline, ppt, '-o', output],
    { timeout: 30 * 60_000, cwd: scriptDir }
  );
  return { stdout, stderr, output };
}

// ==================== CLI ====================

function parseArgs(argv) {
  const out = {};
  for (let i = 0; i < argv.length; i += 2) {
    const k = argv[i];
    if (!k || !k.startsWith('-')) continue;
    // 同时支持 `--state-dir` 与 `-o`；并把 kebab-case 统一转为 camelCase，
    // 与各子命令的入参名（stateDir / outShakeNo ...）保持一致。
    const name = k.replace(/^--?/, '').replace(/-([a-z])/g, (_, c) => c.toUpperCase());
    out[name] = argv[i + 1];
  }
  return out;
}

const [, , cmd, ...rest] = process.argv;
const args = parseArgs(rest);

const CMDS = { probe, pay, complete, render };

if (!cmd || !CMDS[cmd]) {
  console.error(`用法:
  node ppt2video-paid.mjs probe    --ppt "<绝对路径.pptx>" --state-dir <目录>
  node ppt2video-paid.mjs pay      --state-dir <目录> --session-id <会话ID>
  node ppt2video-paid.mjs complete --state-dir <目录> --out-shake-no <订单号>
  node ppt2video-paid.mjs render   --state-dir <目录> [-o <输出.mp4>]`);
  process.exit(1);
}

CMDS[cmd](args)
  .then((r) => {
    if (r.stdout) process.stdout.write(r.stdout);
    if (r.kind) console.error(JSON.stringify({ kind: r.kind, status: r.status, stateDir: r.stateDir }));
    if (r.output) console.error(`[render] 成片已生成：${r.output}`);
  })
  .catch((e) => {
    console.error(`[ppt2video-paid] ${e.message}`);
    process.exit(1);
  });
