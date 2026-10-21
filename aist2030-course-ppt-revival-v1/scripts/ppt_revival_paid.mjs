/**
 * 老旧课程 PPT 复活 · 付费调用脚本（买家侧）
 * ===============================================
 * 三步链路：
 *   probe    → 请求资源接口，未付款时取得 HTTP 402 账单
 *   pay      → 把账单交给支付宝官方 CLI（alipay-bot），用户扫码授权
 *   complete → 用户付款后查询原订单，取得「已授权」凭据
 *
 * 授权通过后，后续 analyze / apply / export_notes 三个 Python 脚本在**买家本机**运行，
 * 服务端不接收 PPT、不处理课件。
 *
 * 设计红线（官方规范）：
 *   · 本脚本只做编排，不接触支付密钥，也不自行实现付款或签名
 *   · 支付与回执一律交给官方 CLI（alipay-bot），成功路径不追加独立回执
 *   · 支付后复用**同一订单**，不重新下单、不重复付款
 *   · 状态不明时先查单，不重新付款
 *
 * 支付宝 402（AI 按量付费）协议对齐点：
 *   ① 402 账单：未付款时服务端返回 402 + Payment-Needed；服务端在返回账单之前已把订单持久化落库。
 *   ② 凭证重试：支付完成后携带 Payment-Proof 重新请求同一 URL、同一方法、同一参数。
 *   ③ 服务端验付：服务端调用 alipay.aipay.agent.payment.verify，交叉核对
 *      active / trade_no / out_trade_no / resource_id / amount 五项。
 *   ④ 履约确认：就绪后由服务端调用 alipay.aipay.agent.fulfillment.confirm，
 *      成功才推进 FULFILLED；失败可用同一 Payment-Proof 重试，不重复扣费。
 *   ⑤ 订单持久化与幂等：唯一 out_trade_no 落库，串行锁原子推进状态机，
 *      命中 FULFILLED 直接复用已存结果。
 *
 * 用法：
 *   node ppt_revival_paid.mjs probe    --ppt "F:/老课件.pptx" --state-dir .state/s1
 *   node ppt_revival_paid.mjs pay      --state-dir .state/s1 --session-id s1
 *   node ppt_revival_paid.mjs complete --state-dir .state/s1 --out-shake-no <NO>
 */

import { execFile } from 'node:child_process';
import { promisify } from 'node:util';
import { writeFile, mkdir, readFile } from 'node:fs/promises';
import path from 'node:path';

const execFileAsync = promisify(execFile);

// ==================== 配置 ====================

const CONFIG = {
  resourceUrl: process.env.PPT_REVIVAL_RESOURCE_URL
    || 'http://127.0.0.1:3000/api/ppt-revival/process',
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

// ==================== probe：取 402 账单 ====================

export async function probe({ ppt, stateDir }) {
  if (!ppt) throw new Error('缺少 --ppt（本地 PPTX 绝对路径）');
  if (!stateDir) throw new Error('缺少 --state-dir');
  await mkdir(stateDir, { recursive: true });

  const url = `${CONFIG.resourceUrl}?ppt=${encodeURIComponent(ppt)}`;
  const { stdout } = await execFileAsync(
    'curl',
    ['-s', '-D', path.join(stateDir, 'headers.txt'),
     '--connect-timeout', '10', '-o', path.join(stateDir, 'body.txt'),
     '-w', 'HTTP_STATUS:%{http_code}', url],
    { timeout: CONFIG.timeoutMs }
  );

  const status = Number(stdout.match(/HTTP_STATUS:(\d+)/)?.[1] ?? 0);
  if (status === 200) return { kind: 'resource', status, stateDir };
  if (status !== 402) throw new Error(`资源请求返回 HTTP ${status}（预期 402 或 200）`);

  const headers = await readFile(path.join(stateDir, 'headers.txt'), 'utf8');
  const paymentNeeded = headers.match(/payment-needed:\s*([^\r\n]+)/i)?.[1]?.trim();
  if (!paymentNeeded) throw new Error('HTTP 402 缺少 Payment-Needed 响应头');

  await writeFile(statePaths(stateDir).paymentNeeded, paymentNeeded, { encoding: 'utf8', mode: 0o600 });
  await saveMeta(stateDir, { resourceUrl: url, ppt, priceYuan: CONFIG.priceYuan, createdAt: new Date().toISOString() });

  return { kind: 'payment-needed', status: 402, stateDir, paymentNeededFile: statePaths(stateDir).paymentNeeded };
}

// ==================== pay：交官方 CLI 收款 ====================

export async function pay({ stateDir, sessionId }) {
  const meta = await loadMeta(stateDir);
  const args = [
    '402-buyer-pay',
    '--session-id', sessionId,
    '--file', statePaths(stateDir).paymentNeeded,
    '--resource-url', meta.resourceUrl,
    '--method', CONFIG.method,
    '--intent-summary', `原始请求：老旧课程 PPT 复活（${meta.ppt || ''}）`,
  ];
  const { stdout, stderr } = await execFileAsync('alipay-bot', args, { timeout: 10 * 60_000 });
  return { stdout, stderr };
}

// ==================== complete：查单取凭据 ====================

export async function complete({ stateDir, outShakeNo }) {
  const meta = await loadMeta(stateDir);
  const { stdout, stderr } = await execFileAsync('alipay-bot', [
    '402-query-payment-status',
    '--out-shake-no', outShakeNo,
    '--resource-url', meta.resourceUrl,
    '--method', CONFIG.method,
  ], { timeout: CONFIG.timeoutMs });
  return { stdout, stderr };
}

// ==================== CLI ====================

function parseArgs(argv) {
  const out = {};
  for (let i = 0; i < argv.length; i += 2) {
    const k = argv[i];
    if (!k || !k.startsWith('-')) continue;
    // 支持 `--state-dir` / `-o`，并把 kebab-case 统一转为 camelCase 以匹配入参名
    const name = k.replace(/^--?/, '').replace(/-([a-z])/g, (_, c) => c.toUpperCase());
    out[name] = argv[i + 1];
  }
  return out;
}

const [, , cmd, ...rest] = process.argv;
const args = parseArgs(rest);

const CMDS = { probe, pay, complete };

if (!cmd || !CMDS[cmd]) {
  console.error(`用法:
  node ppt_revival_paid.mjs probe    --ppt "<绝对路径.pptx>" --state-dir <目录>
  node ppt_revival_paid.mjs pay      --state-dir <目录> --session-id <会话ID>
  node ppt_revival_paid.mjs complete --state-dir <目录> --out-shake-no <订单号>`);
  process.exit(1);
}

CMDS[cmd](args)
  .then((r) => {
    if (r.stdout) process.stdout.write(r.stdout);
    if (r.kind) console.error(JSON.stringify({ kind: r.kind, status: r.status, stateDir: r.stateDir }));
  })
  .catch((e) => {
    console.error(`[ppt-revival-paid] ${e.message}`);
    process.exit(1);
  });
