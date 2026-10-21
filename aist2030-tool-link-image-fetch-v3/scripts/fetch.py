#!/usr/bin/env python3
"""
链接批量取无水印图 (多平台可扩展)

用法:
  python fetch.py <url1> [url2 ...] [output_dir]

- 所有以 http(s) 开头的参数视为分享链接(可多个, 批量处理);
- 最后一个非 http(s) 参数视为输出目录(默认 fetched_images)。
- 按链接 host 自动分发到 platforms/ 下对应适配器。
"""
import os
import sys
import importlib

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

# host -> 平台适配器模块。新增平台在此登记。
PLATFORMS = {
    'mp.weixin.qq.com': 'platforms.wechat',   # 微信公众号图文
    'doubao.com': 'platforms.doubao',
    # 'yixinar.com': 'platforms.wenxin',  # 文心待实现
}


def pick_platform(url):
    for host, mod in PLATFORMS.items():
        if host in url:
            return importlib.import_module(mod)
    return None


def main():
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        sys.exit(1)

    urls, out = [], 'fetched_images'
    for a in args:
        if a.startswith('http://') or a.startswith('https://'):
            urls.append(a)
        else:
            out = a
    if not urls:
        print('未提供有效链接')
        sys.exit(1)

    from common import download_images

    total_ok = 0
    for url in urls:
        mod = pick_platform(url)
        if not mod:
            print(f'[跳过] 不支持的链接: {url}')
            continue
        print('=' * 60)
        print(f'链接: {url}')
        print(f'平台: {getattr(mod, "SUPPORTED_HOSTS", ["?"])}')
        try:
            entries = mod.extract(url)
        except Exception as e:
            print(f'[错误] {e}')
            continue
        print(f'发现 {len(entries)} 个图片(去重后)')
        total_ok += download_images(entries, out, url)

    print('=' * 60)
    print(f'全部完成, 成功下载: {total_ok}')


if __name__ == '__main__':
    main()
