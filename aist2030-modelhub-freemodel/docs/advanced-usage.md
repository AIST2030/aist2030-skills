# 高级使用指南

## 🧠 智能调优深度配置

### 自定义偏好设置

您可以通过以下命令自定义智能调优参数：

```bash
# 设置默认场景偏好
/set-preference default-category technical

# 设置响应速度偏好
/set-preference response-speed fast

# 设置质量偏好
/set-preference quality balanced

# 查看当前偏好
/get-preference
```

### 手动模型选择

虽然系统会自动选择最优模型，您也可以手动指定（下面是 2026-10-21 全渠道体检后**实测可用**的模型）：

```bash
# 自动调度（推荐：最快最稳，首选渠道挂了会自动换家）
/model auto

# GLM-4-9B（硅基流动·最快 0.3s，综合最强）
/model THUDM/GLM-4-9B-0414

# Qwen2.5-7B（硅基流动·代码与结构化输出强 0.25s）
/model Qwen/Qwen2.5-7B-Instruct

# GLM-4-Flash（智谱·中文通用 0.5~1.5s）
/model glm-4-flash

# GLM-4V-Flash（智谱·识图看图，当前唯一稳定的视觉模型）
/model glm-4v-flash

# LongCat-2.0（美团·长文本，12.5 万字上下文）
/model LongCat-2.0

# LongCat-2.5-Preview（美团·深度推理）
/model LongCat-2.5-Preview
```

> ⚠️ 若手动指定的模型所在渠道正好处于冷却中（例如 OpenRouter 每日额度用尽），
> 网关会返回一句人话提示（说明原因与恢复时间），而不是干巴巴的报错。
> 直接改用 `auto` 即可自动绕开。

## 📊 使用统计分析

查看您的使用习惯和性能数据：

```bash
# 查看详细统计
/stats

# 查看模型使用排行榜
/stats models

# 查看场景使用分布
/stats categories

# 导出完整报告
/export-stats
```

## 🔧 高级配置

### 自定义模型池

编辑模型配置文件进行高级定制：

```bash
# 编辑模型配置
/edit-config model-config.json

# 重置为默认配置
/reset-config
```

### 性能监控

实时监控模型性能：

```bash
# 启用性能监控
/monitor enable

# 查看实时性能
/performance

# 生成性能报告
/report-performance
```

## 🛡️ 安全与隐私

- 所有API Key仅存储在本地`%USERPROFILE%\.workbuddy\aist2030-model-manager\`目录
- 不上传任何用户数据到云端
- 支持完全离线使用
- 可随时删除所有本地数据

---

*© 2026 贵州省团之家智付科技有限公司 | AIST2030品牌*