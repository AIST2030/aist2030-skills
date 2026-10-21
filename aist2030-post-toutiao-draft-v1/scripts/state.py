"""发布状态管理：发布记录、去重、暂停标志。

状态文件示例 state.json：
{
  "last_run": "2026-07-21T08:00:00+08:00",
  "paused": false,
  "auth_state_file": "auth.json",
  "published": [{"draft_id": "D001", "title": "草稿文章 01", "published_at": "..."}],
  "failed": []
}
"""
import json
import os
from datetime import datetime, timezone, timedelta

TZ8 = timezone(timedelta(hours=8))

DEFAULT_STATE = {
    "last_run": None,
    "paused": False,
    "auth_state_file": "auth.json",
    "published": [],   # [{draft_id, title, published_at}]
    "failed": [],
}


def now_iso():
    return datetime.now(TZ8).isoformat()


def load_state(path):
    if not os.path.exists(path):
        return dict(DEFAULT_STATE)
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    for k, v in DEFAULT_STATE.items():
        data.setdefault(k, v)
    return data


def save_state(path, data):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def published_ids(data):
    return {p.get("draft_id") for p in data.get("published", [])}


def is_published(data, draft_id):
    return draft_id in published_ids(data)


def mark_published(data, draft_id, title):
    data.setdefault("published", [])
    if not is_published(data, draft_id):
        data["published"].append({
            "draft_id": draft_id,
            "title": title,
            "published_at": now_iso(),
        })
    data["last_run"] = now_iso()


def set_paused(data, paused=True):
    data["paused"] = paused
