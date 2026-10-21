"""本地 mock 草稿箱：开发期冒烟用，绝不连接真实 mp.toutiao.com。

行为：
- GET / 或 /profile_v4/manage/draft 返回含 35 篇草稿的「草稿箱」页面，每篇带「立即发布」按钮。
- POST /publish?id=XXX 标记发布；前 MOCK_FAIL_FIRST 次（读环境变量）返回 500 以测重试/暂停。
- 前端点击后展示 toast（成功/失败），成功则该行置灰为「已发布」。
发布者脚本通过「本地 state.published」去重，mock 仅用于验证 选区/点击/确认/重试 逻辑。
"""
import json
import os
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse, parse_qs

DRAFTS = [{"id": f"D{i:03d}", "title": f"草稿文章 {i:02d}"} for i in range(1, 36)]
_FAIL = [0]  # 失败计数（全局）

PAGE = """<!doctype html><html><head><meta charset="utf-8"><title>草稿箱(Mock)</title>
<style>
.draft-item{{border:1px solid #ccc;padding:8px;margin:4px}}
.published{{opacity:.4}}
.toast{{position:fixed;top:10px;right:10px;padding:8px;color:#fff}}
.toast-success{{background:green}} .toast-error{{background:red}}
</style></head>
<body><h2>草稿箱（Mock，共 {n} 篇）</h2><div id="list">
{rows}
</div><div id="toast"></div>
<script>
document.querySelectorAll('.publish-btn').forEach(function(b){{
  b.onclick = async function(){{
    var item = b.closest('.draft-item');
    var id = item.getAttribute('data-id');
    b.disabled = true;
    try {{
      var r = await fetch('/publish?id=' + id, {{method:'POST'}});
      var j = await r.json();
      var t = document.getElementById('toast');
      if (j.ok) {{
        item.classList.add('published'); b.textContent = '已发布';
        t.innerHTML = '<div class="toast toast-success">发布成功</div>';
      }} else {{
        b.disabled = false;
        t.innerHTML = '<div class="toast toast-error">发布失败</div>';
      }}
      setTimeout(function(){{ t.innerHTML = ''; }}, 2000);
    }} catch(e) {{
      b.disabled = false;
    }}
  }};
}});
</script></body></html>"""


def _rows():
    out = []
    for d in DRAFTS:
        out.append(
            f'<div class="draft-item" data-id="{d["id"]}">'
            f'<span class="title">{d["title"]}</span>'
            f'<button class="publish-btn">立即发布</button></div>'
        )
    return "\n".join(out)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype="text/html; charset=utf-8"):
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path.startswith("/publish"):
            self._send(405, "Method Not Allowed")
            return
        html = PAGE.format(n=len(DRAFTS), rows=_rows())
        self._send(200, html)

    def do_POST(self):
        if not self.path.startswith("/publish"):
            self._send(404, "Not Found")
            return
        q = parse_qs(urlparse(self.path).query)
        did = q.get("id", [""])[0]
        fail_first = int(os.environ.get("MOCK_FAIL_FIRST", "0"))
        _FAIL[0] += 1
        if _FAIL[0] <= fail_first:
            self._send(500, json.dumps({"ok": False}).encode(), "application/json")
            return
        self._send(200, json.dumps({"ok": True, "id": did}).encode(), "application/json")


def start(port=8765):
    srv = HTTPServer(("127.0.0.1", port), Handler)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    return srv


if __name__ == "__main__":
    s = start(8765)
    print("mock server on http://127.0.0.1:8765")
    try:
        while True:
            import time
            time.sleep(1)
    except KeyboardInterrupt:
        s.shutdown()
