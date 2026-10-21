#!/usr/bin/env python3.11
"""头条草稿箱批量发布 —— 命令行入口。

用法：
  python3.11 cli.py login              # 首次：有头浏览器扫码/凭证登录，保存 auth.json
  python3.11 cli.py import-cookies cookies.json [--domain .mp.toutiao.com]   # 用 cookie 生成 auth.json
  python3.11 cli.py dry-run [--count 29]        # 只读预览：列出将发布的候选队列（不点发布）
  python3.11 cli.py run-day            # 日常：按 8 时段配额发布（建议 cron 每日 07:55 拉起）
  python3.11 cli.py run-forever        # 常驻：无 cron 时 nohup 后台日循环
  python3.11 cli.py mock-smoke [--fail-first N] [--show]   # 开发期：本地 mock 草稿箱冒烟
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from scheduler import run_day, run_forever
from toutiao_publisher import ToutiaoPublisher, NeedsLogin
import mock_server
from state import load_state, save_state, set_paused

ROOT = os.path.dirname(os.path.abspath(__file__))
DEFAULT_AUTH = os.path.join(ROOT, "auth.json")
DEFAULT_STATE = os.path.join(ROOT, "state.json")
DEFAULT_BASE = "https://mp.toutiao.com"
DEFAULT_DRAFT = "/profile_v4/manage/draft"


# ---------------- cookie 导入 ----------------
def _parse_cookies(raw, default_domain):
    """支持三种输入：JSON 数组 / 含 cookies 键的 dict / document.cookie 或 curl --cookie 文本。"""
    text = raw.strip()
    try:
        obj = json.loads(text)
        if isinstance(obj, list):
            return obj
        if isinstance(obj, dict) and "cookies" in obj:
            return obj["cookies"]
    except Exception:
        pass
    # 纯文本：name=value; name2=value2
    cookies = []
    for part in text.split(";"):
        part = part.strip()
        if not part or "=" not in part:
            continue
        name, _, value = part.partition("=")
        cookies.append({"name": name.strip(), "value": value.strip()})
    return cookies


SAMESITE_MAP = {
    "unspecified": "Lax",
    "no_restriction": "None",
    "": "Lax",
    None: "Lax",
}


def _normalize_cookie(c, default_domain):
    raw = c.get("sameSite", "Lax")
    same_site = SAMESITE_MAP.get(raw, raw if raw in ("Strict", "Lax", "None") else "Lax")
    out = {
        "name": c.get("name", ""),
        "value": c.get("value", ""),
        "domain": c.get("domain") or default_domain,
        "path": c.get("path") or "/",
        "expires": c.get("expires", 0) or 0,
        "httpOnly": bool(c.get("httpOnly", False)),
        "secure": bool(c.get("secure", True)),
        "sameSite": same_site,
    }
    return out


def cmd_import_cookies(args):
    with open(args.file, "r", encoding="utf-8") as f:
        raw = f.read()
    cookies = _parse_cookies(raw, args.domain)
    if not cookies:
        print("[ERR] 未从文件中解析到任何 cookie。支持：JSON 数组 / 含 cookies 键的 dict / document.cookie 文本。")
        sys.exit(1)
    cookies = [_normalize_cookie(c, args.domain) for c in cookies]
    state = {"cookies": cookies, "origins": []}
    with open(args.auth, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
    try:
        os.chmod(args.auth, 0o600)
    except Exception:
        pass
    print(f"[OK] 已导入 {len(cookies)} 个 cookie → {args.auth}（权限 600，请勿提交 git）")


# ---------------- 各命令 ----------------
def cmd_login(args):
    auth = args.auth
    pub = ToutiaoPublisher(auth_state=None, base_url=args.base, draft_path=args.draft,
                           headless=False, fast=True).launch()
    try:
        pub.page.goto(args.base, wait_until="domcontentloaded")
        input("请在弹出的浏览器中完成登录（扫码/凭证）。登录成功后回到此处按回车保存登录态...")
        pub.context.storage_state(path=auth)
        try:
            os.chmod(auth, 0o600)
        except Exception:
            pass
        print(f"[OK] 登录态已保存至 {auth}（权限 600，请勿提交到 git）")
    finally:
        pub.close()


def cmd_dry_run(args):
    """只读预览：真实登录进草稿箱，按发布顺序列出候选队列，绝不点发布。"""
    if not os.path.exists(args.auth):
        print(f"[ERR] 未找到 {args.auth}。请先执行 login 或 import-cookies 生成登录态。")
        sys.exit(1)
    pub = ToutiaoPublisher(auth_state=args.auth, base_url=args.base, draft_path=args.draft,
                           headless=not args.show, fast=True).launch()
    try:
        pub.goto_draft_box()
        published_set = set()
        print(f"[DRY-RUN] 将按以下顺序发布（共至多 {args.count} 条，不实际发布）：")
        for i in range(args.count):
            sel = pub.select_first_unpublished(published_set)
            if sel is None:
                print("[DRY-RUN] 草稿箱已无更多未发布内容。")
                break
            print(f"  {i + 1:02d}. {sel['title']}  ({sel['draft_id']})")
            published_set.add(sel["draft_id"])
        print("[DRY-RUN] 预览结束，未执行任何发布。")
    except NeedsLogin:
        print("[ERR] 登录态失效，请重新 login 或 import-cookies。")
    finally:
        pub.close()


def cmd_run_day(args):
    run_day(auth_state=args.auth, state_file=args.state, base_url=args.base,
            draft_path=args.draft, headless=not args.show, fast=False)


def cmd_run_forever(args):
    run_forever(auth_state=args.auth, state_file=args.state, base_url=args.base,
                draft_path=args.draft, headless=not args.show)


def cmd_mock_smoke(args):
    port = args.port
    os.environ["MOCK_FAIL_FIRST"] = str(args.fail_first)
    print(f"[MOCK] 启动本地 mock 草稿箱 :{port}，FAIL_FIRST={args.fail_first}，fast 模式冒烟...")
    srv = mock_server.start(port)
    try:
        run_day(auth_state=None,
                state_file=args.state,
                base_url=f"http://127.0.0.1:{port}",
                draft_path="/",
                headless=not args.show,
                fast=True)
    finally:
        srv.shutdown()
    st = load_state(args.state)
    print(f"[MOCK] 结束：published={len(st.get('published', []))} paused={st.get('paused')}")


def main():
    p = argparse.ArgumentParser(description="AIST2030 头条草稿箱批量发布")
    sub = p.add_subparsers(dest="cmd")

    pl = sub.add_parser("login", help="交互式扫码/凭证登录并保存 auth.json")
    pl.add_argument("--auth", default=DEFAULT_AUTH)
    pl.add_argument("--base", default=DEFAULT_BASE)
    pl.add_argument("--draft", default=DEFAULT_DRAFT)
    pl.set_defaults(func=cmd_login)

    pi = sub.add_parser("import-cookies", help="从 cookie 文件生成 auth.json（JSON数组/文本）")
    pi.add_argument("file", help="cookie 文件：JSON 数组 / 含 cookies 键的 dict / document.cookie 文本")
    pi.add_argument("--auth", default=DEFAULT_AUTH)
    pi.add_argument("--domain", default=".mp.toutiao.com", help="缺省 domain（cookie 无 domain 时补）")
    pi.set_defaults(func=cmd_import_cookies)

    pr = sub.add_parser("dry-run", help="只读预览候选队列（不发布）")
    pr.add_argument("--auth", default=DEFAULT_AUTH)
    pr.add_argument("--base", default=DEFAULT_BASE)
    pr.add_argument("--draft", default=DEFAULT_DRAFT)
    pr.add_argument("--count", type=int, default=29, help="最多列出条数")
    pr.add_argument("--show", action="store_true")
    pr.set_defaults(func=cmd_dry_run)

    pd = sub.add_parser("run-day", help="按日排期发布（cron 用）")
    pd.add_argument("--auth", default=DEFAULT_AUTH)
    pd.add_argument("--state", default=DEFAULT_STATE)
    pd.add_argument("--base", default=DEFAULT_BASE)
    pd.add_argument("--draft", default=DEFAULT_DRAFT)
    pd.add_argument("--show", action="store_true", help="有头模式（调试可见）")
    pd.set_defaults(func=cmd_run_day)

    pf = sub.add_parser("run-forever", help="常驻日循环（nohup 用）")
    pf.add_argument("--auth", default=DEFAULT_AUTH)
    pf.add_argument("--state", default=DEFAULT_STATE)
    pf.add_argument("--base", default=DEFAULT_BASE)
    pf.add_argument("--draft", default=DEFAULT_DRAFT)
    pf.add_argument("--show", action="store_true")
    pf.set_defaults(func=cmd_run_forever)

    pm = sub.add_parser("mock-smoke", help="本地 mock 草稿箱冒烟（不触真站）")
    pm.add_argument("--state", default=os.path.join(ROOT, "mock_state.json"))
    pm.add_argument("--port", type=int, default=8765)
    pm.add_argument("--fail-first", type=int, default=0, help="前 N 次 /publish 返回失败（测重试/暂停）")
    pm.add_argument("--show", action="store_true")
    pm.set_defaults(func=cmd_mock_smoke)

    args = p.parse_args()
    if not args.cmd:
        p.print_help()
        sys.exit(1)
    args.func(args)


if __name__ == "__main__":
    main()
