# link-image-fetch 使用说明

通过网页分享链接**批量提取图片**，并尽量拿到**原图**（优先取平台自身提供的 raw / 原始分辨率版本；拿不到水印版时用 OpenCV 兜底抹除角标水印）。

> 当前已实现：**豆包（doubao.com）**、**微信公众号文章（mp.weixin.qq.com）**。架构支持持续扩展其他平台（文心等按同模式补充即可）。

---

## 一、环境要求

- **Python 3.8+**（脚本仅用标准库 `urllib`，正常取原图流程不依赖任何第三方库）。
- **OpenCV 兜底（可选）**：当某链接只有带水印模板、没有原图版本时，会下载带水印版并用 `opencv-python` 抹除角标。启用兜底前先装：
  ```bash
  pip install opencv-python
  ```
  > 不装也能用，只是那种极端情况下会保留带水印版原样下载，不会报错。微信平台不走这条路径。

---

## 二、使用方法

### 单链接
```bash
# 豆包
python scripts/fetch.py "https://www.doubao.com/thread/分享ID" ./out

# 微信公众号文章
python scripts/fetch.py "https://mp.weixin.qq.com/s?__biz=...&mid=...&idx=1&sn=..." ./out
```

### 多链接批量（可跨平台混着来）
```bash
python scripts/fetch.py "https://www.doubao.com/thread/AAA" "https://mp.weixin.qq.com/s?BBB" ./out
```
- 从第一个 `http(s)` 参数起都是链接；**最后一个非 http 参数**视为输出目录（默认 `fetched_images`）。
- 链接可带 `?share_token=...`、`&scene=27` 等查询参数，不影响解析。

### 运行方式注意（WorkBuddy / 沙箱环境）
脚本需要**联网访问目标站点**。在 WorkBuddy 沙箱内网络可能被静默拦截（表现为空输出、退出码 0），必须放开沙箱才能跑通。

### Windows / Git Bash 路径坑
`/c/Users/...` 会被错解为 `D:\c\Users\...`，写文件或跑脚本一律用 `C:/Users/...` 绝对路径。

---

## 三、豆包适配器原理（简述）

1. 从 URL 取 `share_id`：以 `x` 开头 → `im/message/share/get`；否则 → `samantha/thread/share/snapshot/get`。
2. 调用接口拉取完整对话 JSON。
3. 递归提取图片 URL：普通对话走 `file_list[].url_list[]`；图片生成类对话嵌套在字符串化 JSON 中，用正则抓已签名的 `image_raw.png` 链接。
4. 将模板后缀替换为 `image_raw.png` 即得平台原图，带 Referer 下载。
5. raw 失败 → 回退带水印版 →（可选）OpenCV 去水印。

**图片 URL 模板（byteimg）**
```
基础: https://p{N}-flow-imagex-sign.byteimg.com/tos-cn-i-a9rns2rl98/rc_gen_image/{hash}.jpeg~tplv-a9rns2rl98-{template}.png?...
template:
- image_raw.png               → 平台原图(优先, 无水印)
- image_dld_watermark_1_5.png → 下载水印版(右下角"豆包AI生成")
- downsize_watermark_1_5.png  → 缩略+水印版
```

---

## 四、微信公众号适配器原理（简述）

公众号图文页是**服务端直出的静态 HTML**，无需登录态、无需调内部接口，抓 HTML 正则即可。

1. 用 iPhone 微信 UA 请求 `mp.weixin.qq.com/s?...`（公开文章可直接访问）。
2. **限定正文区**：从 `id="js_content"` 截到 `js_pc_qr_code` / `rich_media_area_extra` 等结束标记，避免抓到文末推荐位、评论区、二维码的图。
3. 按文档顺序扫 `data-src` / `data-croporisrc` / `data-backsrc` / `data-original` / `data-cover` / `src` 属性 + CSS `background-image:url(...)`，只保留 `mmbiz.qpic.cn`（排除 `mmbiz.qlogo.cn` 头像/二维码）。
4. **取原图（关键，实测）**：

```
正文 URL: https://mmbiz.qpic.cn/sz_mmbiz_jpg/<hash>/640?wx_fmt=jpeg&from=appmsg&tp=wxpic&wxfrom=5&wx_lazy=1&watermark=1#imgIndex=1
                                              └ 宽度上限
转换:  /640 → /0      # 原始分辨率（实测 PNG 1080x864 → 1402x1122）
       只保留 wx_fmt   # 丢掉 watermark / tp / wxfrom / wx_lazy
       去 #imgIndex=N
       ⚠️ sz_ 前缀必须保留！去掉会返回 243 字节的错误占位 PNG
```

5. **两个必踩的坑**
   - **视频封面**：在 `<iframe class="video_iframe">` 的 `data-cover` 里，是**整体 URL 编码**的（`http%3A%2F%2F...`），必须 `unquote` 后才能用 —— 否则报 `unknown url type`。
   - **重复图**：长文常把同一组图**插两次**。下载后用感知哈希（16x16 灰度均值哈希，汉明距离 ≤8）排重，重复项移入 `_重复图(可删)` 子目录，不要直接删。

---

## 五、扩展新平台

新增一个平台只需在 `scripts/platforms/` 下新建 `<平台>.py`，实现：

```python
SUPPORTED_HOSTS = ['xxx.com']

def extract(share_url) -> list[dict]:
    """返回 [{'hash', 'raw_url', 'wm_url'}, ...]"""
    ...
```

并在 `scripts/fetch.py` 的 `PLATFORMS` 字典登记即可。`common.py` 提供下载去重、后缀嗅探与 OpenCV 去水印兜底，平台无需自己实现。

**entry 可选字段**：`skip_inpaint: True` —— 该平台图片本身无角标水印时跳过 OpenCV 兜底（微信已启用）。

---

## 六、注意事项（务必读）

1. **图片 URL 含签名与过期时间**（`x-signature` / `x-expires`），有效期通常数年，但建议**尽快下载**，过期会 403。
2. **Referer 防盗链**：请求必须带原分享页 URL 作为 Referer，否则返回 403。脚本已自动处理。
3. **豆包 `/chat/` 个人页无法直接提取**：需登录态，无 session 会返回“登录已过期”。请在豆包内对该对话点「分享」生成 `thread` 链接后再提取。**不要索取登录 cookie**。
4. **微信仅支持 `mp.weixin.qq.com/s?...` 图文页**：需要关注后才能看、已删除、违规下架、被“环境异常”拦截的文章无法提取。文末推荐位/评论区/二维码的图会被主动排除。文章内**视频只能取封面图**。
5. **OpenCV 对水印类型有限**：仅对**角落角标**类水印（如右下角平台标识）有效；对平铺/半透明/复杂水印属尽力而为。
6. **接口可能失效**：豆包依赖未公开接口，平台改版需重新逆向适配。

---

## 七、使用边界声明（合规）

本技能仅用于提取**用户本人分享链接中、用户本人生成/上传的图片**，供**个人与受控的内部团队**留存使用：

- 不得用于去除**他人版权内容**的水印；
- 不得用于规避平台技术保护措施；
- 不得对外分发本工具或用于商业牟利；
- 图片版权归原作者/平台所有，使用须遵守对应平台服务条款。

---

## 目录结构

```
link-image-fetch/
  SKILL.md              # skill 元信息 + 触发说明
  README.md             # 本文件
  scripts/
    fetch.py            # CLI 入口：按 host 分发、支持多链接
    common.py           # 下载去重 + 后缀嗅探 + OpenCV 去水印兜底
    platforms/
      __init__.py
      doubao.py         # 豆包适配器（已实现）
      wechat.py         # 微信公众号文章适配器（已实现）
      wenxin.py         # 文心（占位，待按同模式补充）
```
