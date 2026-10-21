#!/usr/bin/env python3
"""
免费模型网关 · 全渠道体检脚本
用法：python health_check.py
输出：每个渠道的可用状态 + 原因（余额不足/欠费/限流/模型下线/正常）
同时把"死渠道"打印成一行汇总，便于一眼看出还能用哪几家。
"""
import json, os, sys, urllib.request, urllib.error
import concurrent.futures as cf

DIR = os.path.dirname(os.path.abspath(__file__))
ENV = {}
for line in open(os.path.join(DIR, '.env'), encoding='utf-8'):
    line = line.strip()
    if not line or line.startswith('#') or '=' not in line:
        continue
    k, v = line.split('=', 1)
    ENV[k.strip()] = v.strip().strip('"').strip("'")

CFG = json.load(open(os.path.join(DIR, 'models.json'), encoding='utf-8'))
PROVS = CFG.get('providers', CFG if isinstance(CFG, list) else [])

def probe(p):
    key = ENV.get(p.get('apiKeyEnv', ''), '')
    if not key:
        return p['id'], 'NOKEY', '未配置 Key', p.get('priority', 99)
    # ★ 必须带上渠道的 extraBody（如 LongCat 的 thinking:disabled），
    #   否则思考型模型会把 max_tokens 全花在 reasoning 上 → 正文为空 → 误判为不可用。
    #   同时 max_tokens 给足（不要用 20 这种极小值）。
    body = {'model': p.get('defaultModel') or (p.get('models') or [''])[0],
            'messages': [{'role': 'user', 'content': 'hi'}], 'max_tokens': 256}
    body.update(p.get('extraBody') or {})
    req = urllib.request.Request(
        p['baseUrl'].rstrip('/') + '/chat/completions',
        data=json.dumps(body).encode('utf-8'),
        headers={'Content-Type': 'application/json', 'Authorization': 'Bearer ' + key})
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            d = json.loads(r.read().decode('utf-8', 'replace'))
            ch = d.get('choices') or []
            c = ch[0].get('message', {}).get('content') if ch else None
            if c:
                return p['id'], 'OK', '', p.get('priority', 99)
            return p['id'], 'EMPTY', '200 但正文为空', p.get('priority', 99)
    except urllib.error.HTTPError as e:
        txt = e.read().decode('utf-8', 'replace')
        reason = ''
        for pat, why in [('free-models-per-day', '每日额度用尽(次日08:00恢复)'), ('Insufficient Balance', '余额不足(需充值)'),
                         ('没有可用套餐', '未订购套餐'), ('Arrearage', '欠费'), ('overdue', '欠费'),
                         ('good standing', '账号状态异常/欠费'), ('NotFound', '模型名无效'),
                         ('Model disabled', '模型已下线'), ('Rate limit', '限流')]:
            if pat.lower() in txt.lower():
                reason = why
                break
        return p['id'], 'HTTP%d' % e.code, reason or txt[:70], p.get('priority', 99)
    except Exception as e:
        return p['id'], 'ERR', str(e)[:60], p.get('priority', 99)

def main():
    targets = [p for p in PROVS if p.get('enabled') is not False and p.get('apiKeyEnv')]
    print('正在体检 %d 个已启用渠道...\n' % len(targets))
    res = []
    with cf.ThreadPoolExecutor(8) as ex:
        for r in ex.map(probe, targets):
            res.append(r)
    res.sort(key=lambda x: x[3])
    ok = []
    print('%-18s %-10s %-34s %s' % ('渠道', '优先级', '状态', '说明'))
    print('-' * 84)
    for pid, st, why, prio in res:
        mark = 'OK  ' if st == 'OK' else 'FAIL'
        print('%-18s %-10s %-34s %s' % (pid, prio, st, why))
        if st == 'OK':
            ok.append(pid)
    print('-' * 84)
    print('\n✅ 真正可用 (%d 家): %s' % (len(ok), ', '.join(ok) or '无'))
    dead = [r[0] for r in res if r[1] != 'OK']
    if dead:
        print('❌ 不可用 (%d 家): %s' % (len(dead), ', '.join(dead)))
    return 0 if ok else 1

if __name__ == '__main__':
    sys.exit(main())
