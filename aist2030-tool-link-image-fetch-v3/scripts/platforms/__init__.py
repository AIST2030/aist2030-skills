# 平台适配器包。新增平台: 在此目录新建 <平台>.py, 实现
# SUPPORTED_HOSTS (host 匹配列表) 与 extract(share_url) -> [{hash, raw_url, wm_url}],
# 并在 scripts/fetch.py 的 PLATFORMS 登记。
