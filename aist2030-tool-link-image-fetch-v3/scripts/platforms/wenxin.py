#!/usr/bin/env python3
"""文心一言/文小言 分享链接适配器 —— 待实现。

实现方式(同 doubao.py 模式):
1. 逆向前端 chunk 找到分享数据接口;
2. extract(share_url) 返回 [{hash, raw_url, wm_url}], 其中 raw_url 为文心原图模板;
3. 在 ../fetch.py 的 PLATFORMS 登记 'yixinar...' 等 host。

注意: 各平台"原图/水印"URL 模板不同, 原生取原图逻辑写在适配器内,
OpenCV 兜底由 common.py 统一提供, 无需在此重复。
"""
SUPPORTED_HOSTS = []  # 例: ['yixinar.com', 'wenxin.baidu.com']


def extract(share_url):
    raise NotImplementedError("文心适配器尚未实现, 请按 doubao.py 模式补充。")
