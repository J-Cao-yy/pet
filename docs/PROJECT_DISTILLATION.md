# Betty Pet 项目提炼与扩展路线

## 1. 项目定位

Betty Pet 是一个运行在 Windows 桌面的轻量级 2D 桌宠原型。它的核心价值不是某一组 PNG，而是一个可替换素材、可编排动作、可逐步接入智能能力的桌面交互容器。

当前技术基线：Python 3.10+、Tkinter、Pillow；OpenCV/NumPy 只用于素材预处理。程序以单进程、单 Tk 事件循环运行，适合先验证交互和角色表现，再逐步增加本地服务与持久化能力。

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
| 命令行 | 资产目录、初始缩放、关闭随机动作、资产检查 | `src/betty_pet/__main__.py` |

目前它仍是“表现层原型”：没有用户档案、状态数值、事件总线、存档、网络/模型适配器，也没有对话上下文。因此扩展时应先把状态与调度从 Tkinter 代码中抽离出来。

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
- 当前状态、恢复效果和对话都没有持久化；关闭程序会丢失状态，这是下一阶段接入 SQLite 前的已知限制。
- 当前行为调度仍使用窗口中的 `root.after()`；增加更多事件前应先集中到 Scheduler，并实现动作优先级、取消和冷却，避免定时器互相覆盖。

## 9. 后续会话交接记录

每次继续开发前先阅读本节和 `git diff`，结束前更新本节，保持实现状态可交接。

**已完成（当前会话）**

- 新增 `src/betty_pet/state.py`：`PetStats`、`PetState`、`RecoveryMethod`、`StatRecovery`。
- 新增 `src/betty_pet/behavior.py`：`BehaviorAction`、`BehaviorRule`、`ThresholdBehaviorEngine`、`LanguageProvider` 及模板实现。
- `PetWindow` 已持有状态，并在随机动作时执行状态衰减、阈值行为选择和模板对话。
- `PetWindow.recover(method)` 与 `PetWindow.speak(context)` 已作为后续菜单、道具和模型接入点。
- 测试现为 11 项，`pytest`、`ruff check` 和素材检查均通过。

**尚未完成**

- 没有喂食、休息、玩耍等可见 UI 控件。
- 没有 SQLite 存档、配置保存和事件日志。
- `LanguageProvider` 目前只有模板实现，尚未接入 Ollama/llama.cpp 等本地模型。
- 行为调度尚未集中到独立 Scheduler，也没有动作优先级与冷却。

**推荐下一步**

先增加右键菜单的三个恢复动作（喂食、休息、玩耍），接入 `StatRecovery` 并显示状态面板；随后实现 SQLite `StateStore`。完成这两个闭环后，再接入本地模型和长期记忆。
