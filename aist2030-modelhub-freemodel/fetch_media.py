#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
媒体素材获取器：防重复 + 智能匹配
- 读取 media_registry.json
- 从 Mixkit / cc0.cn 获取视频/图片
- 标记已用素材，避免跨会话重复
"""
import json
import os
import sys
from pathlib import Path

# 当前脚本所在目录
ROOT_DIR = Path(__file__).parent


def load_registry():
    registry_path = ROOT_DIR / "media_registry.json"
    if registry_path.exists():
        with open(registry_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {"used": [], "lastUsed": {}}


def save_registry(registry):
    registry_path = ROOT_DIR / "media_registry.json"
    with open(registry_path, 'w', encoding='utf-8') as f:
        json.dump(registry, f, ensure_ascii=False, indent=2)


def select_background_video(keyword: str) -> str:
    """选择背景视频（模拟 Mixkit API）"""
    registry = load_registry()

    # 候选视频列表（实际中应调用 Mixkit API）
    candidates = [
        "https://assets.mixkit.co/videos/40766/40766-large.mp4",  # lifestyle
        "https://assets.mixkit.co/videos/5592/5592-large.mp4",  # tech interface
        "https://assets.mixkit.co/videos/5905/5905-large.mp4",  # data flow
        "https://assets.mixkit.co/videos/5935/5935-large.mp4",  # abstract network
        "https://assets.mixkit.co/videos/5951/5951-large.mp4",  # digital transformation
    ]

    # 过滤已用
    unused = [url for url in candidates if url not in registry["used"]]
    if not unused:
        # 全部用过 → 清空 registry（仅开发期）
        registry["used"] = []
        save_registry(registry)
        return candidates[0]

    # 简单关键词打分
    scores = []
    for url in unused:
        score = 0
        if "模型" in keyword or "AI" in keyword:
            score += 2
        if "调度" in keyword or "flow" in keyword:
            score += 3
        if "安全" in keyword or "私有" in keyword:
            score += 1
        scores.append((url, score))

    scores.sort(key=lambda x: x[1], reverse=True)
    best_url = scores[0][0]

    registry["used"].append(best_url)
    registry["lastUsed"][best_url] = int(__import__('time').time())
    save_registry(registry)

    return best_url


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python fetch_media.py <keyword>")
        sys.exit(1)

    keyword = sys.argv[1]
    video_url = select_background_video(keyword)
    print(video_url)