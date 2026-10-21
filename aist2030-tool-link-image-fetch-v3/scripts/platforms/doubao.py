#!/usr/bin/env python3
"""豆包(doubao.com) 分享链接适配器。

extract(share_url) -> [{'hash','raw_url','wm_url'}]
raw_url 为平台提供的 image_raw 原图(优先, 无水印);
wm_url 为带水印版(仅 raw 不可用时作兜底源)。
"""
import json
import os
import re
import sys
import urllib.request
import urllib.error

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))  # 让 common 可被 import
from common import clean_url, hash_from_url  # noqa: E402

SUPPORTED_HOSTS = ['doubao.com']


def extract_share_id(url):
    """从分享 URL 提取 share_id(支持大小写字母)。"""
    m = re.search(r'thread/([A-Za-z0-9]+)', url)
    if not m:
        raise ValueError(f"无法解析 share_id, 需 doubao.com/thread/<id>, 实际: {url}")
    return m.group(1)


def to_raw_url(url):
    """将任意豆包图片 URL 转换为平台提供的原图(raw)版本。"""
    if not url or 'image_raw' in url:
        return url
    raw = re.sub(r'image_[a-z_]*watermark[_0-9]*\.png', 'image_raw.png', url)
    raw = re.sub(r'downsize_watermark[_0-9]*\.png', 'image_raw.png', raw)
    if '~tplv-' in raw and not raw.endswith('.png'):
        raw = re.sub(r'\.[a-z]+\?', '.png?', raw)
    return raw


def to_watermark_url(url):
    """把 raw 模板换成平台下载水印版(仅作 raw 不可用时的兜底源)。"""
    if not url:
        return url
    if 'watermark' in url:
        return url
    wm = re.sub(r'image_raw\.png', 'image_dld_watermark_1_5.png', url)
    if wm == url and '~tplv-' in url:
        wm = re.sub(r'(~tplv-[A-Za-z0-9]+-)image_raw', r'\1image_dld_watermark_1_5', wm)
    return wm


def fetch_dialog_data(share_id, referer):
    """根据 share_id 类型选择对应 API 请求数据。"""
    if share_id.startswith('x'):
        api_url = 'https://www.doubao.com/im/message/share/get'
        payload = {'share_id': share_id, 'need_bot_info': True}
    else:
        api_url = 'https://www.doubao.com/samantha/thread/share/snapshot/get'
        payload = {'share_id': share_id, 'need_bot': False}

    req = urllib.request.Request(api_url, data=json.dumps(payload).encode(), headers={
        'Content-Type': 'application/json',
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Agw-Js-Conv': 'str',
        'Referer': referer,
    })
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = resp.read()
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"API请求失败 HTTP {e.code}: {e.reason} (share_id={share_id})")
    except Exception as e:
        raise RuntimeError(f"API请求失败: {e}")

    ct = resp.headers.get('Content-Type', '')
    if 'json' not in ct and not body.lstrip().startswith(b'{'):
        raise RuntimeError(f"API未返回JSON(Content-Type={ct}), 可能链接失效或需登录. "
                           f"响应前120字节: {body[:120]!r}")
    return json.loads(body)


def extract_image_urls(data):
    """递归遍历 JSON 提取所有图片 URL 并转换为 raw 版本。"""
    by_hash = {}

    def _register(raw_u, wm_u):
        h = hash_from_url(raw_u) or hash_from_url(wm_u)
        if not h:
            return
        entry = by_hash.setdefault(h, {'hash': h, 'raw_url': None, 'wm_url': None})
        if raw_u:
            ru = clean_url(to_raw_url(raw_u))
            if entry['raw_url'] is None or ('image_raw' in ru and 'image_raw' not in entry['raw_url']):
                entry['raw_url'] = ru
        if wm_u and 'watermark' in wm_u:
            entry['wm_url'] = clean_url(wm_u)
        elif entry['wm_url'] is None and raw_u:
            entry['wm_url'] = clean_url(to_watermark_url(raw_u))

    def _walk(obj):
        if isinstance(obj, dict):
            if 'url_list' in obj and isinstance(obj['url_list'], list):
                for item in obj['url_list']:
                    url = item.get('url', '')
                    if 'byteimg' in url and re.search(r'\.(png|jpe?g)', url, re.I):
                        _register(url, url)
                return
            for v in obj.values():
                _walk(v)
        elif isinstance(obj, list):
            for item in obj:
                _walk(item)

    _walk(data)

    # 兜底: 图片生成类对话的图片嵌套在字符串化 JSON 里(无 url_list)。
    if not by_hash:
        text = json.dumps(data, ensure_ascii=False)
        all_urls = re.findall(r'https?://[^\s"\\]+?byteimg\.com/[^\s"\\]+', text)
        for u in all_urls:
            u = clean_url(u)
            if re.search(r'\.(png|jpe?g)', u, re.I):
                _register(u, u)

    return list(by_hash.values())


def extract(share_url):
    """适配器入口: 返回图片条目列表。"""
    share_id = extract_share_id(share_url)
    data = fetch_dialog_data(share_id, share_url)
    return extract_image_urls(data)
