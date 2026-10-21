#!/usr/bin/env python3
"""微信公众号文章适配器 (mp.weixin.qq.com/s?...)

原理:
  公众号图文页是服务端直出的静态 HTML, 正文图片以 `data-src`(懒加载) 形式挂在
  <img> 上, 部分以 CSS background-image 形式挂在 <span>/<section> 上。无需登录态,
  无需调用任何内部接口 —— 直接抓 HTML 正则抽取即可。

取原图规则 (mmbiz.qpic.cn CDN, 实测):
  正文里的 URL 形如
    https://mmbiz.qpic.cn/sz_mmbiz_jpg/<hash>/640?wx_fmt=jpeg&from=appmsg&tp=wxpic&wxfrom=5&wx_lazy=1&watermark=1#imgIndex=1
  - 路径末段的数字是"宽度上限": /640 → 会被压到 640 宽; 换成 /0 → 原始分辨率。
    实测 PNG 1080x864 → 1402x1122, JPG 大图也可能被裁。
  - `sz_` 前缀必须保留! 实测去掉 sz_ 会返回 243 字节的错误占位 PNG。
  - `watermark=1` / `tp=wxpic` / `wxfrom` / `wx_lazy` 都是展示参数, 去掉不影响出图,
    且能规避平台叠加层。只保留 wx_fmt 决定返回格式。
  微信文章本身一般无可见水印, 所以 raw 拿到即可, 通常不需要 OpenCV 兜底。
"""
import re
import urllib.parse
import urllib.request

SUPPORTED_HOSTS = ['mp.weixin.qq.com']

UA = ('Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 '
      '(KHTML, like Gecko) Mobile/15E148 MicroMessenger/8.0.49(0x18003128) NetType/WIFI Language/zh_CN')

# 正文区结束标记(取最先出现的那个), 避免抓到文末推荐位/评论区/二维码的图
_BODY_END_MARKERS = [
    'id="js_pc_qr_code"',
    'class="rich_media_area_extra"',
    'id="content_bottom_area"',
    'id="js_cmt_area"',
    'id="js_article_comment"',
]

# 正文中承载图片的属性
_SRC_ATTRS = (
    'data-src', 'data-croporisrc', 'data-backsrc', 'data-original',
    'data-cover', 'src',
)

_BLOCK_HINTS = (
    '该内容已被发布者删除',
    '此内容因违规无法查看',
    '环境异常',
    '去验证',
    '参数错误',
    '请在微信客户端打开链接',
)


def _fetch_html(url):
    req = urllib.request.Request(url, headers={
        'User-Agent': UA,
        'Accept-Language': 'zh-CN,zh;q=0.9',
    })
    with urllib.request.urlopen(req, timeout=60) as r:
        raw = r.read()
    for enc in ('utf-8', 'gbk'):
        try:
            return raw.decode(enc, errors='ignore')
        except Exception:
            continue
    return raw.decode('utf-8', errors='ignore')


def _body_region(html):
    """截取正文区域, 抓不到就退回整篇(宁多勿漏)。"""
    i = html.find('id="js_content"')
    if i < 0:
        return html
    ends = [html.find(m, i) for m in _BODY_END_MARKERS]
    ends = [e for e in ends if e > i]
    return html[i:min(ends)] if ends else html[i:]


def _collect_urls(region):
    """按文档顺序收集正文图片 URL(去重)。"""
    found, seen, out = [], set(), []
    for attr in _SRC_ATTRS:
        found += re.findall(attr + r'\s*=\s*["\']([^"\']+)["\']', region)
    # CSS 背景图: background-image:url(...) / background:url(...)
    found += re.findall(r'background(?:-image)?\s*:\s*url\(([^)]+)\)', region)
    # 兜底: 正文里裸写的 CDN 直链
    found += re.findall(r'https?://[a-z0-9.]*mmbiz\.qpic\.cn/[^\s"\'\\<>)]+', region)

    for u in found:
        u = u.strip().strip('\'"')
        if 'mmbiz.qpic.cn' not in u or 'mmbiz.qlogo.cn' in u:
            continue
        u = u.replace('&amp;', '&').rstrip('\\')
        # 视频封面(data-cover)等字段是整体 URL 编码的: http%3A%2F%2Fmmbiz...
        if '%3A%2F%2F' in u.lower() or '%2f%2f' in u.lower():
            u = urllib.parse.unquote(u)
        u = u.split('#')[0]                      # 去掉 #imgIndex=N
        m = re.search(r'/(?:sz_)?mmbiz_\w+/([A-Za-z0-9]+)', u)
        key = m.group(1) if m else u
        if key in seen:
            continue
        seen.add(key)
        out.append((key, u))
    return out


def to_raw(url):
    """把展示用 URL 转成原图 URL(见模块文档)。"""
    u = url.replace('&amp;', '&').split('#')[0].strip()
    if u.startswith('http://'):
        u = 'https://' + u[len('http://'):]

    # 只保留 wx_fmt, 丢掉 watermark / tp / wxfrom / wx_lazy 等展示参数
    path, _, query = u.partition('?')
    fmt = ''
    if query:
        m = re.search(r'wx_fmt=([a-zA-Z0-9]+)', query)
        if m:
            fmt = m.group(1)

    # 宽度上限 -> 0(原图)。注意保留 sz_ 前缀, 去掉会返回错误占位图。
    path = re.sub(r'/(\d+)$', '/0', path)

    return path + ('?wx_fmt=' + fmt if fmt else '')


def extract(share_url):
    html = _fetch_html(share_url)
    for hint in _BLOCK_HINTS:
        if hint in html and 'js_content' not in html:
            raise RuntimeError(f'页面不可访问或需验证: 命中「{hint}」。请确认文章为公开可访问。')

    region = _body_region(html)
    pairs = _collect_urls(region)
    if not pairs:
        raise RuntimeError('正文中未找到图片。若文章需关注/验证后才能看, 请先在微信里打开一次。')

    entries = []
    for key, u in pairs:
        entries.append({
            'hash': key,
            'raw_url': to_raw(u),
            'wm_url': u,              # 原样兜底(微信通常无可见水印)
            'skip_inpaint': True,     # 文章图无角标水印, 别用 inpainting 糊边角
        })
    return entries


if __name__ == '__main__':
    import sys
    for e in extract(sys.argv[1]):
        print(e['hash'][:12], e['raw_url'])
