# 现有桌宠项目调研与借鉴清单

本文回答一个问题：**别人的桌宠都做了什么，Betty Pet 该抄哪些、按什么顺序抄。**

调研方式：公开检索各项目的官方仓库、README、wiki 与第三方规格文档（结果汇总于文末链接），
没有逐行阅读源码，因此涉及内部实现细节的说法只在有明确依据时才写。文中标注了「已落地」
的项目，指本文档同一次改动里已经实现的部分。

---

## 1. 结论先行

横向扫一遍会发现，桌宠这个品类早就收敛出了一套事实标准。**运动能力（重力、拖拽、投掷、
追鼠标）不是加分项，是入场券**——Shimeji-ee 的配置校验直接要求 `ChaseMouse`、`Fall`、
`Dragged`、`Thrown` 这四个行为必须存在，缺一个配置文件就不合法。

在本次改动之前，Betty Pet 的架构质量（Scheduler 优先级、SQLite 存档、可测的 domain 层）
其实高于绝大多数同类 Python 项目，但**它站不住、掉不下来、扔不出去、不追鼠标**——也就是说
入场券没拿。所以第一优先级不是道具系统、不是大模型，而是把运动系统补齐。

据此确定的批次：

| 批次 | 内容 | 状态 |
| --- | --- | --- |
| 一 | 物理运动（重力 / 拖拽 / 投掷 / 反弹）+ 追鼠标 + 悬停反应 | **已落地** |
| 二 | 道具表、拒绝规则（吃饱 / 每日上限 / 冷却）、好感度成长 | **已落地** |
| 三 | 窗口栖息、系统托盘、开机自启命令 | **已落地** |
| 三 | 音效（只有抽象层与静音实现，无后端、无素材） | **骨架** |
| 三 | 沿墙与天花板攀爬、多实例、番茄钟 / 提醒 | 待做 |
| 四 | 系统监控联动、全局输入监听、本地模型对话 | 待评估 |

---

## 2. 项目清单

### 2.1 2D 桌面吉祥物（最接近 Betty Pet 的一类）

| 项目 | 技术栈 | 许可 | 关键特征 |
| --- | --- | --- | --- |
| **Shimeji-ee** | Java / Windows | New BSD | 品类鼻祖的分支。`actions.xml` 定义「能做什么」，`behaviors.xml` 定义「何时做、做多频繁」；多套图像集（`img/<名字>/`）即多角色；托盘图标左键繁殖一只、右键退出；预置三档行为频率（恶作剧 / 安静 / 专业） |
| **Shijima-Qt** | C++ / Qt，跨平台 | GPL-3.0 | Shimeji 的现代重写，能直接加载经典图像集，不需要 Java |
| **eSheep / desktopPet** | C# / .NET / Windows | 开源 | XML + PNG 自定义宠物，配 `PetEditor` 编辑器，原生多宠物 |
| **vscode-pets** | TypeScript / VS Code Webview | MIT | 宠物类型 × 颜色 × 尺寸；光标响应；扔球让宠物去捡；主题（森林/城堡/沙滩/冬季）；导出导入宠物列表 |

**Shimeji 的架构最值得学**：`actions.xml` 与 `behaviors.xml` 的分离，和 Betty Pet 已有的
`manifest.json`（素材）+ `behavior.py`（阈值规则）几乎是同一个思路。它的「必须实现的四个
行为」本身就是一份需求清单。

### 2.2 虚拟宠物模拟器（重数值养成）

| 项目 | 技术栈 | 许可 | 关键特征 |
| --- | --- | --- | --- |
| **VPet** | C# / WPF / Windows | Apache-2.0 | 饱食度 / 心情 / 体力 / 健康随时间衰减；打工与学习赚虚拟货币，货币买食物饮料道具；约 32 类 × 4 状态 × 3 变体 ≈ 384 个动画；Steam 创意工坊 Mod，可加宠物、道具、对话、主题、插件；默认一个实例一只宠物 |
| **HoneyPet** | Python / PySide6 | 开源 | 14 种人格，不同人格台词不同；亲密度养成到「灵魂伴侣」；`pynput` 全局输入监听；投掷物理；JSON 存档；托盘入口 |

**VPet 的数值模型值得学**：状态衰减 → 行为倾向 → 消耗道具 → 数值回补，构成闭环。
Betty Pet 的 `PetStats` / `StatRecovery` / `default_recoveries()` 已经有了这个闭环的骨架，
缺的只是「道具」这一层实体和货币/成长。

### 2.3 Python 同类实现（技术栈最接近，可直接对照）

| 项目 | 技术栈 | 关键特征 |
| --- | --- | --- |
| **shuyanCoding/DesktopPet** | PyQt | 动作状态机含 idle / walk / sit / fly / drag_throw / drop / wall_idle / wall_climb / wall_descend / ceiling_walk；**掉落、墙面吸附、天花板移动**；右键「立即生成分身」，某些动作结束后自动生成新实例；CPU / 内存 / GPU 占用映射到动作与托盘动画；单例模式防止多开；处理多显示器与任务栏高度，掉到任务栏以下判定坠落并重置到顶部 |
| **jason131415/xiaohei-desktop-pet** | tkinter + Pillow | **与 Betty Pet 技术栈几乎相同**。拖拽 + 快速扔出触发重力下落与落地缓冲；鼠标悬停触发眯眼，持续抚摸加好感度；悬停 0.8 秒触发挥手；玩具系统（激光笔 / 逗猫棒 / 毛线球 / 小老鼠）；喂鱼（每日上限、饱腹后拒绝）；番茄钟专注模式（25 分钟安静陪伴）；**窗口栖息**（跳到前台窗口标题栏）；8 种行为自动切换；物理含重力、终端速度、拖拽释放速度检测、落地反弹；好感度 0–5 级、`stats.json` 持久化；10 个音效 |
| **90shree/desktop-pet-kirby** | Python / tkinter | 10ms 更新循环；物理全部手写：重力逐帧累加、水平速度、摩擦、屏幕边界碰撞、**拖拽释放速度**、逐次衰减的反弹；坐在其他窗口上方 |
| **gitee desktop_pet** | Python / Tkinter / PyQt5 | 拖拽桌面快捷方式到宠物身上「吃掉」；长按 2 秒进入跟随鼠标；环形右键菜单；开机自启；检测 Chrome/Steam 启动并提醒；透明度调节；全局快捷键；定时喝水提醒；长时间无操作触发睡觉动画；内存 > 80% 弹清理建议；摸头加心情；冷却时间；JSON 配置行为规则 |

`xiaohei-desktop-pet` 是本次调研里最有参考价值的对标物——同样的 tkinter + Pillow，做出来的
功能密度高出一个量级。它证明了 Betty Pet 的技术选型不是天花板。

### 2.4 单点玩法型

| 项目 | 关键特征 | 对 Betty Pet 的价值 |
| --- | --- | --- |
| **Desktop Goose** | 抓住你的鼠标、往桌面丢文件、留脚印 | 看一眼就好。搞破坏对日常使用是负收益 |
| **Bongo Cat** | 跟随真实键鼠输入敲鼓，掉帽子装饰，常驻任务栏 | 「响应真实输入」值得借鉴，但需要全局钩子 |
| **Oneko / Neko** | 追着鼠标跑、睡觉、抓屏幕边缘，品类最早的形态 | 追鼠标行为的源头，实现极简，已被本批次吸收 |

---

## 3. 能力矩阵

`●` 已有 ｜ `◐` 部分 ｜ `○` 没有

| 能力 | Betty Pet | Shimeji | VPet | vscode-pets | xiaohei | DesktopPet(PyQt) |
| --- | --- | --- | --- | --- | --- | --- |
| 重力 / 掉落 | ● | ● | ○ | ○ | ● | ● |
| 拖拽 | ● | ● | ● | ● | ● | ● |
| 投掷（释放速度） | ● | ● | ○ | ○ | ● | ● |
| 墙 / 天花板攀爬 | ○ | ● | ● | ○ | ◐ | ● |
| 追鼠标 | ● | ● | ○ | ● | ● | ○ |
| 悬停 / 抚摸反应 | ● | ● | ● | ○ | ● | ○ |
| 多角色 / 皮肤 | ○ | ● | ● | ● | ○ | ○ |
| 多实例 / 分身 | ○ | ● | ○ | ● | ○ | ● |
| 数值衰减 | ● | ○ | ● | ○ | ● | ○ |
| 道具 / 背包 | ○ | ○ | ● | ○ | ● | ○ |
| 成长 / 好感度 | ○ | ○ | ◐ | ○ | ● | ○ |
| 存档持久化 | ● | ◐ | ● | ◐ | ● | ◐ |
| 音效 | ○ | ○ | ● | ○ | ● | ○ |
| 系统托盘 / 开机自启 | ○ | ● | ● | — | ○ | ● |
| 定时提醒 / 番茄钟 | ○ | ○ | ◐ | ○ | ● | ● |
| 行为优先级 / 冷却 | ● | ● | ● | ○ | ◐ | ◐ |
| 窗口栖息 | ○ | ● | ◐ | ○ | ● | ◐ |
| 全局输入响应 | ○ | ○ | ○ | ○ | ○ | ○ |
| 本地模型对话 | ○ | ○ | ◐ | ○ | ○ | ○ |
| 插件 / Mod 生态 | ○ | ● | ● | ◐ | ○ | ○ |

Betty Pet 在「工程严谨度」一列（行为优先级、冷却、可测试性、存档）是对齐甚至领先的；
短板全部集中在**表现与玩法**。

---

## 4. 已落地（本批次）

### 4.1 物理运动引擎 `src/betty_pet/physics.py`

对应 Shimeji 的 `Fall` / `Dragged` / `Thrown` 三个必备行为，参考 Kirby 与 xiaohei 的物理描述：

- 重力逐帧累加、终端速度截断、空气阻力、地面摩擦
- 边界碰撞：落地、撞左右墙、撞顶
- **阻尼反弹**：只有超过 `min_bounce_velocity` 的撞击才回弹，每次回弹按 `bounce` 系数衰减，
  最终必然静止（有测试断言「反弹高度递减且最终 `settled()`」）
- **拖拽释放速度**：`DragTracker` 只取最近 120ms 的轨迹样本估算释放速度，所以慢慢拖是
  「放下」，快速甩才是「扔出去」；速度上限 `max_throw_speed` 防止宠物飞出屏幕
- 全部为纯逻辑、无 Tkinter 依赖，`tests/test_physics.py` 覆盖 17 项

### 4.2 窗口接入

- 起始位置改为**屏幕右下角、站在地面上**（HoneyPet 也是这个行为），不再是 Tk 默认位置
- 拖拽记录轨迹并在松手时投掷；拖拽中播放 `dragged` 语义动作
- 单一步进循环统一驱动所有位移（行走、追鼠标、掉落、投掷），只有宠物真的在动时才运行，
  静止即停，不空转
- 行走改为经物理驱动，走到计划距离或撞墙后播放 `climb`
- 菜单新增「跟随鼠标」（ChaseMouse，带死区防抖，状态持久化到存档）
- 鼠标悬停 0.8 秒触发挥手（对应 xiaohei 的悬停挥手）
- 状态面板增加实时坐标与「地面 / 空中」

### 4.3 顺带修掉的两个真 bug

1. `Scheduler.repeat()` 的自杀式竞态：回调里调用 `cancel` / `cancel_group` 取消自己时，因为
   任务在触发前就已从队列弹出，取消失败，计时器会把已经不该存在的自己重新排上——变成永不
   停止的循环。现在运行中的任务也会被取消操作看到。
2. 落地后 `y` 可能停在地面上方 0.05px 处不再对齐，导致物理循环每一帧都被唤醒却什么也不做。

### 4.4 素材缺口（重要）

物理动词目前**借用了现有素材**，因为 `assets/manifest.json` 里没有对应的 PNG：

| 语义动作 | 当前回退到 | 建议新增 |
| --- | --- | --- |
| `fall` | `idle` | `fall.png`（下落姿态，1 帧即可） |
| `thrown` | `click` | `thrown.png`（被扔飞的瞬间） |
| `dragged` | `climb` | `dragged.png`（被拎起来） |

回退链写在 `assets.py` 的 `ACTION_FALLBACKS`，`AssetCatalog.resolve()` 负责解析。
**把上面三个 PNG 加进 `assets/` 并写进 `manifest.json` 即自动生效，不需要改代码。**
在此之前程序不会因为缺素材而报错或卡住。

---

## 5. 后续批次

### 批次二：把「养成」补上 —— 已落地

参考 VPet 的数值闭环与 xiaohei 的拒绝机制，实现为 `src/betty_pet/items.py`：

1. `Item` 声明式道具表（效果 / 冷却 / 每日上限 / 台词 / 动作），菜单由表自动生成
2. 好感度每 50 点一级，6 档（陌生 → 熟悉 → 朋友 → 好友 → 亲密 → 挚友），只增不减
3. **每日上限与饱腹拒绝**——参考 xiaohei 的「吃不下啦」，这是让宠物"有反应"而不是"有按钮"的关键
4. 存档侧新增 `daily_usage` 表与 `pet_state.affection` 列（带老库迁移）

**刻意没做**：道具数量与货币。VPet 有打工赚钱的循环撑着货币，Broken 的是"钱只能少不能多"的
半成品经济。等有了产出道具的循环（番茄钟、陪伴时长）再补。

音效层留到批次三。

### 批次三：空间与场景

5. **窗口栖息 —— 已落地**（`src/betty_pet/desktop.py` + `window.py`）。
   实现比预想简单得多：`win32gui` 取前台窗口矩形，把窗口上沿折算成一个临时 `Bounds` 喂给
   原本的 `step()`，于是"站上去、沿窗口走、窗口关掉就掉回地面"全是既有的物理行为。
   已定约定：只认前台窗口、按进程号排除自己、拒绝最大化窗口（上沿在屏幕顶端，没地方站）、
   无 pywin32 时降级为不可用。
6. **墙 / 天花板攀爬 —— 待做**。当前物理只有底部地面，Shimeji 的动作表里有大量沿墙、沿天花板
   移动，需要给 `Bounds` 增加「依附面」概念。栖息这一步已经验证了"换 `Bounds`、不动物理"可行。
7. **多实例 —— 待做**。牵涉到「一份状态还是多份状态」「存档如何区分」，建议先做设计再动手。
8. **番茄钟 / 提醒 —— 待做**。不是桌宠的核心，但实用价值高，且能复用现有 `Scheduler`。
9. **音效 —— 骨架已落地**（`src/betty_pet/audio.py`）。`SoundPlayer` 协议 + 静音实现 + 语义键位
   + 菜单/CLI 开关都已就位，但**既没有播放后端、也没有音频素材**，所以现在打开开关听不到声音。
   剩下的两件事里，素材比后端更卡脖子。
10. **系统托盘 + 开机自启 —— 已落地**（`src/betty_pet/tray.py`、`src/betty_pet/autostart.py`）。
    托盘用 pywin32 直接调 `Shell_NotifyIcon` 自绘，**零新依赖**（本机 pywin32 已在）；开机自启写成
    「启动」文件夹里的 `.vbs`，只由 `--install-autostart` 显式触发，默认不写、也不自动开启。

### 批次四：需要单独评估

9. 托盘与开机自启：需要 `pystray` 之类的新依赖，且涉及写注册表/启动项，属于"改用户系统"，
   必须显式确认后才能做
10. 系统监控联动（CPU/内存 → 动作）：`psutil` 依赖，且"电脑一卡宠物就发疯"未必讨喜
11. 全局输入监听：`pynput` 能感知打字与点击，但同时意味着**记录用户输入**，隐私代价明确，
   除非有"键盘陪伴"这类明确需求，否则不做
12. 本地模型对话：`docs/PROJECT_DISTILLATION.md` 已有完整设计（`DialogueProvider` 协议、
    后台线程、意图白名单），仍然是长期方向

### 明确不抄

- **吃掉桌面快捷方式**：gitee 那个项目里「吃掉图标」会真实处理文件，桌宠删用户文件是事故
- **Desktop Goose 式捣乱**：抢鼠标、往桌面丢文件，日常使用场景下是负收益
- **要管理员权限的功能**：能不碰就不碰

---

## 6. 参考链接

- Shimeji-ee 行为与配置规格：<https://zread.ai/gil/shimeji-ee/conf/settings.properties>
- Shimeji-ee 官方 README wiki：<https://code.google.com/archive/p/shimeji-ee/wikis/Readme.wiki>
- Shimeji 动作类型说明：<https://deepwiki.com/zh050707-lab/-shimeji-AI-/4.1-action-types>
- Shijima-Qt（跨平台重写）：<https://github.com/pixelomer/Shijima-Qt>
- VPet：<https://github.com/LorisYounger/VPet>
- eSheep / desktopPet：<https://github.com/Adrianotiger/desktopPet>
- vscode-pets：<https://github.com/tonybaloney/vscode-pets>
- vscode-pets 配置与命令：<https://deepwiki.com/tonybaloney/vscode-pets>
- Kirby 桌宠（物理说明写得很细）：<https://github.com/90shree/desktop-pet-kirby>
- xiaohei-desktop-pet（同技术栈对标）：<https://github.com/jason131415/xiaohei-desktop-pet>
- DesktopPet（PyQt，含分身与系统监控）：<https://patch-diff.githubusercontent.com/shuyanCoding/DesktopPet>
- desktop_pet（Gitee）：<https://gitee.com/suma_3/desktop_pet>
- HoneyPet（人格与亲密度）：<https://juejin.cn/post/7672975601435131955>
