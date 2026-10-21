# 故障排除指南

## ❓ 常见问题

### Q1: 配置时提示"未找到free-model-gateway"
**解决方案**：
- 下载并安装AIST2030免费模型网关
- 确保gateway.js文件位于`%USERPROFILE%\.workbuddy\free-model-gateway\`目录
- 运行`start-gateway.bat`启动网关

### Q2: 一句话配置没有反应
**解决方案**：
- 确保WorkBuddy版本为5.8.0或更高版本
- 检查网络连接（需要访问本地网关）
- 重启WorkBuddy应用

### Q3: 智能调优没有学习我的习惯
**解决方案**：
- 确保您已经使用了至少5次不同类型的查询
- 检查用户数据文件是否存在：`%USERPROFILE%\.workbuddy\aist2030-model-manager\user-data.json`
- 运行`/reset aist2030-model-manager`重置学习数据

## 🛠️ 技术支持命令

```bash
# 查看系统状态
/status

# 重新初始化
/init

# 重置所有配置
/reset

# 查看日志
/logs

# 联系客服
/support
```

## 📞 客服支持

- **客服电话**：18589521211（工作时间：9:00-21:00）
- **技术支持邮箱**：2265205847@qq.com
- **官方网址**：省团.cn
- **地址**：贵阳市南明区中环广场1号1915

---

*© 2026 贵州省团之家智付科技有限公司 | AIST2030品牌*