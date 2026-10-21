# AIST2030 付费 Skill 上架发布（`AIST2030-pub-skillpay-v1`）

> AIOPC 变现链路的**上架端**：把一份能跑的 Skill，变成一件能卖的商品（SkillPay）。

## 一句话
覆盖「**定模式 → 备资料 → 过门禁 → 通支付 → 做经营**」五段，输出可直接填进平台上架表单的成品文案。

## 它能做什么
1. **定计费模式**：一次性买断 / 订阅制 / 免费对比表 + 推荐 + 建议价位 + 理由；
2. **备上架资料**：Slug、显示名、图标、版本号、变更说明、一句话简介、3 个效果案例、补充材料清单；
3. **跑发布门禁**：文件结构 / ≤10MB / ≤200 文件 / frontmatter 6 字段 / 企业认证 / 商户入驻 / 「即刻收」签约，问题定位到具体文件；
4. **安排支付兜底**：Agent 支付主链路 + 网页支付兜底（v0.8）、钱包绑定与扫码自动确认（v0.7）、云端保护口径；
5. **排上架后经营**：多版本管理、开发者货架与个人主页、评价与订单数据、平台日志复核。

## 包结构
```text
AIST2030-pub-skillpay-v1/
├── SKILL.md                       # 根指令体（RCTFC）
├── README.md                      # 本文件
├── references/
│   ├── skillpay-changelog.md      # SkillPay v0.1–v0.8 能力演进快照 + 能力矩阵
│   └── publish-checklist.md       # 发布前门禁清单（A–G 七组，可勾选）+ 常见卡点速查
└── assets/
    └── case-template.md           # 3 个效果案例（核心/行业/边界）+ 空白模板
```

## 元信息
| 字段 | 值 |
|---|---|
| id | `AIST2030-pub-skillpay-v1` |
| module | 发布类 |
| version | v1.0 |
| owner | AIST2030 |
| pricing | per_call，0.20 元/次（20 分） |
| tags | skillpay, pay, publish, pricing, subscription, 付费, 上架, 变现 |

## 权威口径
- 官方更新日志：<https://skillpay.alipay.com/changelog>
- 本技能内置快照截至 **v0.8（2026-09-29，网页支付 + 买断权益升级）**；上架前请回官方页面复核最新版本。

## 速查
- 平台能力演进：`references/skillpay-changelog.md`
- 发布前门禁：`references/publish-checklist.md`
- 案例模板：`assets/case-template.md`
- 上游字段与命名标准：`AIST2030-gov-skill-standard-v1`
- 他人 skill 验收：`AIST2030-gov-skill-review-v1`

## 边界
不代替用户提交上架、签约或付款；平台费率、分成、审核时长等官方未载明的信息一律标注「待核实」。
