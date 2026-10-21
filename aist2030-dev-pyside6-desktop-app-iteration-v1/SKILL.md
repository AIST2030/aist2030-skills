---
id: aist2030-dev-pyside6-desktop-app-iteration-v1
name: AIST2030 PySide6桌面应用迭代
displayName: AIST2030 PySide6桌面应用迭代
slug: aist2030-dev-pyside6-desktop-app-iteration-v1
module: 开发类
version: 1.0.0
owner: AIST2030
source: 自建
author: 贵州省团之家智付科技有限公司
role: pyside6-desktop-app-iteration 执行助手，擅长在 开发类 场景下按标准流程完成任务交付。
context: 用户输入与素材，经本技能流程处理后产出目标结果；已知约束见 constraint 与边界说明。
task: 将用户关于「pyside6-desktop-app-iteration」的需求转化为标准化交付物，遵循 quality_gate 与 constraint。
format: 结构化结果 + 必要的过程说明，可直接被下游技能或用户消费。
constraint: 仅处理本技能职责范围内的任务；涉及外部密钥/支付/合规时须显式向用户确认；不越权调用其他系统。
quality_gate: 交付前自检：必填字段完整、产出可用、边界清晰、无越权行为。
anti_dup: 与同类 开发类 技能互斥，按语义匹配唯一触发，避免重复执行。
input_schema: 用户需求描述 / 必要素材（链接、文件、参数）。
output_schema: 标准化交付物 + 状态回显（成功 / 失败原因）。
capability: 提供「pyside6-desktop-app-iteration」能力：适用场景：用户反馈 GUI 主题/菜单/功能入口/授权一致性等问题，需要修改源码、重新打包、交付
  docs。，按既定流程交付结果，适用 开发类 场景。
description: 输入：适用场景：用户反馈 GUI 主题/菜单/功能入口/授权一致性等问题，需要修改源码、重新打包、交付 docs。 相关需求或素材。 输出：按本技能流程产出的结果与可交付物。
  适用边界：仅当用户明确需要「pyside6-desktop-app-iteration」能力、且属于 开发类 场景时调用；不属于本技能职责的需求应交由其他技能处理。
tags:
- pyside6
- desktop
- qss
- iteration
pricing:
  model: per_call
  amount_fen: 1
---

# PySide6 桌面应用迭代工作流

适用场景：用户反馈 GUI 主题/菜单/功能入口/授权一致性等问题，需要修改源码、重新打包、交付 docs。

## 1. 定位项目与关键文件
- 优先在项目根目录 `F:/Work_Buddy/local-pdf-toolbox` 下工作。
- 主窗口：`gui/main_window.py`。
- 主题 QSS：`gui/v2/theme.py`。
- 首页矩阵：`gui/v2/home.py`。
- 功能页：`gui/modules/basic_tools.py`、`gui/modules/analysis.py`、`gui/modules/batch.py`。
- 授权逻辑：`core/licensing.py`；作者工具：`tools/gen_key.py`。
- 打包配置：`build_exe.spec`。

## 2. 主题/QSS 调试
- 使用 `QApplication.setStyle("Fusion")` 保证跨平台一致。
- 调试时设置 `QT_QPA_PLATFORM=offscreen`，实例化 `MainWindow`，用 `win.grab().save(path)` 截图。
- 常见坑：
  - `QGroupBox`、`QScrollArea` 默认背景会覆盖主窗口渐变，需显式 `background: transparent`。
  - `QComboBox` 下拉列表样式必须写 `QComboBox QAbstractItemView`。
  - 卡片/容器背景避免使用带 alpha 的 rgba（在不同 Windows 主题下可能渲染异常），改用实色背景。
  - **`setStyleSheet` 不要写成不带选择器的裸字符串**：会波及全部子控件，把主题里
    `QPushButton` 的渐变背景、`QGroupBox` 描边一起清掉。要用 ID 选择器：
    `w.setObjectName("scrollViewport"); w.setStyleSheet("#scrollViewport{background:transparent;}")`。
  - **QSS「属性选择器」跨对话框会串**（2026-09-21 实测）：用
    `setProperty("changed","1")` + `style().unpolish(); style().polish()` 配合
    `QComboBox[changed="1"]{...}` 高亮控件时，**在同一个进程里再新建一个同类对话框**，
    新控件的属性明明已是 `"0"`，界面上却仍沿用上一个对话框的渲染缓存（显示旧高亮）。
    结论：**别用属性选择器做动态高亮**。改成不依赖样式的方案（如在表格里用 `●` 文字标记、
    或直接换图标），或者把控件 `deleteLater()` 后重建。
  - **动态高亮想用行内样式时**：`setStyleSheet` 只写要改的属性（如 `border`）会与 app 级
    QSS 级联，但**浅色/深色两套主题不会自动跟随**——要么两套配色都显式写，要么走上面的文字/图标方案。

  - **表格单元格内嵌控件要锁死形状**（2026-09-21 实测）：用 `QTableWidget.setCellWidget()`
    放横排单选/按钮时，若控件用默认尺寸策略（Preferred），**首次布局发生在列宽还是默认值时**，
    控件会被压成「截断文字」的宽度；之后列宽变大，多出来的空间被末尾的 `addStretch(1)`
    吃掉，控件**不会自己长回来** —— 症状是「行末那个选项右边永远缺一截」，就算列宽已经
    宽出一倍也一样。解法：
    `rb.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)`
    + `rb.setMinimumWidth(rb.sizeHint().width() + 余量)`。
  - **QSS 的 `padding` 不计入 `sizeHint()`**（Qt 已知行为）：给 `QRadioButton` 写了
    `padding: 2px 9px`，`sizeHint().width()` 仍是不含 padding 的值。若选中态背景胶囊
    要占这 18px，按 `sizeHint()` 定宽就会**把文字切掉一个字**。手动补：
    `setMinimumWidth(sizeHint().width() + 左右padding之和 + 4)`。
  - **`QRadioButton::indicator` 别用粗 border 画实心点**：13px 的圆写 `border: 4px solid`
    会被 Qt 渲染成**方块**。要实心选中点就 `border: 1px solid <色>; background: <色>;`
    （未选中态用 `border-radius` 是圆的，已证实）。
  - **深色主题下原生 radio indicator 的选中态常常看不出来**（选中/未选中都是空心圈），
    必须自绘 indicator + 给 `:checked` 加背景胶囊与文字高亮，否则用户分不清选了哪个。
  - **验证这类「差几个像素」的视觉问题，缩略图不可信**：用
    `PIL.Image.crop(...).resize(2x, LANCZOS)` 把出问题的区域裁剪放大再判断，
    否则会把「字体渲染」误判成「真的被裁」或反之。

## 3. 菜单扁平化
- 用 `QMenuBar.addAction(QAction(label, self, triggered=slot))` 把原本二级菜单项提升到一级。
- 新增功能入口对话框时，放在 `gui/dialogs/` 并在 `build_exe.spec` hiddenimports 中注册。

## 4. 专业版锁定一致性
- 首页矩阵拦截：`MainWindow.on_feature_selected()` 中检查 `key in PREMIUM_FEATURES and not is_premium(key)`，弹升级提示并拦截跳转。
- 功能页内部锁定：在 `BasicToolsPage`、`AnalysisPage`、`BatchPage` 中实现 `refresh_lock_state()`，对按钮/子 tab 调用 `setEnabled(False)` / `setTabEnabled(index, False)`。
- 激活成功后，主窗口调用各页面 `refresh_lock_state()` 同步状态。

## 5. 功能补回（PDF→图片）
- 优先使用 `pypdfium2` 做纯本地 PDF 栅格化，避免依赖 Poppler。
- 在 `core/cli.py` 注册命令；在 `gui/modules/basic_tools.py` 增加子 tab；在 `gui/v2/home.py` CATEGORIES 增加卡片。
- `build_exe.spec` hiddenimports 增加 `pypdfium2`、`pypdfium2.raw`、`pypdfium2.internal`。

## 6. 生成本地文档包
- 使用 `python-docx` 生成 `.docx`。
- 四类标准文档：使用教程、软件介绍、免费/专业版对比表（含价格）、授权操作指南。
- 文档中嵌入 `resources/qrcode_aist2030.jpg` 公众号二维码。
- 示例价格可设为：免费版 0 元，专业版 ¥68/设备（一次性永久授权）或 ¥128/3 设备，实际销售时由运营调整。

## 7. 授权文件与文档整理
- `tools/gen_key.py` 应改为自包含，不依赖项目源码，方便单独放入文档包运行。
- 把 `gen_key.py`、示例 `license.dat`、二维码、四份 docx、README 文件说明放到同一文件夹。
- 在 `build_exe.spec` 的 datas 中把该文件夹映射为 `docs`。

## 8. 打包与验证
- 构建命令：`venv2/Scripts/pyinstaller build_exe.spec`（venv2 同时包含 GUI 与核心依赖）。
- 构建后默认输出在 `dist/LocalPDFToolbox`，按版本重命名为 `dist14/LocalPDFToolbox` 等。
- 冒烟验证：
  - 冻结 EXE 执行 `--core-cli rasterize` 或 `--core-cli detect-office` 成功。
  - 检查根目录无残留的 `license.dat` / `theme_config.json`。
  - offscreen 截图检查暗/亮主题可读性。
- 交付前删除上一版备份目录，避免占用空间。

## 9. ★离屏截图验收的四个必踩坑（2026-09-29 实测，AI讲师讲课件项目）

### 9.1 offscreen 平台字体库是空的 → 中文全变「口口口」
`QT_QPA_PLATFORM=offscreen` 下 `QFontDatabase.families()` 返回 **0 个字体族**，
QSS 里的 `font-family:"Microsoft YaHei"` 匹配不到任何东西 → 所有 Qt 控件文字渲染成豆腐块。
**这不是应用 bug，是截图脚本的假象**，但不修就没法验收。
解法：在 `QApplication` 创建**之后**手动注册系统字体：
```python
from PySide6.QtGui import QFontDatabase
for p in (r"C:\Windows\Fonts\msyh.ttc", r"C:\Windows\Fonts\msyhbd.ttc",
          r"C:\Windows\Fonts\simhei.ttf"):
    if os.path.exists(p):
        fid = QFontDatabase.addApplicationFont(p)
        if fid >= 0: got += QFontDatabase.applicationFontFamilies(fid)
```
（画布里由 PIL 画上去的文字不受影响 —— **"画布中文正常、控件全是方框"就是本坑的指纹**。）

### 9.2 「豆腐块」怎么判定：`inFont()` 不可靠，要用位图比对
`QFontMetrics.inFont(ch)` 对缺失字形也返回 `True`，别信它。
实测法：把一个**私用区字符**（如 `\uE123`，必定无字形）当「豆腐块基准」，
用 `QPainter` 把候选字符画到 `QImage` 上，取墨迹像素集合与基准比对 —— 像素完全相同即缺字形。
实测结论（Microsoft YaHei）：
- **缺字形（会变豆腐块）**：`◀ ▶ ⏺ ⏹ ✔ ✓`
- **安全可用**：`● ■ ← → ① ② · • … — ×`

安全清单里没把握的字符，一律改用 `「」` 引号包住**控件真实文案**（如 `点「开始录制」按钮`），
比塞一个装饰性小图标更清楚、且零风险。

### 9.3 `QGraphicsItem` 子类的属性名不能撞内置方法
自定义 `QGraphicsItem` / `QGraphicsRectItem` 子类里写 `self.x`、`self.y`、`self.w`、`self.h`、
`self.pos`、`self.shape`、`self.rect` 会**静默遮蔽** Qt 的同名方法（`itemChange` 里读 `self.x()`、
父类布局调用 `pos()` 全部读到你的数字）。症状是「拖拽/钳制/命中检测莫名其妙不对」，不报错。
解法：换前缀，如 `gx/gy/gw/gh/shape_kind`。

### 9.4 画布预览必须与渲染端「同算法」抄数字
WYSIWYG 画布不要自己发明几何：直接把 PIL 渲染端的常量抄过来。
例：`render_core.draw_subtitle` 用 `pad=18 / 行高=字号+12 / 最大宽=0.8*BASE_W / 圆角胶囊
/ bottom 贴底 24px`，画布就按同一套公式算矩形，并让字体 `setPixelSize(40)` 对齐 PIL 的 `pick_font(40)`。
否则「预览好看、成片跑偏」，而且是**肉眼不易察觉的偏移**。
验证时**别靠肉眼看整窗截图**——用 numpy 找舞台/胶囊包围盒反算映射，
或直接把 `QGraphicsScene.render()` 到 1920×1080 与 PIL 成片逐像素对。

### 9.5 `QLineEdit` 显示长路径会吃掉盘符
`setText()` 后光标默认停在**末尾**，长路径从左边被裁 → 用户看到 `...\输出\xx.mp4`，
以为路径填错了。统一封装：
```python
def set_path_text(le, text):
    le.setText(str(text)); le.setCursorPosition(0); le.setToolTip(str(text))
```
所有路径框（含构造时的默认值）都走它。

### 9.6 冻结包的 GUI 冒烟：`timeout N exe` 看退出码
只跑 `--selftest` 不够（曾出现「编译/自检都过、GUI 一启动就崩」）。
用 `timeout 8 dist/App/App.exe`：**退出码 124 = 存活到超时 = 启动正常**；
其他退出码或秒退说明冻结后缺模块/资源。同时确认随包资源到位（如
`_internal/resources/qrcode_aist2030.jpg`），spec 里用 `(_p, "resources")` 显式映射。

---

## 10. ★冻结包交付前的「可移植性 + 实证」四件套（2026-09-29 实测，数字人口播工作台）

onedir 包要能**拷到别的电脑直接跑**，光打包成功不够。四条必做：

### 10.1 禁止硬编码项目盘符，数据目录按「运行位置」解析
开发期常见写法 `Path(r"F:/Work_Buddy/xxx")` 一冻结就成定时炸弹（换机=写不进去）。
统一走一个解析器，**每级都做可写性探测**：
```python
def _writable(p: Path) -> bool:
    try:
        p.mkdir(parents=True, exist_ok=True)
        (p / ".write_probe").write_text("ok"); (p / ".write_probe").unlink()
        return True
    except Exception:
        return False

def workspace_root() -> Path:
    env = os.environ.get("APP_DATA_DIR")          # 1. 环境变量优先（给高级用户）
    if env and _writable(Path(env)): return Path(env)
    if getattr(sys, "frozen", False):             # 2. 冻结态：EXE 同级「数据」
        cand = Path(sys.executable).resolve().parent / "数据"
        if _writable(cand): return cand
    if _writable(_DEV_WORKSPACE): return _DEV_WORKSPACE   # 3. 开发态工程目录
    fb = Path.home() / "AppName" / "数据"; fb.mkdir(parents=True, exist_ok=True)
    return fb                                     # 4. 兜底
```
> 冻结态用 `sys.executable`（= exe 真身），**不要用 `sys.argv[0]`**，也不要用
> `app_root()/../..` 猜层级。

### 10.2 外部工具（CLI exe）定位要「多候选回退」
随包的外部 CLI（本例 `yovoice.exe`）在开发态和冻结态位置不同：
冻结态在 `_MEIPASS/tools/...`，开发态在 `工程/tools/...`。写成候选列表逐个
`exists()` 命中，**最后一个候选兜底返回**（不要抛异常，抛出后 UI 里全是崩溃日志）：
```python
cands = [app_root()/"tools"/"x"/"x.exe",
         Path(__file__).resolve().parent.parent/"tools"/"x"/"x.exe",
         Path(r"F:/.../tools/x/x.exe")]
for c in cands:
    if c.exists(): return c
return cands[0]
```

### 10.3 外部数据目录必须 ASCII，且允许环境变量覆盖
第三方引擎（如音频服务）对中文路径支持差（实测报 `could not open WAV input`）。
解析顺序：`环境变量 → 已预下载目录 → %LOCALAPPDATA%/<ascii-name>`，
**别把 2GB 模型塞进包**（包会从 390MB 涨到 2.4GB），改成「就绪检测 + 一键下载」。

### 10.4 UI 里必须能看到「依赖就绪状态」，不能静默失败
打包后最容易翻车的是「模型/引擎没准备好 → 用户点了才发现报错」。
做法：启动时探测 + 界面上一个状态文案 + 一个「准备引擎」按钮（走 QThread，
下载期间不能卡 UI）；顶部状态文案里**别用 `✓ ✔ ⏺`**（雅黑缺字形，见 §9.2）。

### 10.5 `--selftest` 的输出必须落文件，路径也要可移植
`console=False` 的 windowed exe 在 bash 里**抓不到 stdout**。
自检里 `logging.basicConfig(filename=...)` 写日志，路径同样走 `workspace_root()/临时/`。
冻结态自检至少覆盖：模块导入 → 外部 CLI 存在性 → 数据目录 → **一次真实渲染出图**（证明 PIL/字体/ffmpeg 链路没断）。

## 11. ★沙箱里 QProcess 起不了子进程 → 用「拦截」验证 GUI 编排逻辑（2026-09-29 实测）

**现象**：`QProcess.start(prog, argv)` 一律 `FailedToStart`（`errorString()` 是管道错误），
连 `QProcess.start(sys.executable, ["-c", "print('hi')"])` 都起不来。
先做最小对照实验排除自己的参数问题，确认是**执行环境限制、不是产品缺陷**：

```python
for name, use_env, use_wd in [("有env+有wd",True,True), ("无env+有wd",False,True), ("无env+无wd",False,False)]:
    p = QProcess()
    if use_env: p.setProcessEnvironment(QProcessEnvironment.systemEnvironment())
    if use_wd:  p.setWorkingDirectory(os.getcwd())
    p.start(sys.executable, ["-c", "print('hi')"])
    print(name, p.waitForStarted(8000), p.errorString())   # 三个都 False → 环境限制
```

**结论**：这种环境下 GUI 的**真实出片**无法在会话内验证。验证策略改为两层：

1. **逻辑层（在会话内做）**：monkeypatch 掉子进程入口，只验编排逻辑
   （输出路径、参数拼装、状态机、批量分支）——这些恰恰是最容易写错的：
   ```python
   import gui.main_window as mw
   mw.run_sync = lambda args, timeout_ms=20000: {"ok": True, "slides": 3, "ratio_label": "16:9",
                                                  "need_notes": False, "heteronym_candidates": []}
   w = mw.MainWindow()
   w.runner.start = lambda: None              # 不真跑
   captured = {}
   w.runner.enqueue = lambda jobs: captured.update(jobs=jobs)
   w._append_files([r"C:\tmp\A.pptx"]); w._start()
   for j in captured["jobs"]:                 # 断言 out_path 落在期望目录
       print(j.input_path, "->", j.out_path)
   ```
   ⚠️ 被 monkeypatch 掉的 probe 要**返回足够完整的假数据**，否则后面分支会 KeyError，
   看起来像"代码坏了"，实际是假数据不全。
2. **冷冻层（必须做，且是唯一实证）**：用冻结态 exe 走 `--core-cli` 端到端
   （注意 `cwd` 必须是 `exe.parent`，输入用相对路径），再对产物做**量化断言**
   （音量/音调/尺寸/亮度），而不是只看 exit code 0。
   纯 GUI 存活用 `timeout 8 exe.exe` → **退出码 124 = 存活到超时 = 启动正常**。

