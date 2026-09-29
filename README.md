# Betty Pet

一个以 Python/Tkinter 为基础的高自定义桌宠原型。当前支持透明置顶窗口、重力与投掷物理、跟随鼠标、拖拽、右键菜单、缩放、随机动作、对话气泡、SQLite 存档和按 manifest 管理动画素材。

## 交互

| 操作 | 效果 |
| --- | --- |
| 左键拖拽 | 拎起宠物；松手时按拖拽速度决定是「放下」还是「扔出去」 |
| 左键单击 | 触发 click 动作与随机台词 |
| 鼠标悬停 0.8 秒 | 打招呼 |
| 滚轮 / 右键「放大 / 缩小」 | 缩放（0.3~2.5 倍，写入存档） |
| 右键菜单 | 喂食 / 玩耍 / 休息（子菜单标出今日剩余次数）、跟随鼠标、状态面板、历史记录、退出 |

宠物从屏幕右下角出现并站在地面上；被扔出去会走抛物线、撞墙和落地都会带阻尼反弹，最终停下。
「跟随鼠标」打开后会朝光标走过去，靠近到死区内自动停下（防止来回抖动）。

## 养成

道具表在 `src/betty_pet/items.py` 的 `default_items()`，加一条就是加一个菜单项。

| 道具 | 分组 | 效果 | 今日上限 |
| --- | --- | --- | --- |
| 饼干 | 喂食 | 饥饿 −18，心情 +3，好感 +1 | 6 |
| 小鱼干 | 喂食 | 饥饿 −35，心情 +6，好感 +2 | 3 |
| 热茶 | 喂食 | 饥饿 −10，精力 +10，心情 +3，好感 +1 | 5 |
| 毛线球 | 玩耍 | 心情 +16，精力 −8，好感 +2 | 4 |
| 逗猫棒 | 玩耍 | 心情 +12，精力 −5，好感 +3 | 5 |
| 打个盹 | 休息 | 精力 +35，心情 +2，好感 +1 | 3 |

**宠物会拒绝。** 吃饱了（饥饿 ≤ 20）会说「吃不下啦」；当日次数用尽会说「今天已经吃够了」；
冷却没到会说「等一下嘛」。这三种拒绝都不消耗次数。

好感度每 50 点升一级：陌生 → 熟悉 → 朋友 → 好友 → 亲密 → 挚友。好感度**不会随时间衰减**，
升级时会说出来并写进事件日志。每日次数、好感度都在 SQLite 存档里，跨天自动重置。

## 准备环境

```powershell
conda activate pic
conda env update -f environment.yml
python -m pip install -e .
```

桌宠运行核心依赖是 Pillow；`png_process.py` 需要 OpenCV 和 NumPy，`environment.yml` 已包含。Windows 可用 `python -m tkinter` 检查 Tkinter。

## 运行

```powershell
python main.py
python main.py --check-assets
python main.py --scale 1.25 --no-random
python main.py --status                      # 打印存档状态与最近事件后退出
python main.py --db ./betty.db               # 指定 SQLite 存档位置
python main.py --no-persist                  # 本次运行不读写存档
```

## 目录约定

```text
src/betty_pet/
  config.py       运行配置
  assets.py       素材清单和加载
  model.py        与界面无关的动作状态机
  state.py        宠物状态、好感度、衰减
  items.py        道具表与使用规则（含拒绝条件）
  behavior.py     阈值行为、语言接口和模板实现
  movement.py     移动计划、边界目标与追鼠标方向
  physics.py      重力、摩擦、阻尼反弹、拖拽投掷速度
  scheduler.py    定时器调度（优先级、分组取消、冷却）
  store.py        SQLite 存档、设置和事件日志
  window.py       Tkinter 窗口和交互
  __main__.py     CLI 入口
assets/           已处理、可直接使用的 PNG 和 manifest.json
input/            原始素材
output/           png_process.py 的处理结果
```

## 存档

默认存档位置是 `~/.betty_pet/state.db`，三张表：`pet_state`（数值与时间戳）、`settings`（缩放等偏好）、`event_log`（启动/关闭/恢复事件，自动裁剪保留最近 500 条）。启动时读取并按离线时长补算自然衰减，运行中每分钟自动保存，退出前再保存一次。存档不可用时自动降级为内存存档，不影响启动。

## 素材

新增动作时，在 `assets/manifest.json` 增加动作名和 PNG 文件列表即可。

物理与交互动词（`fall` / `thrown` / `dragged` / `chase_mouse`）目前没有专属素材，会按
`assets.py` 的 `ACTION_FALLBACKS` 回退到现有动作，因此不加素材也能正常运行。
想让它更准确，往 `assets/` 放这三张图并写进 manifest 即可，**不需要改代码**：
`fall.png`（下落）、`thrown.png`（被扔飞）、`dragged.png`（被拎起）。

## 延伸阅读

- 项目的当前边界、模块职责与扩展路线：[项目提炼与扩展路线](docs/PROJECT_DISTILLATION.md)
- 同类桌宠项目调研与可借鉴清单：[现有桌宠项目调研](docs/EXTERNAL_REFERENCES.md)

素材缩放时会自动将半透明边缘转换为透明/不透明两级，避免 Windows Tkinter 的洋红透明色产生紫红色光晕。
