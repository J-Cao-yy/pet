# 沿墙与天花板攀爬 · 设计草案

> 状态：**草案，未实现**。`docs/PROJECT_DISTILLATION.md` §9 已写明这一步是结构性改动、
> 必须先出设计。本文就是那份设计。文中标了三个需要用户拍板的决策点，见 §7。

## 1. 目标行为（对齐 Shimeji）

Shimeji 的动作表里，四个方向是**并列**的，不是"地面 + 特例"：

| 状态 | 表现 |
| --- | --- |
| 地面 | 在屏幕底部左右走（已有） |
| 沿左墙 / 沿右墙 | 贴住屏幕左右边缘，上下移动 |
| 沿天花板 | 贴住屏幕顶部，横向移动 |

玩家的动作序列大致是：在地面走到屏幕边缘 → 吸附到墙上 → 沿墙往上爬 → 爬到顶端吸附到
天花板 → 沿天花板横移 → 从另一侧下来。任何时候被拖拽/投掷都会打断攀爬、掉回地面。

## 2. 现状与差距

| 项 | 现状 |
| --- | --- |
| 重力方向 | 恒定向下（`physics.step()` 里 `vy += gravity * dt`） |
| 支撑面 | 只有 `bounds.bottom` |
| `MotionState.grounded` | 只有"贴地"一个含义 |
| 边界 | 只有主屏幕四边，且左右边是"撞墙就停"的墙，不是可攀附的表面 |
| 素材 | 只有 `climb.png` / `climb-1.png`；**缺**沿墙上下与天花板行走的帧 |

## 3. 核心方案：把「重力方向 + 支撑面」抽成一个 `Surface`

关键判断：**不需要为攀爬改写物理**。栖息那次已经证明"换个 `Bounds` 就能站在别的东西上"，
攀爬是同一思路的推广——把坐标系转一下即可。

```python
class Surface(StrEnum):
    FLOOR = "floor"
    CEILING = "ceiling"
    WALL_LEFT = "wall_left"
    WALL_RIGHT = "wall_right"
```

`step()` 增加一个 `surface: Surface = FLOOR` 参数。实现上**不建议写四套分支**，而是：

1. `to_canonical(state, bounds, surface)`：把状态与边界映射到规范坐标系
   —— 规范坐标系里**重力恒为 +y、支撑面恒为 `bounds.bottom`**；
2. 用现有的 `step()` 主体照常计算（重力、阻力、摩擦、阻尼反弹一行不改）；
3. `from_canonical(...)` 再映射回来。

四个表面各自的定义：

| Surface | 重力方向 | 支撑边 | 沿面运动 |
| --- | --- | --- | --- |
| `FLOOR` | `+y` | `bottom` | `vx` |
| `CEILING` | `-y` | `top` | `vx` |
| `WALL_LEFT` | `+x` | `left` | `vy` |
| `WALL_RIGHT` | `-x` | `right` | `vy` |

映射本质是一次旋转（`FLOOR` 不旋转；`CEILING` 旋转 180°；左右墙各旋转 ±90°）。

`MotionState` 增加 `surface: Surface = FLOOR`，`grounded` 的语义变为"贴着当前 surface"，
`settled()` 不变。`MotionEvents` 增加 `attached: Surface | None` 与 `detached: bool`。

## 4. 吸附与脱离规则（放在 window 层，不进 physics）

物理只负责"在有支撑面的情况下怎么动"，"什么时候换支撑面"是玩法，属于窗口层：

- 在地面朝某一侧走到 `x == bounds.left / right` 且**继续朝该侧走** → 吸附到
  `WALL_LEFT` / `WALL_RIGHT`，并把速度转成向上爬（`vy = -walk_speed`）；
- 沿左墙爬到 `y == bounds.top` → 吸附 `CEILING`；沿右墙同理；
- 从墙上走回 `y == bounds.bottom` → 回到 `FLOOR`；
- **任何一次拖拽/投掷都打断攀爬**，恢复 `FLOOR` 重力自然下落；
- 换面时播放一次过渡动画（现在可以先复用 `climb`）。

## 5. 素材缺口（这是真正的卡点）

| 需要的动作 | 现状 | 影响 |
| --- | --- | --- |
| `walk_left` / `walk_right` | 有 | 地面用 |
| `climb_wall_left` / `climb_wall_right` | **没有** | 沿墙上下；现在只能回退到 `climb.png` |
| `walk_ceiling` | **没有** | 天花板横向；没有可回退的合适帧 |

回退链（`assets.py` 的 `ACTION_FALLBACKS`）可以让代码先跑起来，但没有素材时视觉上是
"站着贴墙平移"，比不做好不了多少。所以：

**建议先把 `ACTION_FALLBACKS` 的键位加上、逻辑打通，素材等有了再挂**；或者由用户决定
是否接受用现有 `climb` 帧做旋转/翻转占位。

## 6. 工作量与风险

| 部分 | 规模 | 说明 |
| --- | --- | --- |
| `physics.py` | 中 | 坐标映射 + `Surface` + 新事件，约 +120 行、+15 项单测 |
| `window.py` | 中 | 吸附规则、换面动画、状态面板显示"贴墙 / 天花板"、打断处理 |
| 回归 | **必须** | `grounded` 语义变了，既有 17 项 physics 测试与栖息路径都要重跑 |
| 栖息 | 不受影响 | 栖息只是换 `Bounds`，`surface` 始终是 `FLOOR` |

## 7. 需要拍板的决策点

1. **做不做、以及素材怎么办**：没有 `climb_wall_*` / `walk_ceiling` 素材时，是先打通逻辑
   （视觉上将就），还是等素材到位再动手？
2. **墙上的自由度**：只允许贴墙上下（Shimeji 的做法），还是也允许在墙上横向挪动？
3. **屏幕边缘的范围**：左右边缘现在只有主屏幕。任务栏区域（`floor_offset_px`）和副显示器
   算不算可攀附的表面？这会影响 `Bounds` 的定义。

## 8. 建议顺序

攀爬被素材卡着，**先做不依赖素材的批次三剩余项更划算**：番茄钟/提醒（纯逻辑、复用
`Scheduler`），然后是多实例（需要先定"一份状态还是多份状态"）。等 §7 的三个问题有答案、
素材也有着落，再按本文实现攀爬。
