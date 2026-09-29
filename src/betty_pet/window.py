from __future__ import annotations

import math
import random
import time
import tkinter as tk
from dataclasses import replace
from tkinter import Menu, messagebox

from PIL import ImageTk

from .assets import AssetCatalog
from .behavior import (
    DialogueContext,
    TemplateLanguageProvider,
    ThresholdBehaviorEngine,
    default_behavior_rules,
)
from .config import AppConfig
from .items import GROUP_LABELS, Item, ItemOutcome, apply_item, default_items, items_by_group
from .model import PetModel
from .movement import MovementPlan, MovementPlanner, chase_direction, horizontal_target
from .physics import (
    Bounds,
    DragTracker,
    MotionEvents,
    MotionState,
    bounds_for,
    clamp_to_bounds,
    step,
)
from .scheduler import Scheduler, TkClock
from .state import affection_title, affection_to_next_level
from .store import MemoryStateStore, SQLiteStateStore

IDLE = "idle"
WALK_ACTIONS = ("walk_left", "walk_right")
LOOPING_ACTIONS = frozenset({IDLE, *WALK_ACTIONS})
PHYSICS_ACTIONS = frozenset({"fall", "thrown", "dragged"})

PRIORITY_IDLE = 0
PRIORITY_RANDOM = 1
PRIORITY_USER = 5

CHASE_POLL_MS = 250


class PetWindow:
    """Tkinter presentation layer for the desktop pet.

    Two loops keep the pet alive:

    * ``Scheduler`` jobs decide *what* the pet does (animation, behaviour,
      dialog, autosave). Timers are grouped so they can be torn down together
      and prioritised so a click is never overruled by a random action.
    * a physics loop - running only while the pet actually moves - decides
      *where* it is. Gravity, drag, friction and a damped bounce live in
      :mod:`betty_pet.physics`, keeping motion maths out of this class.
    """

    TRANSPARENT = "#ff00ff"

    def __init__(self, root: tk.Tk, config: AppConfig, store=None) -> None:
        self.root, self.config = root, config
        self.store = store if store is not None else self._build_store(config)
        self.scheduler = Scheduler(TkClock(root))

        self.state = self.store.load()
        self.state.update_elapsed()
        self.store.log_event("startup", self._stats_snapshot())

        self.catalog = AssetCatalog(config.asset_dir)
        self.model = PetModel(self.catalog.actions())
        self.movement_planner = MovementPlanner()
        self.drag_tracker = DragTracker()
        self.items = default_items()
        self._play_priority = PRIORITY_IDLE
        self.drag_origin: tuple[int, int] | None = None
        self.dragged = False
        self.walk_direction: str | None = None
        self.walk_remaining = 0.0
        self.walk_speed = 150.0
        self.walk_will_hit_wall = False
        self.follow_mouse = self.store.get_setting("follow_mouse") == "1"

        self.behavior_engine = ThresholdBehaviorEngine(
            default_behavior_rules(), available_actions=set(self.catalog.actions())
        )
        self.language_provider = TemplateLanguageProvider(
            {
                "sleep": ("贝蒂有点困了。",),
                "hungry": ("贝蒂肚子饿了。",),
                "tired": ("休息一下吧。",),
                "happy": ("今天心情不错！",),
                "greet": ("你好呀。",),
                "walk": ("出去走走。",),
                "eat_cookie": ("咔嚓咔嚓。", "饼干不错。"),
                "eat_fish": ("鱼干最好吃了！", "谢谢，这个我喜欢。"),
                "drink_tea": ("暖乎乎的。", "喝口茶歇会儿。"),
                "play_yarn": ("毛线球滚起来了！", "好玩！"),
                "play_feather": ("抓不到……再来！", "逗猫棒最讨厌了。"),
                "nap": ("眯一会儿……", "睡醒了。"),
                "full": ("吃不下啦，肚子已经圆了。", "饱了饱了，等会儿再吃。"),
                "limit": ("今天已经吃够了，明天再说吧。", "再吃就胖了。"),
                "wait": ("等一下嘛，贝蒂还没缓过来。", "让我歇会儿。"),
                "level_up": ("好感度提升了！现在是「{title}」。", "我们更熟了一点，已经是「{title}」了。"),
            }
        )

        stored_scale = self.store.get_setting("scale")
        self.scale = config.clamp_scale(float(stored_scale) if stored_scale else config.scale)

        root.overrideredirect(True)
        root.attributes("-topmost", True)
        root.attributes("-transparentcolor", self.TRANSPARENT)
        root.configure(bg=self.TRANSPARENT)
        self.canvas = tk.Canvas(root, bg=self.TRANSPARENT, highlightthickness=0)
        self.canvas.pack()
        self.sprite = self.canvas.create_image(0, 0, anchor="nw")

        self._build_dialog()
        self._build_status_panel()
        self._build_menu()

        self.canvas.bind("<ButtonPress-1>", self.on_mouse_down)
        self.canvas.bind("<B1-Motion>", self.on_mouse_move)
        self.canvas.bind("<ButtonRelease-1>", self.on_mouse_up)
        self.canvas.bind("<Button-3>", self.show_menu)
        self.canvas.bind("<MouseWheel>", self.on_wheel)
        self.canvas.bind("<Button-4>", lambda _event: self.change_scale(0.1))
        self.canvas.bind("<Button-5>", lambda _event: self.change_scale(-0.1))
        self.canvas.bind("<Enter>", self.on_hover_enter)
        self.canvas.bind("<Leave>", self.on_hover_leave)
        self.root.protocol("WM_DELETE_WINDOW", self.close)

        self.placement = self._measure_placement()
        self.motion = MotionState(
            x=max(self.placement.left, self.placement.right - config.initial_margin_px),
            y=self.placement.bottom,
            grounded=True,
        )

        self._load_images()
        self._render()
        self._apply_motion()
        self._start_timers()

    @staticmethod
    def _build_store(config: AppConfig):
        """SQLite when persistence is on, memory otherwise, never a crash."""
        if not config.persist:
            return MemoryStateStore()
        try:
            return SQLiteStateStore(config.db_path)
        except Exception as error:  # pragma: no cover - defensive fallback
            print(f"[betty_pet] 存档不可用，本次运行不持久化：{error}")
            return MemoryStateStore()

    def _build_dialog(self) -> None:
        self.dialog = tk.Toplevel(self.root)
        self.dialog.withdraw()
        self.dialog.overrideredirect(True)
        self.dialog.attributes("-topmost", True)
        self.dialog_label = tk.Label(
            self.dialog, bg="white", fg="#222222", font=("Microsoft YaHei UI", 10),
            relief="solid", bd=1, padx=8, pady=4,
        )
        self.dialog_label.pack()

    def _build_status_panel(self) -> None:
        self.status_window = tk.Toplevel(self.root)
        self.status_window.withdraw()
        self.status_window.title("贝蒂状态")
        self.status_window.attributes("-topmost", True)
        self.status_window.resizable(False, False)
        self.status_window.protocol("WM_DELETE_WINDOW", self.hide_status)
        self.status_text = tk.StringVar(value="")
        tk.Label(
            self.status_window, textvariable=self.status_text, justify="left",
            font=("Microsoft YaHei UI", 10), padx=12, pady=8,
        ).pack()
        tk.Button(self.status_window, text="关闭", command=self.hide_status, width=8).pack(pady=(0, 8))

    def _build_menu(self) -> None:
        self.menu = Menu(self.root, tearoff=0)
        self._item_groups = items_by_group(self.items)
        self._item_submenus: dict[str, Menu] = {}
        for group, members in self._item_groups.items():
            submenu = Menu(self.menu, tearoff=0)
            for item in members:
                submenu.add_command(
                    label=self._item_label(item),
                    command=lambda item_id=item.id: self.request_item(item_id),
                )
            self._item_submenus[group] = submenu
            self.menu.add_cascade(label=GROUP_LABELS.get(group, group), menu=submenu)
        self.menu.add_separator()
        self.follow_var = tk.BooleanVar(value=self.follow_mouse)
        self.menu.add_checkbutton(label="跟随鼠标", variable=self.follow_var, command=self.toggle_follow_mouse)
        self.menu.add_command(label="状态面板", command=self.show_status)
        self.menu.add_separator()
        self.menu.add_command(label="放大", command=lambda: self.change_scale(0.1))
        self.menu.add_command(label="缩小", command=lambda: self.change_scale(-0.1))
        self.menu.add_separator()
        self.menu.add_command(label="历史记录", command=self.show_history)
        self.menu.add_command(label="检查素材", command=self.check_assets)
        self.menu.add_command(label="退出", command=self.close)

    def _item_label(self, item: Item) -> str:
        if item.daily_limit is None:
            return item.name
        remaining = max(0, item.daily_limit - self.store.daily_count(item.id))
        return f"{item.name}（今日剩 {remaining}）"

    def _refresh_item_labels(self) -> None:
        """Menus do not observe state, so the quota is re-rendered on open."""
        for group, members in self._item_groups.items():
            submenu = self._item_submenus[group]
            for index, item in enumerate(members):
                submenu.entryconfigure(index, label=self._item_label(item))

    @property
    def size(self) -> tuple[int, int]:
        edge = int(self.config.base_size * self.scale)
        return edge, edge

    def _measure_placement(self) -> Bounds:
        width, height = self.size
        return bounds_for(
            self.root.winfo_screenwidth(),
            self.root.winfo_screenheight(),
            width,
            height,
            self.config.floor_offset_px,
        )

    def _load_images(self) -> None:
        self.images: dict[str, list[ImageTk.PhotoImage]] = {}
        for action in self.catalog.actions():
            self.images[action] = [ImageTk.PhotoImage(frame) for frame in self.catalog.load_frames(action, self.size)]

    def _render(self) -> None:
        width, height = self.size
        self.root.geometry(f"{width}x{height}")
        self.canvas.configure(width=width, height=height)
        frames = self.images.get(self.model.current.name) or self.images[IDLE]
        self.canvas.itemconfigure(self.sprite, image=frames[self.model.frame_index % len(frames)])

    def _apply_motion(self) -> None:
        self.root.geometry(f"+{int(self.motion.x)}+{int(self.motion.y)}")

    def _start_timers(self) -> None:
        self.scheduler.repeat("animate", self.config.frame_interval_ms, self._animate, group="animation")
        self.scheduler.repeat("chase_poll", CHASE_POLL_MS, self._chase_poll, group="chase")
        if self.config.persist:
            self.scheduler.repeat("autosave", self.config.autosave_interval_ms, self._autosave, group="persistence")
        self.schedule_random_action()

    def _animate(self) -> None:
        frames = self.images.get(self.model.current.name) or self.images[IDLE]
        self.model.next_frame(len(frames))
        self._render()

    def change_scale(self, delta: float) -> None:
        self.scale = self.config.clamp_scale(self.scale + delta)
        self._load_images()
        self._render()
        self.placement = self._measure_placement()
        self.motion = clamp_to_bounds(self.motion, self.placement)
        self._apply_motion()
        self.store.set_setting("scale", f"{self.scale:.2f}")

    def on_wheel(self, event: tk.Event) -> None:
        self.change_scale(0.1 if getattr(event, "delta", 0) > 0 else -0.1)

    def on_hover_enter(self, _event: tk.Event) -> None:
        self.scheduler.schedule(
            "hover_wave",
            self.config.hover_delay_ms,
            lambda: self.play("wave"),
            group="hover",
        )

    def on_hover_leave(self, _event: tk.Event) -> None:
        self.scheduler.cancel_group("hover")

    def on_mouse_down(self, event: tk.Event) -> None:
        self.drag_origin, self.dragged = (event.x, event.y), False
        self.scheduler.cancel_group("hover")
        self._stop_walk()
        self._stop_physics()
        self.drag_tracker.clear()
        self.drag_tracker.add(time.monotonic(), self.root.winfo_x(), self.root.winfo_y())

    def on_mouse_move(self, event: tk.Event) -> None:
        if self.drag_origin is None:
            return
        dx, dy = event.x - self.drag_origin[0], event.y - self.drag_origin[1]
        if abs(dx) + abs(dy) > 3:
            self.dragged = True
        x = self.root.winfo_x() + dx
        y = self.root.winfo_y() + dy
        moved = replace(self.motion, x=float(x), y=float(y), vx=0.0, vy=0.0, grounded=False)
        self.motion = clamp_to_bounds(moved, self.placement)
        self._apply_motion()
        x, y = int(self.motion.x), int(self.motion.y)
        self.drag_tracker.add(time.monotonic(), x, y)
        dragged = self.catalog.resolve("dragged")
        if self.model.current.name != dragged:
            self._set_action(dragged)

    def on_mouse_up(self, _event: tk.Event) -> None:
        was_dragged = self.dragged
        self.drag_origin, self.dragged = None, False
        if was_dragged:
            self._release_throw()
            return
        self.play("click", priority=PRIORITY_USER)
        self.show_dialog(random.choice(self.config.messages))

    def _release_throw(self) -> None:
        """Turn the recorded drag gesture into a velocity and let go."""
        vx, vy = self.drag_tracker.release_velocity(time.monotonic(), self.config.physics)
        self.drag_tracker.clear()
        self.motion = replace(self.motion, vx=vx, vy=vy, grounded=False, airborne_time=0.0)
        verb = "thrown" if math.hypot(vx, vy) >= self.config.physics.throw_threshold else "fall"
        self._play_priority = PRIORITY_IDLE
        self.play(verb, priority=PRIORITY_USER)
        self._ensure_physics()

    def play(self, action: str, *, priority: int = PRIORITY_RANDOM, duration_ms: int | None = None) -> None:
        """Start an action unless a higher-priority one is still running.

        ``idle`` always wins, otherwise the pet could get stuck mid-animation.
        """
        if action == IDLE:
            self._play_priority = PRIORITY_IDLE
        elif priority < self._play_priority:
            return
        else:
            self._play_priority = priority

        self.scheduler.cancel("return_idle")
        self._stop_walk()
        self._set_action(self.catalog.resolve(action))

        if action in WALK_ACTIONS:
            self._begin_walk(action.removeprefix("walk_"))
            return
        if action != IDLE and action not in PHYSICS_ACTIONS:
            self.scheduler.schedule(
                "return_idle",
                duration_ms or self.config.action_duration_ms,
                lambda: self.play(IDLE),
                priority=PRIORITY_IDLE,
                group="action",
            )

    def _set_action(self, action: str) -> None:
        """Switch the displayed animation only. Never moves the pet."""
        self.model.set_action(action, once=action not in LOOPING_ACTIONS)
        self._render()

    def _begin_walk(self, direction: str, plan: MovementPlan | None = None) -> None:
        """Walk a random distance, then stop - or bump into a wall."""
        movement = plan or self.movement_planner.plan(direction)  # type: ignore[arg-type]
        target, will_hit_wall = horizontal_target(
            self.root.winfo_x(), self.size[0], self.root.winfo_screenwidth(), movement
        )
        self.walk_direction = direction
        self.walk_speed = movement.speed_px * (1000.0 / movement.interval_ms)
        self.walk_remaining = abs(target - self.motion.x)
        self.walk_will_hit_wall = will_hit_wall
        self._ensure_physics()

    def _stop_walk(self) -> None:
        self.walk_direction = None
        self.walk_remaining = 0.0
        self.walk_will_hit_wall = False

    def cancel_motion(self) -> None:
        """Stop everything that moves the window, leaving it where it stands."""
        self._stop_walk()
        self._stop_physics()
        self.motion = replace(self.motion, vx=0.0, vy=0.0)

    def _ensure_physics(self) -> None:
        if self.drag_origin is not None or self.scheduler.is_pending("physics_step"):
            return
        self.scheduler.schedule(
            "physics_step", self.config.physics_interval_ms, self._physics_tick, group="physics"
        )

    def _stop_physics(self) -> None:
        self.scheduler.cancel_group("physics")

    def _physics_tick(self) -> None:
        dt = self.config.physics_interval_ms / 1000.0
        drive = self._drive_velocity()
        before_x = self.motion.x
        self.motion, events = step(self.motion, dt, self.placement, self.config.physics, drive_vx=drive)
        self._apply_motion()
        self._handle_motion_events(events, before_x)
        if self._should_keep_physics(drive):
            self.scheduler.schedule(
                "physics_step", self.config.physics_interval_ms, self._physics_tick, group="physics"
            )

    def _drive_velocity(self) -> float | None:
        if self.walk_direction is not None:
            return self.walk_speed if self.walk_direction == "right" else -self.walk_speed
        return self._chase_velocity()

    def _chase_velocity(self) -> float | None:
        if not self.follow_mouse or not self.motion.grounded or self.drag_origin is not None:
            return None
        direction = chase_direction(
            self.motion.x + self.size[0] / 2,
            float(self.root.winfo_pointerx()),
            deadzone=self.config.chase_deadzone_px,
        )
        if direction is None:
            return None
        return self.config.chase_speed_px if direction == "right" else -self.config.chase_speed_px

    def _chase_poll(self) -> None:
        velocity = self._chase_velocity()
        if velocity is None:
            return
        want = "walk_right" if velocity > 0 else "walk_left"
        if self.model.current.name != want:
            self._play_priority = PRIORITY_RANDOM
            self._set_action(self.catalog.resolve(want))
        self._ensure_physics()

    def _should_keep_physics(self, drive: float | None) -> bool:
        if drive is not None or self.walk_direction is not None:
            return True
        return not self.motion.settled()

    def _handle_motion_events(self, events: MotionEvents, before_x: float) -> None:
        if events.landed:
            self._play_priority = PRIORITY_IDLE
            self.play(IDLE)
            return
        if self.walk_direction is None:
            return
        self.walk_remaining -= abs(self.motion.x - before_x)
        if self.walk_remaining <= 0:
            hit_wall = self.walk_will_hit_wall or events.hit_wall
            self._play_priority = PRIORITY_IDLE
            self.play("climb" if hit_wall else IDLE)

    def toggle_follow_mouse(self) -> None:
        self.follow_mouse = bool(self.follow_var.get())
        self.store.set_setting("follow_mouse", "1" if self.follow_mouse else "0")
        if not self.follow_mouse:
            self.play(IDLE)
            self.show_dialog("不跟了。")
            return
        self.show_dialog("跟着你走。")
        self._chase_poll()

    def show_dialog(self, text: str) -> None:
        self.dialog_label.configure(text=text)
        self._place_above(self.dialog)
        self.dialog.deiconify()
        self.scheduler.schedule(
            "hide_dialog", self.config.dialog_duration_ms, self.dialog.withdraw, group="dialog"
        )

    def _place_above(self, window: tk.Toplevel) -> None:
        window.update_idletasks()
        x = int(self.motion.x) + self.size[0] // 2 - window.winfo_width() // 2
        y = max(0, int(self.motion.y) - window.winfo_height() - 6)
        window.geometry(f"+{x}+{y}")

    def schedule_random_action(self) -> None:
        if not self.config.random_actions:
            return
        self.scheduler.schedule(
            "random_action",
            random.randint(*self.config.idle_delay_ms),
            self._random_action,
            priority=PRIORITY_RANDOM,
            group="behavior",
        )

    def _random_action(self) -> None:
        self.state.update_elapsed()
        self._refresh_status()
        if not self.motion.grounded:
            self.schedule_random_action()
            return
        action = self.behavior_engine.choose(self.state)
        chasing = self._chase_velocity() is not None
        if not (chasing and action.animation_name in WALK_ACTIONS):
            self.play(action.animation_name)
        self.speak(DialogueContext(self.state, action=action))
        self.schedule_random_action()

    def request_item(self, item_id: str) -> bool:
        """Menu entry point.

        Refusals (too full, daily quota spent) are answered immediately and
        never reach the scheduler, so the pet reacts even mid-cooldown.
        """
        item = self.items.get(item_id)
        if item is None:
            return False
        used_today = self.store.daily_count(item.id)
        refusal = item.refusal(self.state, used_today)
        if refusal is not None:
            self.speak(DialogueContext(self.state, recovery=refusal))
            return False
        if self.scheduler.cooldown_remaining_ms(f"item:{item.id}") > 0:
            self.speak(DialogueContext(self.state, recovery="wait"))
            return False
        return self.scheduler.schedule(
            f"item:{item_id}",
            0,
            lambda: self.use_item(item),
            priority=PRIORITY_USER,
            group="recovery",
            cooldown_ms=item.cooldown_ms,
        )

    def use_item(self, item: Item) -> ItemOutcome:
        """Apply an item, record the use and narrate the result."""
        outcome = apply_item(item, self.state, self.store.daily_count(item.id))
        if outcome.refusal is not None:
            self.speak(DialogueContext(self.state, recovery=outcome.refusal))
            return outcome
        self.store.bump_daily(item.id)
        self.store.log_event(
            "item",
            {
                "item": item.id,
                "changes": outcome.changes,
                "affection": outcome.affection_gain,
            },
        )
        self.play(item.animation or "happy", priority=PRIORITY_USER)
        if outcome.levelled_up:
            self._announce_level_up(outcome.level_after)
        elif outcome.dialogue_key:
            self.speak(DialogueContext(self.state, recovery=outcome.dialogue_key))
        self._refresh_status()
        return outcome

    def _announce_level_up(self, level: int) -> None:
        template = self.language_provider.reply(DialogueContext(self.state, recovery="level_up"))
        if template:
            self.show_dialog(template.format(title=affection_title(level)))
        self.store.log_event("level_up", {"level": level, "title": affection_title(level)})

    def speak(self, context: DialogueContext) -> str | None:
        """Resolve a template or future LLM response and show it when present."""
        text = self.language_provider.reply(context)
        if text:
            self.show_dialog(text)
        return text

    def show_menu(self, event: tk.Event) -> None:
        self._refresh_item_labels()
        self.menu.post(event.x_root, event.y_root)

    def show_status(self) -> None:
        self._refresh_status()
        self.status_window.deiconify()
        self.status_window.lift()
        self._place_above(self.status_window)
        self.scheduler.repeat("status_refresh", 1_000, self._refresh_status, group="status")

    def hide_status(self) -> None:
        self.scheduler.cancel_group("status")
        self.status_window.withdraw()

    def _stats_snapshot(self) -> dict[str, float]:
        stats = self.state.stats
        return {
            "hunger": stats.hunger,
            "mood": stats.mood,
            "energy": stats.energy,
            "affection": self.state.affection,
        }

    def _refresh_status(self) -> None:
        stats = self.state.stats
        ground = "地面" if self.motion.grounded else "空中"
        remaining = affection_to_next_level(self.state.affection)
        progress = "已满" if remaining <= 0 else f"还差 {remaining:.0f}"
        self.status_text.set(
            f"饱腹度　{100 - stats.hunger:5.1f}\n"
            f"心情　　{stats.mood:5.1f}\n"
            f"精力　　{stats.energy:5.1f}\n"
            f"好感度　{self.state.affection:5.1f}（{self.state.title}·{progress}）\n"
            f"位置　　{int(self.motion.x)}, {int(self.motion.y)}（{ground}）"
        )

    def show_history(self) -> None:
        rows = self.store.recent_events(limit=8)
        if not rows:
            self.show_dialog("还没有记录。")
            return
        lines = []
        for ts, kind, detail in rows:
            stamp = ts[11:16] if len(ts) >= 16 else ts
            suffix = detail if detail and detail != "{}" else ""
            lines.append(f"{stamp} {kind} {suffix}".rstrip())
        self.show_dialog("\n".join(lines))

    def check_assets(self) -> None:
        missing = self.catalog.missing_files()
        if missing:
            messagebox.showwarning("素材检查", "缺少文件：\n" + "\n".join(path.name for path in missing), parent=self.root)
        else:
            messagebox.showinfo("素材检查", "素材完整。", parent=self.root)

    def _autosave(self) -> None:
        self.persist_state()
        self.store.prune_events()

    def persist_state(self) -> None:
        self.state.update_elapsed()
        self.store.save(self.state)
        self.store.set_setting("scale", f"{self.scale:.2f}")
        self.store.set_setting("follow_mouse", "1" if self.follow_mouse else "0")

    def close(self) -> None:
        self.scheduler.cancel_all()
        self.store.log_event("shutdown", self._stats_snapshot())
        self.persist_state()
        self.dialog.destroy()
        self.status_window.destroy()
        self.root.destroy()
