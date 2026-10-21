# -*- coding: utf-8 -*-
"""
从 Skill 台账 CSV 生成两份页面：
  1) 台账看板.html  —— 内部全量看板（含 异常/不上架/已下线）
  2) 技能展示页.html —— 对外合规版（过滤已下线、去内部字段、去价格/付费措辞）
用法：python build_ledger_dashboard.py <台账.csv> [--outdir <dir>]
CSV 列：id,展示名,模块,版本,来源,发布状态,优化状态,维护方,上架日期,备注
"""
import csv, io, os, sys, html, datetime, argparse

COLUMNS = ["id", "展示名", "模块", "版本", "来源", "发布状态", "优化状态", "维护方", "上架日期", "备注"]

def read_ledger(path):
    rows = []
    with io.open(path, encoding="utf-8-sig", newline="") as f:
        r = csv.DictReader(f)
        for row in r:
            row = {k.strip(): (v or "").strip() for k, v in row.items()}
            if not row.get("id") and not row.get("展示名"):
                continue
            rows.append(row)
    return rows

def esc(s):
    return html.escape(str(s), quote=True)

def stat_cards(rows, pub=False):
    if pub:
        pool = [d for d in rows if d["发布状态"] != "已下线"]
        cards = [
            {"n": len(pool), "l": "技能总数", "ic": "📦"},
            {"n": sum(1 for d in pool if d["发布状态"] == "已上架"), "l": "✅ 已发布", "ic": "🚀"},
            {"n": sum(1 for d in pool if d["来源"] in ("乐享", "自建")), "l": "💬 自主运营", "ic": "🛡"},
        ]
    else:
        cards = [
            {"n": len(rows), "l": "技能总数", "ic": "📦"},
            {"n": sum(1 for d in rows if d["发布状态"] == "已上架"), "l": "✅ 已上架", "ic": "🚀"},
            {"n": sum(1 for d in rows if d["发布状态"] == "待发布"), "l": "⏳ 待发布", "ic": "⏳"},
            {"n": sum(1 for d in rows if d["发布状态"] == "异常"), "l": "⚠️ 异常", "ic": "🛠"},
            {"n": sum(1 for d in rows if d["发布状态"] == "不上架"), "l": "🚫 不上架", "ic": "🔒"},
            {"n": sum(1 for d in rows if d["发布状态"] == "已下线"), "l": "🗑 已下线", "ic": "🗑"},
        ]
    return cards

STATUS_CLASS = {"已上架": "b-ok", "待发布": "b-wait", "异常": "b-err", "不上架": "b-no", "已下线": "b-off"}
STATUS_ICON = {"已上架": "✅", "待发布": "⏳", "异常": "⚠️", "不上架": "🚫", "已下线": "🗑"}

def render_table(rows, pub=False):
    out = []
    for i, d in enumerate(rows, 1):
        if pub and d["发布状态"] == "已下线":
            continue
        cls = ' class="row-warn"' if d["发布状态"] == "异常" else ""
        out.append(
            "<tr" + cls + "><td>" + str(i) + "</td><td><span class='id'>" + esc(d.get("id", "")) + "</span></td><td>"
            + esc(d.get("展示名", "")) + "</td><td>" + esc(d.get("模块", "")) + "</td><td>"
            + esc(d.get("版本", "")) + "</td><td>" + esc(d.get("来源", "")) + "</td><td><span class='badge "
            + STATUS_CLASS.get(d["发布状态"], "b-no") + "'>" + STATUS_ICON.get(d["发布状态"], "")
            + " " + esc(d["发布状态"]) + "</span></td></tr>"
        )
    return "\n".join(out)

def render_dist(rows, pub=False):
    pool = rows if not pub else [d for d in rows if d["发布状态"] != "已下线"]
    counts = {}
    for d in pool:
        counts[d.get("模块", "未分类")] = counts.get(d.get("模块", "未分类"), 0) + 1
    if not counts:
        return "<div class='empty'>暂无数据</div>"
    mx = max(counts.values())
    out = []
    for m, v in sorted(counts.items(), key=lambda x: -x[1]):
        out.append("<div class='bar-row'><div class='name'>" + esc(m) + "</div><div class='bar-track'>"
                   + "<div class='bar-fill' style='width:" + str(int(v / mx * 100)) + "%'></div></div>"
                   + "<div class='val'>" + str(v) + "</div></div>")
    return "\n".join(out)

CSS = """<style>
:root{--bg:#0f1115;--card:#171a21;--text:#e8eaf0;--muted:#9aa3b2;--brand1:#6d28d9;--brand2:#2563eb;--brand3:#0891b2;--green:#22c55e;--amber:#f59e0b;--red:#ef4444;--gray:#64748b;--line:#262b36}
[data-theme=light]{--bg:#f6f7fb;--card:#fff;--text:#1a1d24;--muted:#5b6472;--line:#e6e9f0}
*{box-sizing:border-box}
body{margin:0;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif;background:var(--bg);color:var(--text);transition:background .3s,color .3s}
.hero{background:linear-gradient(135deg,var(--brand1),var(--brand2) 55%,var(--brand3));color:#fff;padding:34px 18px 28px;position:relative;overflow:hidden}
.hero-inner{max-width:1280px;margin:0 auto;padding:0 18px;box-sizing:border-box}
.hero h1{margin:0;font-size:26px;letter-spacing:.5px}
.hero .sub{margin-top:8px;opacity:.9;font-size:14px}
.hero .meta{margin-top:14px;font-size:12px;opacity:.8}
.wrap{max-width:1280px;margin:0 auto;padding:22px 18px 60px}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:14px;margin-top:-42px;position:relative;z-index:2}
.card{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:16px;box-shadow:0 6px 20px rgba(0,0,0,.12)}
.card .ic{font-size:22px}.card .num{font-size:28px;font-weight:700;margin-top:4px}.card .lbl{color:var(--muted);font-size:13px;margin-top:2px}
.toolbar{display:flex;flex-wrap:wrap;gap:10px;align-items:center;margin:22px 0 10px}
.pill{cursor:pointer;padding:6px 12px;border-radius:999px;border:1px solid var(--line);background:var(--card);color:var(--text);font-size:13px}
.pill.active{background:var(--brand1);color:#fff;border-color:transparent}
select,input[type=search]{padding:6px 10px;border-radius:8px;border:1px solid var(--line);background:var(--card);color:var(--text)}
.spacer{flex:1}
.theme-btn{cursor:pointer;padding:6px 12px;border-radius:8px;border:1px solid var(--line);background:var(--card);color:var(--text)}
.count-line{color:var(--muted);font-size:13px;margin:6px 0 12px}
.tablewrap{overflow-x:auto;border:1px solid var(--line);border-radius:12px;background:var(--card)}
table{width:100%;border-collapse:collapse;font-size:14px}
th,td{padding:10px 12px;text-align:left;border-bottom:1px solid var(--line);white-space:nowrap}
th{color:var(--muted);font-weight:600;font-size:12px;text-transform:uppercase;letter-spacing:.4px}
.id{font-family:monospace;color:var(--muted);font-size:12px}
.row-warn{background:rgba(239,68,68,.08)}
.badge{padding:2px 8px;border-radius:999px;font-size:12px}
.b-ok{background:rgba(34,197,94,.15);color:var(--green)}.b-wait{background:rgba(245,158,11,.15);color:var(--amber)}
.b-err{background:rgba(239,68,68,.15);color:var(--red)}.b-no{background:rgba(100,116,139,.15);color:var(--gray)}
.b-off{background:rgba(100,116,139,.1);color:var(--gray)}
.empty{padding:30px;text-align:center;color:var(--muted)}
.dist{margin-top:22px}.dist h3{font-size:15px;margin:0 0 10px}
.bar-row{display:flex;align-items:center;gap:10px;margin:6px 0}
.bar-row .name{width:120px;font-size:13px}.bar-track{flex:1;height:10px;background:var(--line);border-radius:6px;overflow:hidden}
.bar-fill{height:100%;background:linear-gradient(90deg,var(--brand2),var(--brand1))}
.bar-row .val{width:30px;text-align:right;font-size:13px;color:var(--muted)}
footer{margin-top:40px;color:var(--muted);font-size:13px;line-height:1.7}
</style>"""

def page(rows, pub, title, brand, footer_note):
    # 对外版：彻底剔除「已下线」条目，连内嵌 DATA 也不携带，避免 JS 重渲染时漏网
    data_rows = rows if not pub else [d for d in rows if d["发布状态"] != "已下线"]
    cards = stat_cards(rows, pub)
    cards_html = "".join(
        "<div class='card'><div class='ic'>" + c["ic"] + "</div><div class='num'>" + str(c["n"])
        + "</div><div class='lbl'>" + c["l"] + "</div></div>" for c in cards
    )
    table = render_table(data_rows, pub)
    dist = render_dist(rows, pub)
    extra_pills = "" if pub else "<span class='pill' data-f='不上架'>🚫 不上架</span><span class='pill' data-f='已下线'>🗑 已下线</span>"
    today = datetime.date.today().isoformat()
    data_json = esc(repr(data_rows))
    cards_json = esc(repr(cards))
    filter_expr = "true" if not pub else "d['发布状态']!=='已下线'"
    pub_filter_js = "d['发布状态']!=='已下线'" if pub else "true"

    head = ("<!DOCTYPE html>\n<html lang='zh-CN' data-theme='dark'>\n<head><meta charset='utf-8'>"
            "<meta name='viewport' content='width=device-width,initial-scale=1'>\n<title>" + esc(title)
            + "</title>" + CSS + "</head>\n<body>\n")
    hero = ("<div class='hero'><div class='hero-inner'>\n  <h1>" + esc(title) + "</h1>\n"
            + "  <div class='sub'>单一事实源：本页由 Skill 台账 CSV 派生，与台账保持一致。</div>\n"
            + "  <div class='meta'>维护方：" + esc(brand) + " ｜ 生成时间：" + today + "</div>\n"
            + "</div></div>\n")
    toolbar = ("<div class='wrap'>\n  <div class='cards'>" + cards_html + "</div>\n  <div class='toolbar'>\n"
               + "    <span class='pill active' data-f='all'>全部</span>\n"
               + "    <span class='pill' data-f='已上架'>✅ 已发布</span>\n"
               + "    <span class='pill' data-f='待发布'>⏳ 待发布</span>\n"
               + "    <span class='pill' data-f='异常'>⚠️ 异常</span>\n"
               + "    <span class='pill' data-f='不上架'>🚫 不上架</span>\n" + extra_pills
               + "    <input type='search' id='search' placeholder='搜索展示名 / id …'>\n"
               + "    <div class='spacer'></div>\n    <button class='theme-btn' id='themeBtn'>☀️ 浅色</button>\n  </div>\n")
    count_line = "  <div class='count-line' id='countLine'></div>\n"
    table_html = ("  <div class='tablewrap'><table>\n    <thead><tr><th>#</th><th>id</th><th>展示名</th><th>模块</th>"
                  "<th>版本</th><th>来源</th><th>发布状态</th></tr></thead>\n    <tbody id='tbody'>" + table
                  + "</tbody>\n  </table></div>\n")
    dist_html = "  <div class='dist'><h3>📊 按模块分布</h3><div id='distBars'>" + dist + "</div></div>\n"
    footer = ("  <footer>\n    <div>" + esc(brand) + " · " + esc(title) + "</div>\n"
              + "    <div style='margin-top:6px'>" + footer_note + "</div>\n  </footer>\n</div>\n")
    script = ("<script>\nconst DATA=" + data_json + ";\nconst NS={};\nconst STATUS_CLASS={"
              + "'已上架':'b-ok','待发布':'b-wait','异常':'b-err','不上架':'b-no','已下线':'b-off'};\n"
              + "const STATUS_ICON={'已上架':'✅','待发布':'⏳','异常':'⚠️','不上架':'🚫','已下线':'🗑'};\n"
              + "let curStatus='all',curKey='';\n"
              + "function rows(){return DATA.filter(d=>{if(curStatus!=='all'&&d.发布状态!==curStatus)return false;"
              + "if(curKey){const k=curKey.toLowerCase();if(!(d.展示名.toLowerCase().includes(k)||d.id.toLowerCase().includes(k)))return false;}return true;});}\n"
              + "function renderCards(){const c=" + cards_json + ";const box=document.querySelector('.cards');if(box)box.innerHTML=c.map(x=>`<div class='card'><div class='ic'>${x.ic}</div><div class='num'>${x.n}</div><div class='lbl'>${x.l}</div></div>`).join('');}\n"
              + "function renderTable(){const t=document.getElementById('tbody');const list=rows();"
              + "if(!list.length){t.innerHTML=\"<tr><td colspan='7' class='empty'>没有匹配的技能</td></tr>\";}"
              + "else{t.innerHTML=list.map((d,i)=>{const cls=d.发布状态==='异常'?' class=\\'row-warn\\'':'';return `<tr${cls}><td>${i+1}</td><td><span class=\\'id\\'>${d.id}</span></td><td>${d.展示名}</td><td>${d.模块}</td><td>${d.版本}</td><td>${d.来源}</td><td><span class='badge ${STATUS_CLASS[d.发布状态]||\\'b-no\\'}'>${STATUS_ICON[d.发布状态]||''} ${d.发布状态}</span></td></tr>`;}).join('');}"
              + "document.getElementById('countLine').textContent=`当前显示 ${list.length} / ${DATA.length} 项`;}\n"
              + "function renderDist(){const pool=DATA.filter(d=>" + filter_expr + ");const counts={};pool.forEach(d=>counts[d.模块]=(counts[d.模块]||0)+1);const mx=Math.max(...Object.values(counts),1);const box=document.getElementById('distBars');if(!box)return;box.innerHTML=Object.entries(counts).sort((a,b)=>b[1]-a[1]).map(([m,v])=>`<div class='bar-row'><div class='name'>${m}</div><div class='bar-track'><div class='bar-fill' style='width:${v/mx*100}%'></div></div><div class='val'>${v}</div></div>`).join('');}\n"
              + "document.querySelectorAll('.pill').forEach(p=>p.addEventListener('click',e=>{if(!e.target.classList.contains('pill'))return;document.querySelectorAll('.pill').forEach(x=>x.classList.remove('active'));e.target.classList.add('active');curStatus=e.target.dataset.f;renderTable();}));\n"
              + "document.getElementById('search').addEventListener('input',e=>{curKey=e.target.value.trim();renderTable();});\n"
              + "document.getElementById('themeBtn').addEventListener('click',()=>{const d=document.documentElement.getAttribute('data-theme')==='dark';document.documentElement.setAttribute('data-theme',d?'light':'dark');document.getElementById('themeBtn').textContent=d?'🌙 深色':'☀️ 浅色';});\n"
              + "renderCards();renderTable();renderDist();\n</script>\n</body></html>")
    return head + hero + toolbar + count_line + table_html + dist_html + footer + script

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("csv")
    ap.add_argument("--outdir", default=".")
    a = ap.parse_args()
    rows = read_ledger(a.csv)
    os.makedirs(a.outdir, exist_ok=True)
    with io.open(os.path.join(a.outdir, "台账看板.html"), "w", encoding="utf-8") as f:
        f.write(page(rows, False, "AIST2030 Skill 台账看板",
                    "AIST2030（贵州省团之家智付科技有限公司）",
                    "本看板由 Skill 台账 CSV 派生，含全部状态（含异常/不上架/已下线），仅供内部盘点。"))
    with io.open(os.path.join(a.outdir, "技能展示页.html"), "w", encoding="utf-8") as f:
        f.write(page(rows, True, "AIST2030 Skill 技能展示",
                    "AIST2030（贵州省团之家智付科技有限公司）",
                    "本页展示的技能均发布于 SkillHub 技能社区，能力与条款以各技能页面说明为准。"))
    print("读取 %d 条，生成：台账看板.html + 技能展示页.html（已落盘到 %s）" % (len(rows), a.outdir))

if __name__ == "__main__":
    main()
