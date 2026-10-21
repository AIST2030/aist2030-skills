# 阶段 0 · 产品图像识别与 3D 理解

> 用户给的图**不是直出素材**，是「待理解的对象」。这一步必须在任何运镜/动效之前完成：
> 用多模态能力读懂产品的三维情况，再决定怎么拍它。

## 1. 为什么要先做识别

直接把产品图拿去做 Ken Burns 推拉，本质是「平面照片假装会动」，观感假、卖点讲不透。
真正高级的产品讲解片，镜头语言建立在「产品是三维物体」这件事上：

- 用户图往往只有 2–3 个角度、白底或场景图，AI 生成模型（转盘/细节/人物手托）需要**明确的 3D 先验**才不乱跑。
- 只有先搞清楚「这是什么形状、多大、什么材质、哪个面是正面、哪个口是接口、logo 在哪」，才能：
  - 决定**转盘旋转**用哪张/哪几张图生成、转出多少度合理；
  - 决定**细节推进**该推到哪个特征（logo / 屏幕 / 接口 / 纹理）；
  - 决定**AI 人物手托**的手该出现在哪一侧、握哪个部位才自然；
  - 把「关键字 / 金句」动效卡精确地钉在对应卖点上。

## 2. 识别产物：`product_3d_profile.json`

多模态识别后产出一份结构化档案，下游所有阶段读它。字段规范：

```jsonc
{
  "identity": {
    "name": "省团 × 拉卡拉 第三代收款码（碰一下云音箱）",
    "category": "支付终端 / 收银硬件",
    "brand": ["省团", "拉卡拉"],
    "brand_color": ["#1A3FA0", "#0E7C5A"]   // 识别出的品牌主色，动效配色对齐
  },
  "form": {
    "shape": "扁平方形机身 + 立式扫码牌 + 喇叭网面",
    "form_factor": "桌上立式小设备",
    "dim_estimate": {"h": 0.18, "w": 0.12, "d": 0.05, "unit": "m"},  // 估算尺寸，仅用于运镜比例
    "aspect": "竖向略高 / 正面近似方形"
  },
  "material": {
    "body": "哑光塑料 + 局部金属网",
    "finish": "哑光",
    "reflective": false,
    "accent": "金色/银色 logo 与边框"
  },
  "color": {
    "base": "深空灰 / 黑",
    "accent": "金 / 银",
    "screen_or_light": "绿色扫码指示光"
  },
  "features": [   // 可成为「细节推进」目标的特征，按重要性排序
    {"id": "logo", "where": "正面中上", "type": "印刷/蚀刻标识", "sell": "品牌背书"},
    {"id": "scan_panel", "where": "正面扫码区", "type": "二维码/扫码窗", "sell": "碰一下/扫码收款"},
    {"id": "speaker_mesh", "where": "机身下部", "type": "喇叭网", "sell": "语音播报"},
    {"id": "port", "where": "侧/底", "type": "电源/接口", "sell": "供电方式"}
  ],
  "angle_coverage": {   // 用户实际给了哪些角度
    "front": true, "side": true, "back": false,
    "top": false, "detail": true, "scene": false,
    "missing_for_turntable": ["back", "top"]  // 转盘缺角度时的兜底策略
  },
  "shot_plan": {   // 由 profile 自动推导的运镜建议（供阶段2采纳）
    "turntable": {"feasible": true, "use_images": ["front","side"], "spin_deg": 90, "note": "缺背/顶，限转90°避免露出空白面"},
    "detail_push": [
      {"feature": "scan_panel", "zoom": 2.4, "from": "front"},
      {"feature": "logo", "zoom": 3.0, "from": "front"}
    ],
    "hand_hold": {"feasible": true, "hand_side": "right", "grip": "托底+扶侧", "caution": "避免遮住扫码面"},
    "scene_shot": {"feasible": false, "reason": "用户未给使用场景图，需补拍或生成"}
  },
  "confidence": {"overall": 0.85, "notes": "材质与尺寸为估算，运镜比例以估算为准"}
}
```

## 3. 识别提示词模板（可复用于任意产品）

把用户多图与产品名/已知信息喂给多模态模型，要求**只输出上面的 JSON**（不要散文）：

```
你是一名产品 3D 理解专家。下面有 N 张同一产品的不同角度照片。
请逐张观察，输出严格的 product_3d_profile JSON：
1) identity：名称/品类/品牌/品牌主色；
2) form：整体形状、形态、估算尺寸(米)、长宽比；
3) material：机身材质、表面处理(哑光/亮面)、是否反光、点缀材质；
4) color：基色/点缀色/屏或指示灯色；
5) features：可成为「细节特写」目标的特征清单（位置+类型+对应卖点），按重要性排序；
6) angle_coverage：用户图覆盖了哪些角度(front/side/back/top/detail/scene)，缺哪些；
7) shot_plan：基于以上，推导 turntable（可行性/用图/转角度数）、
   detail_push（特征→放大倍数→来源图）、hand_hold（可行性/手侧/握法/注意）、
   scene_shot（是否可行/原因）的建议；
8) confidence：整体把握度与不确定项。
只输出 JSON，字段名严格一致，不要解释。
```

> 本 Skill 的编排器（agent）本身具备多模态读图能力，可直接执行此识别，
> 把结果落盘为 `product_3d_profile.json` 作为后续阶段的唯一事实源。

## 4. 识别结果 → 运镜映射（与 camera-prompt 库衔接）

识别出的 `shot_plan` 再交给 `camera-prompt`（50 种运镜 / 14 行业）翻译成**具体镜头语言**：

| 识别结论 | camera-prompt 选用 | 下游 AI 运镜 |
|---|---|---|
| turntable.feasible | `orbit`（环绕）/ `lazy-susan`（转盘） | product-360 (Agnes) |
| detail_push[i] | `push-in`（推进）/ `macro`（微距）/ `rack-focus`（变焦转清晰） | product-video (千帆) / image-awake |
| hand_hold.feasible | `handheld`（手持感）/ `hero-pan`（英雄光摇） | 角色视频模型 / 数字人 |
| scene_shot.feasible=false | 跳过实景，改用「卖点卡 + 产品悬浮」 | 合成兜底 |

这样「图 → 理解 → 镜头词 → AI 出片」形成闭环，而不是凭空编运镜。
