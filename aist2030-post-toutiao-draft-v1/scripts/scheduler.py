"""每日发布控制器：按 8 个高峰时段配额，以 ≥15min 间隔自调度 29 次发布。

时段配额（单日全量，合计 29）：
  08:00×3  10:00×2  12:00×3  14:00×2
  17:00×4  19:00×5  21:00×6  23:00×4
每个时段内从起点向后按 15min 铺开；相邻两次间隔 ≥15min，时段内不越界。

执行模型：
- run_day：处理一整天（进程因 sleep 全天存活，末次发布后退出，次日由 cron 重新拉起）。
- run_forever：无 cron 场景，自带日循环（nohup 常驻，满足"保持后台运行"）。
"""
import os
import time
import urllib.request
from datetime import datetime, timedelta, timezone

from state import load_state, save_state, published_ids, mark_published, set_paused
from toutiao_publisher import ToutiaoPublisher, NeedsLogin, PublishError

TZ8 = timezone(timedelta(hours=8))

# 时段（时:分, 配额）
SLOT_PLAN = [
    ("08:00", 3), ("10:00", 2), ("12:00", 3), ("14:00", 2),
    ("17:00", 4), ("19:00", 5), ("21:00", 6), ("23:00", 4),
]
TOTAL = sum(c for _, c in SLOT_PLAN)  # 29


def build_timeline(today=None):
    """展开为 29 个绝对时刻（按当日日期）。"""
    today = today or datetime.now(TZ8).date()
    times = []
    for hhmm, cnt in SLOT_PLAN:
        h, m = map(int, hhmm.split(":"))
        base = datetime(today.year, today.month, today.day, h, m, tzinfo=TZ8)
        for i in range(cnt):
            times.append(base + timedelta(minutes=15 * i))
    return times


def notify(msg, hook=None):
    line = f"{datetime.now(TZ8).isoformat()} {msg}\n"
    try:
        with open("notify.log", "a", encoding="utf-8") as f:
            f.write(line)
    except Exception:
        pass
    hook = hook or os.environ.get("TOUTIAO_NOTIFY_HOOK")
    if hook:
        try:
            urllib.request.urlopen(urllib.request.Request(hook, data=line.encode(), method="POST"))
        except Exception:
            pass


def _sleep_until(target):
    secs = (target - datetime.now(TZ8)).total_seconds()
    if secs > 0:
        time.sleep(secs)


def _sleep_until_tomorrow(hour=7, minute=55):
    now = datetime.now(TZ8)
    nxt = (now + timedelta(days=1)).replace(hour=hour, minute=minute, second=0, microsecond=0)
    secs = (nxt - now).total_seconds()
    if secs > 0:
        time.sleep(secs)


def run_day(auth_state="auth.json", state_file="state.json",
            base_url="https://mp.toutiao.com", draft_path="/profile_v4/manage/draft",
            headless=True, fast=False, interval_sec=None):
    """处理一整天的发布排期。fast=True 用于 mock 冒烟（压缩间隔、不等待绝对时刻）。"""
    interval = float(interval_sec if interval_sec is not None else (0.1 if fast else 900))
    state = load_state(state_file)
    published_set = published_ids(state)

    pub = ToutiaoPublisher(auth_state=auth_state, base_url=base_url,
                           draft_path=draft_path, headless=headless, fast=fast).launch()
    try:
        if state.get("paused"):
            notify("检测到 paused=true，跳过本日运行；请排查后清除 paused 标志再重跑。")
            print("[SKIP] paused=true，已跳过。")
            return

        timeline = build_timeline()
        done = 0
        for idx, t in enumerate(timeline):
            if not fast:
                _sleep_until(t)
            try:
                sel = pub.publish_one(state, published_set)
            except NeedsLogin:
                notify("登录失效，需重新执行 login 生成 auth.json。")
                set_paused(state, True)
                save_state(state_file, state)
                print("[PAUSE] 登录失效，已暂停并通知。")
                return
            except PublishError as e:
                notify(f"[PAUSE] 发布异常，已暂停：{e}")
                set_paused(state, True)
                save_state(state_file, state)
                print(f"[PAUSE] 已暂停并通知：{e}")
                return
            if sel is None:
                print("[INFO] 草稿箱已无未发布内容，今日提前结束。")
                break
            mark_published(state, sel["draft_id"], sel["title"])
            save_state(state_file, state)
            published_set.add(sel["draft_id"])
            print(f"[OK] 已发布 {sel['title']} @ {datetime.now(TZ8).isoformat()}")
            done += 1
            if idx < len(timeline) - 1:
                time.sleep(interval)
        print(f"[DAY] 今日发布 {done} 条，浏览器保持运行；进程将于末次发布后退出，次日由 cron 重新拉起。")
    except KeyboardInterrupt:
        print("[INT] 用户中断。")
    finally:
        pub.close()


def run_forever(auth_state="auth.json", state_file="state.json",
                base_url="https://mp.toutiao.com", draft_path="/profile_v4/manage/draft", headless=True):
    """无 cron 常驻模式：自带日循环，满足"保持后台运行以备次日任务"。"""
    while True:
        run_day(auth_state, state_file, base_url, draft_path, headless, fast=False)
        _sleep_until_tomorrow()
