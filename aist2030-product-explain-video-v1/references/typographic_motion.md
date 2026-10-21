# 文字动效库 v2（关键字 / 金句动效展示，替代字幕）

> 设计原则（源自 adu-motion-video 的编舞经验，务必遵守）：
> 1. **不烧字幕**：用户明确——不要逐句字幕。把「关键字、金句、数据、行动词」做成**动效展示**，随口播节拍点出现又退场。
> 2. **错峰与主次**：大标题先落，关键字随后弹出；主卖点卡抬升，邻卡压后；镜头跟随被强调的卖点。不要让所有字同时动。
> 3. **连续形变**：同一块字从「小→大→定格→缩走」，观众看得出它去了哪里；不要每 2 秒换一张不动的卡。
> 4. **文字与容器错时**：旧字先退场，再变尺寸，最后新字进入；避免两个标签在终点堆叠。
> 5. **真实落点**：动效出现/消失的时刻对齐 `口播时间轴.json` 的关键词时刻，不是随便飘。

## 1. 原子动效表（adu lib.js 风格的可复刻原语）

每个原语给出：语义、CSS/JS 配方、建议时长、推荐音效（adu 68 音效表里的可调用项）。

| # | 原语 | 语义 | 配方要点 | 时长 | 音效 |
|---|---|---|---|---|---|
| 1 | `up` 上滑入 | 字从下方升入 | `translateY(40px→0)` + `o(0→1)` | 0.35s | `slide` / `swipe` |
| 2 | `down` 下滑入 | 从上方落 | `translateY(-40px→0)` | 0.35s | `slide` |
| 3 | `left`/`right` 侧入 | 左/右飞入 | `translateX(±60px→0)` | 0.35s | `swipe` |
| 4 | `pop` 弹入 | 缩放弹出 | `scale(.6→1)` + `EZ.back` 回弹 | 0.4s | `pop` / `bubble_pop` |
| 5 | `zoom` 放大定格 | 由小放大并停留 | `scale(.3→1.0)` + `EZ.out` | 0.5s | `rise` |
| 6 | `slam` 砸字 | 金句重击落定 | `scale(1.4→1.0)` + `o` + 落地微震 | 0.45s | `hit` + `crash` |
| 7 | `blur` 凝焦 | 模糊→清晰（聚焦细节） | `filter:blur(12px→0)` | 0.4s | `shine` |
| 8 | `mask` 擦出 | 遮罩揭开（左→右/下→上） | `clip-path` 动画 | 0.5s | `wipe` / `whoosh` |
| 9 | `words` 逐词现 | 关键词一个一个蹦出 | 每词 `stagger 60–90ms` + `pop` | 按词数 | `typing` / `type` |
| 10 | `counter` 数字滚动 | 数据从 0 滚到目标 | `requestAnimationFrame` 缓动 + `fmt` 千分位 | 0.8–1.2s | `counter`(d) |
| 11 | `cam-shake` 镜头震 | 强调瞬间全屏微震 | 容器 `translate(±4px)` 衰减 | 0.2s | `hit` |
| 12 | `spring` 果冻 | 弹性回弹（活泼卖点） | `EZ.spring` 过冲 | 0.5s | `boing` |
| 13 | `typewriter` 打字 | 逐字打出（科技感） | 宽度/字符裁切 | 按字数 | `typing`(d) |
| 14 | `stroke-grow` 描边生长 | 描边沿路径画出 | `stroke-dashoffset` 动画 | 0.7s | `write` |
| 15 | `glitch` 故障 | 数据/科技强调 | RGB 分离 + 抖动几帧 | 0.25s | `glitch` |
| 16 | `particle` 粒子聚合 | 字由粒子汇聚成形 | 粒子动到目标位置淡出、字淡入 | 0.9s | `sparkle` |
| 17 | `highlight-pulse` 高亮脉冲 | 关键词亮一下 | 背景色脉冲 1–2 次 | 0.6s | `shine` / `chime` |
| 18 | `quote-stamp` 金句盖章 | 引语 + 落章 | `slam` + 角标印章 `pop` | 0.6s | `stamp` + `ding` |
| 19 | `keyword-flyin` 关键词飞入 | 词组划过屏幕定格 | `right` 入 + 轻微 `cam` 跟随 | 0.5s | `whoosh` |

缓动函数复用 adu：`EZ.out / out5 / expo / inout / in / back / spring`（spring 带苹果风回弹）。

## 2. 组合预设（直接套用，对齐分镜）

### 预设 A · 钩子关键词（开场 0–3s）
- 大字标题 `zoom` 定格 → 副标题 `up` 错峰 0.15s 后入 → 一行小字 `words` 逐词。
- 例如：「你家收款码，还能赚钱吗？」→ 标题 `slam`，问句 `highlight-pulse`。

### 预设 B · 卖点卡（中段，每个卖点 3–5s）
- 卖点词 `pop` 弹入 → 解释行 `up` 入 → 配 `counter`（若有数据）→ 退场 `down`+`o` 退。
- 错峰：上一张开始退，下一张才入，避免同屏堆叠（原则 4）。

### 预设 C · 数据滚动（强信任点）
- 大数字 `counter` 0→目标值（如「分润 +37%」）→ 单位 `words` 现 → `highlight-pulse` 收。
- 配 `counter`(d) 音效，节奏感强。

### 预设 D · 金句砸字（转折/高潮）
- 金句整句 `slam` 砸下 + `cam-shake` 微震 + `quote-stamp` 落章。
- 例：「收款不是终点，是起点。」→ `slam` + `stamp`。

### 预设 E · CTA 行动号召（结尾）
- 行动词 `keyword-flyin` 划过 → 主按钮/二维码区 `pop` → 品牌角标 `spring` 弹入。
- 例：「评论区打个『三代』」→ `keyword-flyin` + `pop`。

## 3. 自包含渲染配方（Chrome headless → 帧序列 → ffmpeg）

adu 走的是「HTML/CSS/JS 实时动画 → Chrome 逐帧截图 → 合成」。
我们复刻同一思路，做一个 `text_motion.html` 模板，由 JS 在时间 `t` 推进所有文字状态（即 `renderAt(t)` 模式），
再用 Chrome headless 按 fps 抽帧，ffmpeg 拼成带透明背景的动效层 mp4，最后在合成阶段叠加到 AI 运镜片段上。

### 3.1 模板骨架（参考，可直接用）

```html
<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<style>
  html,body{margin:0;width:1920px;height:1080px;overflow:hidden;background:transparent;
           font-family:"Microsoft YaHei","PingFang SC",sans-serif;}
  #stage{position:absolute;inset:0}
  .kw{position:absolute;opacity:0;will-change:transform,opacity,filter}
  .gold{color:#FFD24D}.white{color:#fff}.shadow{text-shadow:0 4px 18px rgba(0,0,0,.55)}
</style></head><body><div id="stage"></div>
<script>
// ---- 极简缓动 ----
const EZ={out:x=>1-Math.pow(1-x,3),back:x=>{const c=1.7;return 1+ (c+1)*Math.pow(x-1,3)+c*Math.pow(x-1,2)},spring:x=>{const c=1.7;return Math.pow(2,-10*x)*Math.sin((x*10-0.75)*2.094)+1}};
const pr=(t,a,b)=>Math.max(0,Math.min(1,(t-a)/(b-a)));
// 一个关键字元素：在[t0,t1]做某种入场，[t0o,t1o]退场
function KW(o){const e=document.createElement('div');e.className='kw '+(o.cls||'');
  e.style.left=o.x+'px';e.style.top=o.y+'px';e.style.fontSize=o.fs+'px';
  e.style.fontWeight=o.fw||900;e.innerHTML=o.html;document.getElementById('stage').appendChild(e);o.el=e;}
function step(t){for(const o of KWS){const e=o.el;let s=0,o2=1,sc=1,bl=0;
  if(t<o.t0){s=0;o2=0;} else if(t<o.t1){const p=pr(t,o.t0,o.t1);const k=o.k||'up';
    if(k==='up'){s=1-EZ.out(p);} if(k==='pop'){sc=0.6+0.4*EZ.back(p);o2=EZ.out(p);}
    if(k==='slam'){sc=1.4-0.4*EZ.out(p);o2=EZ.out(p);}
    if(k==='zoom'){sc=0.3+0.7*EZ.out(p);o2=EZ.out(p);}
    if(k==='blur'){bl=12*(1-EZ.out(p));o2=EZ.out(p);} }
  if(o.t0o&&t>=o.t0o){const p=pr(t,o.t0o,o.t1o||o.t0o+0.4);o2=1-p;if(o.ko==='down')s=p;}
  e.style.opacity=o2;e.style.transform=`translateY(${s*40}px) scale(${sc})`;
  e.style.filter=bl?`blur(${bl}px)`:'none';}}
window.KWS=[ /* 由生成脚本注入 */ ];
window.renderAt=t=>{for(const o of KWS)if(!o.el)KW(o);step(t);};
window.END=8;
const q=new URLSearchParams(location.search);const t=Number(q.get('t')||0);
document.fonts.ready.then(()=>renderAt(t));
</script></body></html>
```

### 3.2 生成与抽帧（Python 端）

1. 读 `口播时间轴.json`，把每段口播里的「关键字/金句」抽出来，按 `[t0,t1]` 时刻生成 `KWS` 数组，注入模板。
2. Chrome headless 抽帧：`--window-size=1920,1080 --screenshot` 配 `?t=K/FPS`，逐帧截到 `frames/%05d.png`（透明度保留：`--default-background-color=00000000`）。
3. ffmpeg 把 `frames/*.png` 拼成 `text_layer.mov`（**必须用 qtrle(RGBA) 承载 alpha**；本机 libvpx-vp9 解码器不暴露 VP9-alpha 轨道，vp9+alpha webm 在 overlay 时透明区会变黑盖住底图），供合成阶段 `overlay` 叠加到 AI 运镜底片上。
4. 文字层与底片时间轴严格一致（同一 `END` 与 fps）。

> 这样「关键字/金句」是**带透明通道的动效层**，可叠在转盘/细节/人物手托任意 AI 运镜片段上，
> 比烧死字幕高级，且随时可改文案重渲文字层而不动底片。

## 4. 与口播时间轴对齐（关键）

`口播时间轴.json` 由阶段 3 TTS 生成，含每段 `[start,end,text]`。
文字动效层**只取其中的关键字/金句**做动效，不在整段铺满字幕。抽取规则：
- 每段口播挑 1–3 个核心词（名词/动词/数字/结论词），其余口播只靠配音，不显示文字；
- 金句（转折句、结论句、CTA）整句 `slam`/`quote-stamp`；
- 数据句用 `counter`；
- 出现时刻 = 该词在口播里的位置（用标点/语义切分估算，误差 ±0.2s 可接受）。

## 5. 配色与品牌对齐

- 文字主色取自 [product_recognition.md](product_recognition.md) 的 `brand_color`；强调色用金 `#FFD24D` / 品牌蓝。
- 背景透明，叠加在 AI 运镜片段上时，给文字加 `shadow` 类保证任意底图可读（原则：元素降暗后仍占视觉位置，不把新内容叠在降暗旧字上）。
