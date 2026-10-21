"""头条草稿箱自动发布核心：Playwright 驱动，只读点击「立即发布」。

设计铁律：
- 只发不写：对标题/封面/正文只读取用于定位，零写入；仅点击「立即发布」。
- 去重：每次选区前查本地 state.published，已发布 id 永不二次点击。
- 登录态：优先用 auth.json（Playwright storage_state）；缺失则抛 NeedsLogin 交由 CLI 走登录流程。
- 异常：publish_one 内置 1+max_retries 次尝试，全部失败后抛 PublishError 交由调度器暂停。
"""
import os
import time
from datetime import datetime, timezone, timedelta

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    sync_playwright = None

TZ8 = timezone(timedelta(hours=8))


class NeedsLogin(Exception):
    pass


class PublishError(Exception):
    pass


def now_iso():
    return datetime.now(TZ8).isoformat()


class ToutiaoPublisher:
    def __init__(self, auth_state=None, base_url="https://mp.toutiao.com",
                 draft_path="/profile_v4/manage/draft", headless=True, fast=False):
        if sync_playwright is None:
            raise RuntimeError("Playwright 未安装：pip install playwright && playwright install chromium")
        self.auth_state = auth_state
        self.base_url = base_url.rstrip("/")
        self.draft_path = draft_path
        self.headless = headless
        self.fast = fast
        self.browser = None
        self.context = None
        self.page = None
        self._pw = None

    # ---------- 生命周期 ----------
    def launch(self):
        storage = self.auth_state if (self.auth_state and os.path.exists(self.auth_state)) else None
        exe = None
        for c in ("/usr/bin/google-chrome", "/usr/bin/google-chrome-stable", "/usr/bin/chromium"):
            if os.path.exists(c):
                exe = c
                break
        self._pw = sync_playwright().start()
        try:
            self.browser = self._pw.chromium.launch(headless=self.headless, executable_path=exe)
        except Exception:
            self.browser = self._pw.chromium.launch(headless=self.headless)
        ctx_kwargs = {}
        if storage:
            ctx_kwargs["storage_state"] = storage
        self.context = self.browser.new_context(**ctx_kwargs)
        self.page = self.context.new_page()
        return self

    def close(self):
        for fn in ("context", "browser", "_pw"):
            obj = getattr(self, fn, None)
            try:
                if obj:
                    obj.close() if fn != "_pw" else obj.stop()
            except Exception:
                pass

    # ---------- 页面操作（只读） ----------
    def goto_draft_box(self):
        url = self.base_url + self.draft_path
        try:
            self.page.goto(url, wait_until="domcontentloaded", timeout=30000)
        except Exception:
            self.page.goto(self.base_url, wait_until="domcontentloaded", timeout=30000)
        try:
            self.page.wait_for_selector(".draft-item, [class*='draft'], [class*='article']", timeout=20000)
        except Exception:
            pass
        if self._is_login_page():
            raise NeedsLogin("检测到未登录，请先执行 login 流程生成 auth.json")

    def _is_login_page(self):
        try:
            return ("passport" in self.page.url) or (self.page.locator("input[type='password']").count() > 0)
        except Exception:
            return False

    def select_first_unpublished(self, published_set):
        """选区：DOM 首行且 data-id 不在 published_set 中的草稿（未发布且未标记首条）。"""
        items = self.page.locator(".draft-item")
        n = items.count()
        for i in range(n):
            it = items.nth(i)
            try:
                did = it.get_attribute("data-id") or ""
            except Exception:
                did = ""
            if did in published_set:
                continue
            try:
                if "published" in (it.get_attribute("class") or ""):
                    continue
            except Exception:
                pass
            try:
                title = it.locator(".title, [class*='title']").first.inner_text().strip()
            except Exception:
                title = did or f"row{i}"
            btn = it.locator("button:has-text('立即发布'), .publish-btn")
            return {"draft_id": did, "title": title, "el": it, "btn": btn}
        return None

    def _wait_publish_result(self, timeout=15000):
        """轮询等待发布结果并判定（对 toast 短时消失也鲁棒）。

        成功判定：出现 .toast-success，或任意「立即发布」按钮变为「已发布」。
        失败判定：出现 .toast-error。
        """
        deadline = time.time() + timeout / 1000.0
        while time.time() < deadline:
            if self.page.locator(".toast-success").count() > 0:
                return
            if self.page.locator("button:text('已发布')").count() > 0:
                return
            if self.page.locator(".toast-error").count() > 0:
                raise PublishError("页面提示发布失败")
            time.sleep(0.3)
        raise PublishError("发布结果确认超时（未出现成功/失败提示）")

    def publish_one(self, state, published_set, max_retries=2):
        """发布一条：选首条未发布 → 点击立即发布 → 确认结果。

        内置 1 + max_retries 次尝试；全部失败抛 PublishError。
        返回选中元数据；若无更多草稿返回 None。
        """
        last_err = None
        for attempt in range(1 + max_retries):
            try:
                self.goto_draft_box()
                sel = self.select_first_unpublished(published_set)
                if sel is None:
                    return None
                sel["btn"].first.click(timeout=10000)
                self._wait_publish_result()
                return sel
            except Exception as e:
                last_err = e
                time.sleep(2 if not self.fast else 0.2)
        raise PublishError(f"发布失败（已重试{max_retries}次）：{last_err}")
