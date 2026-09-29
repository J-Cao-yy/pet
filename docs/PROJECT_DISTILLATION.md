# Betty Pet 项目提炼与扩展路线

## 1. 项目定位

Betty Pet 是一个运行在 Windows 桌面的轻量级 2D 桌宠原型。它的核心价值不是某一组 PNG，而是一个可替换素材、可编排动作、可逐步接入智能能力的桌面交互容器。

当前技术基线：Python 3.10+、Tkinter、Pillow；OpenCV/NumPy 只用于素材预处理。程序以单进程、单 Tk 事件循环运行，适合先验证交互和角色表现，再逐步增加本地服务与持久化能力。

同类开源项目的横向对比（Shimeji-ee / VPet / vscode-pets / 数个 Python 同类实现）以及「该抄什么、
按什么顺序抄」的判断，见 [现有桌宠项目调研](EXTERNAL_REFERENCES.md)。

## 2. 当前能力边界

| 能力 | 现状 | 代码落点 |
| --- | --- | --- |
| 透明置顶桌宠窗口 | 已支持 Windows 透明色、置顶、无边框 | `src/betty_pet/window.py` |
| 拖拽与点击交互 | 左键拖拽；点击触发 click 动作和随机气泡 | `window.py` |
| 动作播放 | 一次性动作与循环动作；固定 180ms 帧间隔 | `src/betty_pet/model.py`、`window.py` |
| 随机行为 | 6~15 秒随机选择非 idle/click 动作 | `window.py`、`src/betty_pet/config.py` |
| 素材管理 | `manifest.json` 声明动作到 PNG 帧的映射，启动时校验缺失文件 | `src/betty_pet/assets.py`、`assets/manifest.json` |
| 缩放 | 0.3~2.5 倍，滚轮或右键菜单调整 | `config.py`、`window.py` |
| 对话展示 | 顶部无边框白色气泡，按时自动隐藏 | `window.py`、`config.py` |
| 命令行 | 资产目录、初始缩放、关闭随机动作、资产检查、存档路径、音效覆盖、专注时长 | `src/betty_pet/__main__.py` |
| 定时调度 | 命名任务、优先级、分组取消、冷却，全部定时器集中管理 | `src/betty_pet/scheduler.py` |
| 存档 | SQLite 存状态 / 设置 / 事件日志，启动补算离线衰减，每分钟自动保存 | `src/betty_pet/store.py`、`config.py` |
| 道具 | 6 件道具分喂食 / 玩耍 / 休息三组，声明式表驱动，菜单自动生成 | `src/betty_pet/items.py`、`window.py` |
| 拒绝规则 | 吃饱拒食、每日上限、冷却未到，三种拒绝各有台词且不消耗次数 | `items.py`、`window.py`、`store.py` |
| 好感度 | 每 50 点一级（陌生→挚友），只增不减，升级播报并记事件 | `state.py`、`window.py` |
| 专注计时 | 番茄钟：坐定安静、倒计时、坐满给好感度并自动进休息；中途退出不给奖励 | `src/betty_pet/focus.py`、`window.py` |
| 物理运动 | 重力、终端速度、空气阻力、地面摩擦、阻尼反弹、拖拽投掷 | `src/betty_pet/physics.py` |
| 追鼠标 | 死区防抖，朝光标行走，开关写入存档 | `physics.py`、`movement.py`、`window.py` |
| 悬停反应 | 停留 0.8 秒触发挥手 | `window.py`、`config.py` |
| 窗口栖息 | 站到前台窗口上沿；随窗口移动/缩放跟随；窗口关闭、最小化或顶到屏幕顶部即掉落回地面 | `desktop.py`、`window.py` |
| 音效 | `SoundPlayer` 抽象 + 默认静音实现；事件键位、菜单开关、CLI 覆盖就位，**尚未接播放后端** | `src/betty_pet/audio.py` |
| 系统托盘 | pywin32 自绘图标（零新依赖）；显示/隐藏、跟随鼠标、退出；动作经队列回投主线程 | `src/betty_pet/tray.py` |
| 开机自启 | `--install-autostart` / `--uninstall-autostart` 写入「启动」文件夹的 `.vbs`（无窗口启动） | `src/betty_pet/autostart.py`、`__main__.py` |

边界仍然清楚：**音效只有抽象层、没有播放后端；没有道具数量与货币；没有多角色/皮肤；没有沿墙与天花板
攀爬；没有多实例；没有本地模型对话。** 同类项目的横向对比与借鉴顺序见
[现有桌宠项目调研](EXTERNAL_REFERENCES.md)。

## 3. 建议的目标架构

```text
Tkinter/PetWindow（渲染与输入）
        ↓ 发布用户事件 / 订阅表现指令
EventBus + Scheduler（事件、随机时间、优先级、冷却）
        ↓
PetState（情绪、需求、关系、背包、记忆、指标）
        ↓
BehaviorEngine（规则/行为树/效用选择）
        ↓
ActionPlayer + AssetCatalog（动作、帧、音效、换装图层）
        ↓
DialogueService（模板、LLM 适配器、内容安全）
        ↓
Persistence（SQLite/JSON 存档、事件日志、配置）
```

关键原则：`PetModel` 继续保持无 UI；Tkinter 只负责显示和投递事件；耗时的 LLM、数据库和指标计算不得阻塞 Tk 主线程。

## 4. 扩展方向

### 4.1 道具、背包与换装

增加 `Item`、`Inventory`、`Equipment` 三个领域对象。道具应包含 `id/name/type/effect/duration/cooldown`，使用后通过事件修改状态，例如喂食增加饱腹度、玩具触发开心动作、服装切换渲染图层。素材 manifest 可扩展为带元数据的 JSON：动作帧、锚点、图层顺序、碰撞区域、音效。

### 4.2 本地大模型接入

定义稳定的 `DialogueProvider` 接口（`reply(context) -> Reply`），再实现 Ollama、llama.cpp 或 OpenAI-compatible 本地 HTTP 适配器。模型调用放入线程/进程队列，由 Tk 主线程轮询结果；增加超时、取消、离线回退和上下文长度上限。不要让模型直接修改状态，模型只能返回“文本 + 结构化意图”，意图由白名单命令执行。

### 4.3 更丰富的对话与互动

将现有随机消息拆成 `DialogueCatalog`：按动作、情绪、时间段和用户行为匹配模板。加入连续对话上下文、打断、输入框、快捷回复、语音输入/播报（可选）以及对话冷却。所有回复保留模板回退，保证模型不可用时仍可运行。

### 4.4 信息管理与记忆

用 SQLite 保存用户偏好、宠物档案、事件日志和记忆摘要；短期记忆保留最近 N 轮，长期记忆只保存高价值事实（偏好、重要日期、明确承诺）。为记忆增加来源、时间、置信度和可删除 API，提供“查看/编辑/清空记忆”界面。后续可选向量检索，但应先用 SQLite FTS 或关键词检索验证价值。

### 4.5 情绪、需求与指标

建议把数值统一为 0~100，并记录变化原因：`hunger`、`energy`、`happiness`、`affection`、`health`、`stress`。情绪不是单独硬编码，而是由数值映射到 `mood`（平静、开心、困倦、委屈等），再影响对话语气、动作权重和随机事件。指标系统应支持当前值、变化量、阈值事件和历史曲线；UI 可先做托盘/小面板，再接监控导出。

### 4.6 随机时间触发与行为系统

将 `root.after` 的散落定时器集中到 `Scheduler`。事件定义为 `trigger/condition/cooldown/weight/effect/action`，支持启动、定时、空闲、用户点击、系统时间和连续行为触发。行为选择可从随机抽样升级为效用评分：需求越紧迫、情绪越匹配，动作权重越高；增加动作优先级和可打断规则，避免多个 `after` 同时把宠物强行切回 idle。

### 4.7 更生动流畅的动画

短期：manifest 增加每帧时长、循环模式、动作结束回调和插值位移；缓存不同缩放尺寸，避免缩放时重复解码。中期：支持图层合成（身体/服装/道具/特效）、阴影、粒子和屏幕边界寻路。长期：把 Tk Canvas 渲染层替换为更适合高帧率的渲染器，同时保留 `ActionPlayer` 接口。动画资源需配套预览、帧率检查和透明边缘检查。

## 5. 分阶段落地顺序

1. **基础重构**：引入 `PetState`、事件类型和 `Scheduler`，把定时器、动作优先级、配置持久化从 `PetWindow` 中移出。
2. **可玩性闭环**：需求/情绪数值、道具背包、模板对话、SQLite 存档、状态小面板。
3. **智能交互**：`DialogueProvider` 接口、本地 LLM 适配器、意图白名单、短期/长期记忆和离线回退。
4. **表现升级**：图层换装、帧级时间轴、音效、粒子、边界移动和更高帧率渲染。
5. **可运营性**：指标历史、调试面板、事件回放、插件 API、自动化素材/动画测试。

## 6. 第一批建议新增的接口

```python
class DialogueProvider(Protocol):
    def reply(self, context: DialogueContext) -> Reply: ...

class Scheduler(Protocol):
    def schedule(self, event: ScheduledEvent) -> None: ...

class StateStore(Protocol):
    def load(self) -> PetState: ...
    def save(self, state: PetState) -> None: ...
```

先定义接口，再接具体实现，可以让桌宠在无模型、无数据库时继续启动，也便于测试。领域层应有单元测试；调度、存档和模型适配器使用 fake 实现测试；Tkinter 只保留少量手工/端到端测试。

## 7. 需要提前注意的风险

- Tkinter 不是线程安全的，任何 UI 更新必须回到主线程。
- 随机动作、用户点击和 LLM 回复可能竞争，必须有优先级、取消和冷却机制。
- 本地模型的输出不能直接执行文件、网络或任意 Python；只接受校验后的结构化意图。
- 记忆涉及隐私，默认本地存储、可见可删，并限制日志内容。
- 资源名称目前包含空格和大小写差异，新增资源时建议统一命名并在 manifest 校验 schema。
- 配置、存档和模型服务都可能失败，必须有默认值和离线降级路径。

## 8. 当前实现注意事项

这一节记录已经落地的接口约定，后续新增功能应遵守这些约定：

- `PetStats.hunger` 是“饥饿程度”，数值越高越饿；`mood` 和 `energy` 数值越高越好，三者都限制在 `0~100`。
- `PetStats.adjust()` 会自动截断越界值；恢复手段只应提交增量，不要直接绕过该方法修改状态。
- `PetState.update_elapsed()` 根据 `last_updated` 计算离线期间的自然衰减。当前窗口在随机行为触发前调用它，接入存档后应在启动和保存前各调用一次。
- `StatRecovery` 是最简单的恢复实现，适合 cookie、睡觉、玩具等固定效果；有次数、冷却、条件或副作用的道具应实现自己的 `RecoveryMethod`，不要把规则塞进窗口类。
- `BehaviorAction.animation_name` 必须对应 `assets/manifest.json` 的动作名；行为规则可以多于当前素材，但 `ThresholdBehaviorEngine` 会过滤不可用动画并回退到 idle。
- `BehaviorRule` 的阈值是包含边界的（例如 `energy_at_most=20` 在精力等于 20 时生效）；`weight` 必须大于 0 才会参与抽样。
- `LanguageProvider` 只负责返回文本，不应直接修改 `PetState` 或调用 Tkinter。未来的本地大模型适配器应放到后台线程，并将结果回传主线程。
- 所有延迟调用都必须走 `Scheduler`，不要再用 `root.after()`。`Scheduler` 接受一个 `Clock`：生产用 `TkClock`（包装 `after` / `after_cancel`），测试用 `ManualClock`（时间只在 `advance()` 时前进）。
- `Scheduler` 的任务按 `name` 唯一、`group` 分组。已有分组：`animation`、`motion`、`behavior`、`dialog`、`action`、`recovery`、`status`、`persistence`。关闭面板、取消移动时按组取消，不要逐个名字记。
- `Scheduler.schedule()` 返回 `False` 表示被拒绝（冷却未过、或新任务优先级低于同名在途任务），调用方要接受被拒绝而不是假设一定生效。
- `Scheduler.repeat()` 不支持冷却：冷却时间会大于间隔时把自续期任务卡死。
- 动作优先级常量在 `window.py`：`PRIORITY_IDLE=0` < `PRIORITY_RANDOM=1` < `PRIORITY_USER=5`。`play()` 会拒绝低于当前在播动作优先级的请求，但 `idle` 永远放行，避免宠物卡在某个动作上；因此新增动作时必须保证最终有回 idle 的路径。
- 状态持久化在 `store.py`：`StateStore` 协议 + `SQLiteStateStore` + `MemoryStateStore`（`--no-persist` 或存档失败时的降级实现）。表结构为 `pet_state` / `settings` / `event_log`，事件日志由 `_autosave()` 自动裁剪到最近 500 条。
- `PetWindow` 在构造时 `store.load()` 并 `update_elapsed()`，在 `persist_state()`（自动保存与退出）时再 `update_elapsed()`；新增持久化字段时这三处要同步。
- `SQLiteStateStore` 建库失败会回退到 `MemoryStateStore`，这是刻意的离线降级路径，不要改成抛异常终止启动。
- `Scheduler.repeat()` 的回调可以取消自己（`cancel` / `cancel_group`）。运行中的任务已经离开待执行队列，但取消操作仍然能看到它，否则计时器会把自己重新排上，变成停不下来的循环。
- `physics.py` 只认像素和秒，不认 Tkinter。`step()` 的 `drive_vx` 是「控制器」语义：给值就直接设定水平速度（行走、追鼠标），不给值就按地面摩擦或空气阻力自然衰减。速度控制必须走这条路，不要自己去改 `MotionState`。
- `MotionState.grounded` 只表示「贴着地面且竖直速度非负」。落地后 `y` 会被吸附到 `placement.bottom`，不要依赖「接近地面」来判断站立。
- 物理循环只在宠物真的在动的时候运行：`_should_keep_physics()` 返回 `False` 就停。新增任何会让宠物移动的功能，都必须保证条件判断能覆盖到它，否则宠物会动一半停在半路。
- 屏幕下边界靠 `AppConfig.floor_offset_px` 预留任务栏高度（默认 48px）。Tkinter 拿不到任务栏真实高度，这是显式假设，多显示器场景需要另做处理。
- 拖拽位置会被裁剪到 `placement` 范围内，避免宠物被拖到屏幕外找不回来。想允许拖到任务栏区域就得放宽这个裁剪，但要同时提供找回手段。
- 物理与交互动词（`fall` / `thrown` / `dragged` / `chase_mouse`）走 `AssetCatalog.resolve()` 的 `ACTION_FALLBACKS` 回退链。补上对应 PNG 并写进 manifest 就会自动启用，`resolve()` 不需要改。
- `LOOPING_ACTIONS`（`idle` / `walk_left` / `walk_right`）循环播放，其余动作播放一次后停在末帧。新增循环类动作要加进这个集合。
- **道具是唯一该被"喂"给宠物的东西。** 不要再往 `window.py` 里塞硬编码的状态修改；加一样道具就是在 `default_items()` 里加一条 `Item`。`RecoveryMethod` / `StatRecovery` 这套旧抽象已被 `Item` + `apply_item()` 取代并删除，别把它们加回来。
- `Item.refusal()` 的判定顺序是固定的：**先判饱腹，再判每日上限**。`full_at` 用 `hunger`（越大越饿）的语义，所以 `full_at=20` 表示"饥饿值 ≤ 20 就吃不下"。
- `apply_item()` 只负责判定和改数值，**不记录每日次数**——次数由调用方在成功之后 `store.bump_daily()`。这样重复调用 `apply_item` 不会污染配额，测试也更好写。
- 三种拒绝（`full` / `limit` / `wait`）都在 `request_item()` 里同步判定并直接说话，**不进 Scheduler、不消耗次数**。冷却中也要能说话，否则用户点了没反应会以为程序卡了。
- 菜单标签是"今日剩 N"，靠 `show_menu()` 里的 `_refresh_item_labels()` 在每次弹出前重渲染。Tk 菜单不会自动跟随状态变化，新增带配额的菜单项要一并登记进 `_item_groups`。
- 好感度存在 `PetState.affection`，**不进 `PetStats`**——`PetStats` 的三个值都会衰减且被夹在 0~100，好感度只增不减、没有上限。
- 存档表加字段必须同步更新 `store.py` 的 `ADDED_COLUMNS`，否则老存档打开会缺列。现在有一条针对老库的回归测试，别删。
- 每日次数按**本地日期**（`local_day()`）分桶，用 `(day, key)` 作主键，跨天自然归零，不需要清理任务。
- 左右行走由 `MovementPlanner` 生成随机距离，`PetWindow.start_walk()` 按固定步长移动窗口；目标位置按屏幕左右边界裁剪，撞墙后播放 `climb`。
- `PetWindow.cancel_motion()` 会取消当前移动定时器；点击触发其他动作、关闭窗口或新行走动作时都应调用它，避免旧回调继续修改窗口位置。
- 当前“墙壁”仅指主屏幕左右边界，尚未处理多显示器、任务栏工作区、屏幕顶部/底部和其他窗口碰撞。
- 位置移动仍依赖 Tkinter 的 `after()`，移动回调必须在 Tk 主线程执行；后续耗时寻路或窗口扫描不能直接放进该回调。
- `desktop.py` 只报**前台窗口**，并且默认用当前进程号把自己的窗口排除掉：用户点宠物时宠物就是前台窗口，不排除就会"栖息在自己身上"。别再改成"枚举全部窗口"——那会让宠物爬到它够不着的对话框和 tooltip 上。
- 栖息**不是新的物理**：`_active_bounds()` 把窗口上沿折算成一个临时 `Bounds`（地面=窗口上沿、左右=窗口左右边）喂给原来的 `step()`。沿窗口行走、掉落回地面全是既有逻辑，不要为此改 `physics.py`。
- **最大化的窗口会被拒绝栖息**：它的上沿在屏幕最顶端，宠物没地方站。宁可拒绝，也不要让宠物盖住窗口标题栏和关闭按钮。
- 窗口轮询（`_probe_windows`，默认 500ms）只在栖息面**真的变了**时才唤醒物理循环（靠 `_perch_surface` 比对）。否则宠物静止时会每 500ms 被唤醒一次空转。
- 抓取宠物（拖拽超过 3px）才脱离窗口，**单击不会**——否则点一下宠物就掉下去。
- `audio.py` 的音效键是**封闭集合**（`SOUND_KEYS`），键名是语义而非文件名。加音效＝加一个键 + 一个调用点；后端只要实现 `SoundPlayer.play(key)`，不要改调用点。
- 音效默认**关闭**，开关存在 `settings.sound`；CLI 的 `--sound` / `--no-sound` 显式覆盖存档（`AppConfig.sound_enabled=None` 表示"没意见，听存档的"）。
- `tray.py` 的 win32 部分**只能在托盘线程里跑**（`PumpMessages` 阻塞，而 Tk 占着主线程）。托盘动作一律 `put` 进 `TrayIcon.actions`，由主线程的 `_drain_tray` 消费——Tkinter 不是线程安全的，托盘线程里绝不能直接碰 UI。
- 托盘、栖息、pywin32 都**允许不存在**，分别降级为 `NullTray` / `NullWindowProbe` / 直接可用。新增平台相关能力时保持这个模式，别让"没有托盘"变成"启动不了"。
- 没有托盘时 `hide_pet()` 会**拒绝隐藏并说明原因**，否则宠物会藏到一个回不来的地方。
- `autostart.py` 是唯一会写项目目录之外的模块，且**只在显式命令下执行**（`--install-autostart` / `--uninstall-autostart`），写的是「启动」文件夹里的 `.vbs`（可见、可单独删除）。不要在启动流程里自动调用它。
- **"静止姿态"是可换的**：`play(idle)` 不直接播 `idle`，而是播 `self._rest_action`（默认 `IDLE`，专注期间是 `SIT`）。这样"专注时坐着"不需要额外的定时器去维持——任何动作播完、任何打断之后，`return_idle` 都会把宠物带回坐姿。新增需要改变常态姿态的功能时，改 `_rest_action` 而不是反复 `play("sit")`。
- `_rest_action` 只在 `play()` 里生效：`play("sit", ...)` 会照常按普通动作处理（1.2 秒后回 idle）。**别用 `play("sit")` 表示"坐下别动"**，那只会坐 1.2 秒。
- `focus.py` 的 `FocusTimer` 是**纯状态机**：不碰 Tkinter、不碰 `Scheduler`、没有自己的时钟，由窗口把流逝的毫秒喂给它。`tick()` 返回**刚刚结束的阶段**（`FOCUS` / `BREAK`），阶段转换发生在 `tick()` 内部。
- `FocusTimer.tick()` **一次最多推进一个阶段**，超出的 `delta_ms` 直接丢弃。睡了一觉醒过来不应该一口气跑完好几个番茄钟。
- 专注**只有坐满才算**：`_complete_focus()` 才给好感度和 `daily_usage` 的 `focus` 计数；`stop_focus()`（提前退出）什么都不给。这是这个功能存在的理由，不要"按比例折算"。
- 专注的分组是 `focus`（倒计时任务），与 `behavior`（随机动作）分开：`_focus_quiet(True)` 取消 `behavior` 但不取消 `focus`。别把倒计时塞进 `behavior`，否则一安静就把自己停了。
- 专注期间 `_chase_velocity()` 返回 `None`（不追鼠标）、`on_hover_enter()` 直接 return（不挥手）。想加新的"主动打扰"行为时记得也判一下 `self.focus_timer.active`。

## 9. 后续会话交接记录

每次继续开发前先阅读本节和 `git diff`，结束前更新本节，保持实现状态可交接。

**已完成（历史会话，按时间顺序）**

1. `state.py`：`PetStats`、`PetState`、`RecoveryMethod`、`StatRecovery`。
2. `behavior.py`：`BehaviorAction`、`BehaviorRule`、`ThresholdBehaviorEngine`、`LanguageProvider` 及模板实现。
3. `movement.py`：`MovementPlan`、`MovementPlanner`、`horizontal_target()`。
4. `scheduler.py`：`Clock` / `ManualClock` / `TkClock` / `Scheduler`（命名任务、优先级、分组取消、冷却、`repeat`）。窗口内 `root.after()` 已清零。
5. `store.py`：`StateStore` / `SQLiteStateStore` / `MemoryStateStore`。
6. 右键菜单喂食 / 休息 / 玩耍（4 秒冷却）+ 状态面板 + 历史记录；`default_recoveries()`；CLI `--db` / `--no-persist` / `--status`。

**已完成（上一轮：物理运动）**

- 新增 `src/betty_pet/physics.py`：`PhysicsConfig`、`Bounds`、`MotionState`、`MotionEvents`、`step()`、`DragTracker`、`bounds_for()`、`clamp_to_bounds()`、`clamp_speed()`。纯逻辑，17 项单测。
- 窗口位移全部改由物理驱动：出生在屏幕右下角地面；拖拽记录轨迹，松手按释放速度投掷；重力下落、撞墙与落地阻尼反弹、空气阻力、地面摩擦；静止后自动停掉步进循环，不空转。
- 行走改走物理层，走到计划距离或撞墙后播放 `climb`（外部行为不变，实现换了）。
- 菜单新增「跟随鼠标」（ChaseMouse，带死区，开关写入存档）；鼠标悬停 0.8 秒触发挥手。
- `assets.py` 新增 `ACTION_FALLBACKS` 与 `AssetCatalog.resolve()`，物理动词缺素材时回退到现有动作。
- `movement.py` 新增 `chase_direction()`；`config.py` 新增 `physics` / `physics_interval_ms` / `floor_offset_px` / `chase_speed_px` / `chase_deadzone_px` / `hover_delay_ms` / `initial_margin_px`。
- `LOOPING_ACTIONS` 让 `walk_left` / `walk_right` 真正循环播放（此前会停在末帧）。
- **修复两个真 bug**：`Scheduler.repeat()` 回调自我取消时计时器会复活成停不下来的循环；落地后 `y` 停在地面上方 0.05px 导致物理循环空转。
- 新增 `docs/EXTERNAL_REFERENCES.md`：同类项目调研、能力矩阵与分批借鉴顺序。
- 测试现为 45 项（新增 `test_physics.py`），`pytest` 与 `ruff check src tests main.py` 通过；另做过一次 Tk 冒烟，覆盖出生位置 / 悬停挥手 / 拖拽 / 投掷 / 落地 / 甩飞 / 追鼠标 / 撞墙爬 / 状态面板 / 喂食冷却。

**已完成（历史：养成闭环）**

- 新增 `src/betty_pet/items.py`：`Item`、`ItemOutcome`、`apply_item()`、`default_items()`、`items_by_group()`。6 件道具分喂食 / 玩耍 / 休息三组，菜单由表自动生成。
- **新增"拒绝"这一层**：吃饱（`full_at`）、当日上限（`daily_limit`）、冷却未到，三种拒绝各有台词且不消耗次数。这是让宠物从"按钮面板"变成"有身体的角色"的关键。
- 好感度：`PetState.affection` + `affection_level()` / `affection_title()` / `affection_to_next_level()`，每 50 点一级共 6 档，只增不减；升级会说出来并写 `level_up` 事件。
- 存档：`pet_state` 加 `affection` 列并带**迁移逻辑**（老库自动补列，有回归测试）；新增 `daily_usage(day, key, count)` 表按本地日期分桶记录每日次数。
- 右键菜单改为三组子菜单，标签实时显示"今日剩 N"；状态面板增加好感度、等级与升级进度。
- **删除已过时的抽象**：`RecoveryMethod` / `RecoveryResult` / `StatRecovery` / `default_recoveries()` 被 `Item` + `apply_item()` 完全取代，已从 `state.py` 与 `__init__` 导出中移除，相关测试迁移到 `tests/test_items.py`。
- 测试现为 65 项（新增 `test_items.py`，扩充 `test_state.py` / `test_store.py`），`pytest` 与 `ruff` 通过；另做过一次 Tk 冒烟，覆盖子菜单生成、配额标签刷新、喂食、冷却拦截、吃饱拒绝、上限拒绝、升级播报、状态面板、事件落库。

**已完成（上一轮：窗口栖息 / 托盘 / 音效骨架）**

- 新增 `src/betty_pet/desktop.py`：`WindowRect`、`WindowProbe` 协议、`NullWindowProbe`、`Win32WindowProbe`、`make_probe()`、`perch_bounds()`。只报**前台窗口**，并按进程号排除自己。
- **窗口栖息**：菜单「跳到窗口」把宠物放到前台窗口上沿，「离开窗口」让它掉回地面；窗口移动/缩放会跟随，关闭、最小化或顶到屏幕顶端会自动脱离并掉落。实现方式是**换 `Bounds`，不动物理**。
- 新增 `src/betty_pet/audio.py`：`SoundPlayer` 协议 + `SilentPlayer`（只记录不发声）+ 语义键 `SOUND_KEYS` + `sound_for_group()`。菜单与 CLI 都有开关，**播放后端刻意留空**。
- 新增 `src/betty_pet/tray.py`：pywin32 自绘托盘（零新依赖）——显示/隐藏、跟随鼠标、退出；动作经 `queue` 回投主线程；无 pywin32 时降级为 `NullTray`。
- 新增 `src/betty_pet/autostart.py` 与 `--install-autostart` / `--uninstall-autostart` / `--autostart-status`：写「启动」文件夹里的 `.vbs`（`pythonw` 无黑框启动）。**只提供命令，未实际写入**。
- `config.py` 新增 `perch_poll_ms` / `tray_poll_ms` / `sound_enabled`；`--sound` / `--no-sound` 覆盖存档。
- 测试 65 → 99 项（新增 `test_desktop.py` / `test_audio.py` / `test_tray.py` / `test_autostart.py`）。另做过一次 Tk 冒烟，覆盖：栖息到窗口上沿（y=172）、状态面板显示「窗口上」、窗口下移后跟随（y=372）、窗口消失后掉落回地面（y=904）、离开窗口、静止时物理循环不空转、喂食/拒绝音效键、托盘队列翻转跟随鼠标、无托盘时拒绝隐藏、隐藏/恢复往返。

**已完成（当前会话：专注计时）**

- 新增 `src/betty_pet/focus.py`：`FocusTimer`（纯状态机，`FOCUS` / `BREAK` / `IDLE`）+ `format_mmss()`。20 项单测。
- **专注（番茄钟）**：菜单「专注 25 分钟」/「结束专注」，CLI `--focus` / `--focus-minutes`。专注期间宠物坐下不动、随机动作停掉、不追鼠标、悬停不挥手，状态面板多一行实时倒计时。
- **坐满才给奖励**：走完 25 分钟才 +3 好感度并记 `focus` 事件与每日次数，然后自动进入 5 分钟休息（继续坐着），休息结束自己回常态。中途退出**什么都不给**。这是目前唯一不靠道具的好感度来源。
- **发现并修复一个真 bug**：`play("sit")` 会被 1.2 秒后的 `return_idle` 拉回站姿，25 分钟的"陪坐"实际只坐 1.2 秒。改成引入 `self._rest_action`（静止姿态）——专注期间把它从 `idle` 换成 `sit`，于是 `play(idle)` 本身就是坐下，姿态不需要额外定时器维持，也不会和 `return_idle` 打架。
- `speak()` 增加 `**values`，模板里的 `{minutes}` / `{title}` 由调用点填；`_announce_level_up()` 一并改走 `speak()`，去掉重复的分支。
- `config.py` 新增 `focus_minutes` / `focus_break_minutes` / `focus_poll_ms` / `focus_affection`；`audio.py` 的 `SOUND_KEYS` 新增 `focus_start` / `focus_done`；包版本 0.5.0 → 0.6.0，`pyproject.toml` 同步。
- 新增 `docs/CLIMBING_DESIGN.md`：沿墙/天花板攀爬的设计草案（抽象"依附面"、把重力映射到规范坐标），**尚未实现**，其中 3 个决策待确认（素材、墙壁自由度、屏幕边界范围）。
- 测试 99 → 119 项（新增 `tests/test_focus.py`），`pytest` 与 `ruff check src tests` 通过。另做过一次 Tk 冒烟 + 一次 CLI 桩测试，覆盖：起始无倒计时行、坐姿跨过 `action_duration_ms` 仍然保持、`happy` 播完回到坐姿、专注期间忽略悬停、倒计时实时递减、坐满 +3 且不重复计数、自动进休息并在休息期间继续坐着、休息结束回常态、提前退出不给好感度、音效键落到播放器、升级模板未回归、`--focus` / `--focus-minutes` 生效且 `0` 被拒。

**尚未完成**

- `LanguageProvider` 目前只有模板实现，尚未接入 Ollama/llama.cpp 等本地模型。
- 道具没有数量、没有货币、没有解锁条件。刻意如此：没有"打工赚钱→买道具"的循环时，数量只会变成一个再也回不来的数字，读起来像 bug 而不是机制。
- 好感度现在有两个来源（道具、坐满一次专注），但仍没有**抚摸 / 点按 / 长时间陪伴**这类轻交互。点宠物目前只播 `click` 动作和随机台词，不加好感度。
- 专注只有单段固定时长（`focus_minutes` / `focus_break_minutes`），没有多轮循环、没有"长休息"、没有跨次累计统计；`FocusTimer.completed_sessions` 只在内存里，重启即清零（落库的是每日次数）。
- **音效只有抽象层与静音实现**：开关打开也没有声音——缺播放后端，也缺音频素材（`assets/` 里一个音频文件都没有，manifest 也没有音频段）。
- 托盘用的是系统默认图标，没有自己的 `.ico`；托盘菜单里还没有「跳到窗口」这类入口。
- 栖息只认主屏幕边界，且拒绝最大化窗口；多显示器未处理。开机自启的命令写好了但**没执行过**，真机开机验证待做。
- 没有多角色皮肤、沿墙与天花板攀爬、多实例。
- 碰撞边界只有主屏幕上下左右；任务栏高度靠 `floor_offset_px` 假设，多显示器未处理。
- 物理动词缺专属素材（`fall` / `thrown` / `dragged` 三张 PNG），目前走回退链。
- `png_process.py` 有一个既有的 ruff 报警（`PIL.Image` 未使用），与代码改动无关，未处理。

**推荐下一步**

批次三还剩**沿墙与天花板攀爬**和**多实例**，两者都是结构性改动，动手前先补设计：

- **攀爬**要先给 `Bounds` / `MotionState` 增加"依附面"概念——现在 `grounded` 只有"贴地"一个含义，
  而 Shimeji 的动作表里沿墙、沿天花板是与地面并列的状态。这次栖息已经证明"换 `Bounds`、不动物理"
  这条路可行，攀爬可以照这个思路往四向扩展。草案见 [攀爬设计草案](CLIMBING_DESIGN.md)，
  但**卡在素材**：`assets/` 里没有攀爬动作的 PNG，而且墙壁只在主屏幕左右边界、没有别的窗口参与。
- **多实例**要先回答两个问题：一份状态还是多份状态、存档怎么区分。建议先出设计文档再动代码。

音效要真正响起来，最省事的顺序是：先有音频素材（或允许我用程序合成占位音），再挂后端。
目前**素材比后端更卡脖子**。

轻交互（抚摸 / 点按给好感度）是比攀爬更小的一步，可以作为多实例与攀爬之间的填充：改动只在
`window.py` 的点击处理 + 一个新的事件键，不需要新素材。

`LanguageProvider` 与 `StateStore` 两个接口都已就位，接模型时不要改窗口类。
