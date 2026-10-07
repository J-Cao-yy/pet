from __future__ import annotations

import math
import queue
import random
import time
import tkinter as tk
from dataclasses import replace
from datetime import date
from tkinter import Menu, messagebox

from PIL import ImageTk

from .assets import AssetCatalog
from .audio import SilentPlayer, make_sound_player, sound_for_group, sound_for_refusal
from .behavior import (
    DialogueContext,
    TemplateLanguageProvider,
    ThresholdBehaviorEngine,
    default_behavior_rules,
)
from .config import AppConfig
from .desktop import WindowProbe, WindowRect, make_probe, perch_bounds
from .focus import FOCUS, FocusTimer, format_mmss, summarize_focus_events
from .items import GROUP_LABELS, Item, ItemOutcome, apply_item, default_items, items_by_group
from .model import PetModel
from .movement import MovementPlan, MovementPlanner, chase_direction, horizontal_target
from .petting import CLICK, DAILY_KEY, STROKE, PettingRules, evaluate_petting
from .physics import (
    Bounds,
    DragTracker,
    MotionEvents,
    MotionState,
    Surface,
    attach,
    bounds_for,
    clamp_to_bounds,
    detach,
    step,
    surface_bounds,
)
from .scheduler import Scheduler, TkClock
from .state import affection_title, affection_to_next_level
from .store import MemoryStateStore, SQLiteStateStore
from .tray import NullTray, TrayAction, make_tray

IDLE = "idle"
SIT = "sit"
WALK_ACTIONS = ("walk_left", "walk_right")
# Continuous travel: these loop, and they must never be given a return-to-idle
# timer, or a climb would drop back to the resting pose mid-wall.
CLIMB_ACTIONS = ("climb_wall_left", "climb_wall_right", "walk_ceiling")
TRAVEL_ACTIONS = (*WALK_ACTIONS, *CLIMB_ACTIONS)
LOOPING_ACTIONS = frozenset({IDLE, *TRAVEL_ACTIONS})
PHYSICS_ACTIONS = frozenset({"fall", "thrown", "dragged"})
WALL_SURFACES = {"left": Surface.WALL_LEFT, "right": Surface.WALL_RIGHT}

PRIORITY_IDLE = 0
PRIORITY_RANDOM = 1
PRIORITY_USER = 5

CHASE_POLL_MS = 250

# The resting pose while clinging: a held pose per surface, swapped through
# ``_rest_action`` so that every action that ends puts the pet back on the wall.
CLING_REST_ACTIONS = {Surface.WALL_LEFT: "climb", Surface.WALL_RIGHT: "climb", Surface.CEILING: SIT}


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
        # What the pet does when nothing else is happening. Focus sessions swap
        # this to ``sit``, clinging swaps it to a held pose, so the quiet pose
        # survives every action that ends.
        self._rest_action = IDLE
        # Climbing: which way it is travelling along the current surface, how
        # much of this stretch is left, and which way it is leaning *across* a
        # wall band ("hug" = press to the screen edge, "in" = drift towards the
        # screen interior, which ends in a fall once it clears the band).
        self.climb_direction: str | None = None
        self.climb_remaining = 0.0
        self.climb_lean: str | None = None

        # ``self.sound`` always records (tests and the status of what *would*
        # have played); ``self.sound_fx`` actually makes noise where a backend
        # exists (winsound on Windows), gated by the same on/off switch.
        if config.sound_enabled is not None:
            self.sound_enabled = config.sound_enabled
        else:
            self.sound_enabled = (self.store.get_setting("sound") or "0") == "1"
        self.sound = SilentPlayer()
        self.sound_fx = make_sound_player(config.asset_dir / "sounds")

        # Light interactions: when the pet was last poked or stroked, so the
        # affection cooldown has something to measure. None = untouched this run.
        self._last_petting: float | None = None

        # Window perching: the probe reports the foreground window, the pet
        # stands on its top edge. ``_last_window`` remembers the window the user
        # was looking at, because interacting with the pet steals focus.
        self.probe: WindowProbe = make_probe()
        self.perched: WindowRect | None = None
        self._last_window: WindowRect | None = None
        self._perch_surface: Bounds | None = None
        self.hidden = False

        # Focus sessions: the pet goes quiet and sits with the user. Several
        # rounds may run back to back; every Nth break is a long one.
        try:
            saved_sessions = max(0, int(self.store.get_setting("focus_completed_total") or 0))
        except ValueError:  # a hand-edited save must not stop the pet
            saved_sessions = 0
        self.focus_timer = FocusTimer(
            focus_ms=config.focus_minutes * 60_000,
            break_ms=config.focus_break_minutes * 60_000,
            rounds=config.focus_rounds,
            long_break_ms=config.focus_long_break_minutes * 60_000,
            long_break_every=config.focus_long_break_every,
            # A lifetime record that resets on restart is not a record.
            completed_sessions=saved_sessions,
        )

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
                "pet": ("呼噜呼噜。", "蹭蹭你的手。", "再来一下嘛。", "就知道你会来摸我。"),
                "pet_limit": ("今天已经摸够啦，明天再来。", "再摸下去贝蒂要化掉了，明天见。"),
                "level_up": ("好感度提升了！现在是「{title}」。", "我们更熟了一点，已经是「{title}」了。"),
                "focus_start": (
                    "开始 {rounds} 轮专注，每轮 {minutes} 分钟，贝蒂陪着你。",
                    "接下来 {rounds} 轮 × {minutes} 分钟，我在这儿坐着。",
                ),
                "focus_next": ("下一轮，继续。", "还剩 {rounds} 轮，贝蒂在这儿。"),
                "focus_done": ("专注完成，休息一下。", "这一段干得不错。"),
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
        self.tray = self._start_tray()
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

    # -- tray ---------------------------------------------------------------

    def _start_tray(self):
        """A tray icon when the platform allows it, otherwise a silent stand-in.

        A tray that cannot be created must never stop the pet from running, so
        this collapses every failure into :class:`NullTray`.
        """
        tray = make_tray(self._tray_tooltip())
        if not tray.start():
            return NullTray()
        return tray

    def _tray_tooltip(self) -> str:
        chasing = "开" if self.follow_mouse else "关"
        return f"Betty Pet · 跟随鼠标：{chasing}"

    def _drain_tray(self) -> None:
        """Tray thread -> Tk main thread hand-off.

        The tray runs on its own thread and only ever pushes strings onto a
        queue; this job is the single place those become UI mutations. Tkinter
        is not thread-safe, so nothing else may touch it from the tray side.
        """
        if isinstance(self.tray, NullTray):
            return
        while True:
            try:
                action = self.tray.actions.get_nowait()
            except queue.Empty:
                return
            if action == TrayAction.TOGGLE_VISIBLE:
                self.toggle_visible()
            elif action == TrayAction.TOGGLE_FOLLOW:
                self.set_follow_mouse(not self.follow_mouse)
            elif action == TrayAction.QUIT:
                self.close()
                return

    # -- sound --------------------------------------------------------------

    def _play_sound(self, key: str | None) -> None:
        """Fire an effect for ``key`` when sound is on. Never blocks, never raises."""
        if key is None or not self.sound_enabled:
            return
        try:
            self.sound.play(key)
        except Exception:  # pragma: no cover - a broken player must not kill the pet
            pass
        try:
            self.sound_fx.play(key)
        except Exception:  # pragma: no cover - same: decoration must not crash
            pass

    def _record_petting(self, kind: str) -> bool:
        """A poke or a stroke: maybe affection, maybe a reason why not.

        The whole policy (amounts, cooldown, daily cap) lives in
        :func:`evaluate_petting` so tests can pin it without an event loop; this
        method only applies the verdict and narrates it.

        Returns ``True`` when the interaction has been **handled here** - either
        affection was granted, or the daily cap was explained out loud. The
        caller must not stack its own remark on top of an answer this method
        already gave. A cooldown refusal returns ``False`` deliberately: staying
        quiet and falling back to the ordinary reaction is the friendly option,
        and nagging "冷却中" on every poke would be worse than silence.
        """
        if self.focus_timer.active:
            # Focus means still and quiet; poking the cat mid-session would
            # break the very thing the session is for.
            return False
        rules = PettingRules(
            click_affection=self.config.pet_affection_click,
            stroke_affection=self.config.pet_affection_stroke,
            daily_limit=self.config.pet_affection_daily_limit,
            cooldown_s=self.config.pet_affection_cooldown_ms / 1000.0,
        )
        now = time.monotonic()
        seconds_since = None if self._last_petting is None else now - self._last_petting
        decision = evaluate_petting(
            kind,
            used_today=self.store.daily_count(DAILY_KEY),
            seconds_since_last=seconds_since,
            rules=rules,
        )
        if not decision.granted:
            if decision.reason == "limit":
                self._play_sound(sound_for_refusal())
                self.play("refuse", priority=PRIORITY_USER)
                self.speak(DialogueContext(self.state, recovery="pet_limit"))
                return True
            return False

        self._last_petting = now
        self.store.bump_daily(DAILY_KEY)
        before = self.state.level
        self.state.gain_affection(decision.affection)
        self.store.log_event(
            "pet",
            {"kind": kind, "affection": decision.affection, "today": decision.daily_count},
        )
        self._refresh_status()
        if self.state.level > before:
            self._announce_level_up(self.state.level)
        else:
            self.speak(DialogueContext(self.state, recovery="pet"))
        return True

    def _hover_wave(self) -> None:
        self.play("wave")
        self._play_sound("wave")
        # Lingering over the pet is a stroke. A refused stroke (cooldown or the
        # daily cap) just stays a greeting, which is the right quiet fallback.
        self._record_petting(STROKE)

    def toggle_sound(self) -> None:
        self.sound_enabled = bool(self.sound_var.get())
        self.store.set_setting("sound", "1" if self.sound_enabled else "0")
        if self.sound_enabled:
            # Be honest: the switch works, but there is no backend behind it yet.
            self.show_dialog("音效开了，不过还没接播放后端，暂时听不到。")

    # -- window perching ----------------------------------------------------

    def _active_bounds(self) -> Bounds:
        """The surface the pet stands on: a window's top edge, or the floor.

        Perching is nothing more than swapping the physics rectangle, which is
        why gravity, walking along the surface and falling back to the floor
        all keep working without a line of new motion maths.
        """
        if self.perched is None:
            return self.placement
        surface = perch_bounds(self.perched, *self.size, self.placement)
        if surface is None:
            self._leave_perch(fall=True)
            return self.placement
        return surface

    def perch_on_window(self) -> bool:
        """Jump onto the top edge of the window the user was last using."""
        target = self.probe.foreground() or self._last_window
        if target is None:
            self.show_dialog("没找到能站的窗口。")
            return False
        surface = perch_bounds(target, *self.size, self.placement)
        if surface is None:
            self.show_dialog("那个窗口顶上没地方站。")
            return False
        # Coming off a wall first: perching is a floor, and ``surface`` in the
        # motion state would otherwise still say "clinging to the left edge".
        self._let_go()
        self.cancel_motion()
        self.perched = target
        self._last_window = target
        self._perch_surface = surface
        x = min(max(self.motion.x, surface.left), surface.right)
        self.motion = attach(
            replace(self.motion, x=x, y=surface.bottom, vx=0.0, vy=0.0), Surface.FLOOR
        )
        self._sync_rest_action()
        self._apply_motion()
        self._play_priority = PRIORITY_IDLE
        self.play("wave", priority=PRIORITY_USER)
        self._play_sound("perch")
        self.store.log_event("perch", {"title": target.title[:60]})
        self.show_dialog(f"站到「{(target.title or '那个窗口').strip()[:12]}」上面了。")
        return True

    def leave_window(self) -> None:
        """Step off the perch and fall back to the floor."""
        if self.perched is None:
            self.show_dialog("贝蒂没在窗口上。")
            return
        self._leave_perch(fall=True)

    def _leave_perch(self, *, fall: bool) -> None:
        if self.perched is None:
            return
        self.perched = None
        self._perch_surface = None
        self.motion = replace(self.motion, grounded=not fall, vy=0.0)
        if fall:
            self._play_priority = PRIORITY_IDLE
            self.play("fall", priority=PRIORITY_USER)
            self._ensure_physics()

    def _probe_windows(self) -> None:
        """Remember the user's window, and keep the perch in sync with it."""
        current = self.probe.foreground()
        if current is not None:
            self._last_window = current
        if self.perched is None:
            return
        refreshed = self.probe.inspect(self.perched.handle)
        if refreshed is None:
            # Closed, minimised or hidden: the platform is gone.
            self._leave_perch(fall=True)
            return
        surface = perch_bounds(refreshed, *self.size, self.placement)
        if surface is None:
            self._leave_perch(fall=True)
            return
        self.perched = refreshed
        if surface != self._perch_surface:
            # The window moved or was resized under the pet. Wake the physics
            # loop so it follows, instead of floating where the window used to
            # be - and stay idle the rest of the time.
            self._perch_surface = surface
            self._ensure_physics()

    # -- focus sessions -----------------------------------------------------

    def start_focus(self) -> bool:
        """Go quiet and sit with the user for one focus stretch."""
        if not self.focus_timer.start():
            self.show_dialog("已经在专注了。")
            return False
        self._focus_quiet(True)
        self._play_sound("focus_start")
        self.store.log_event(
            "focus_start",
            {
                "minutes": self.config.focus_minutes,
                "rounds": self.config.focus_rounds,
            },
        )
        self.speak(
            DialogueContext(self.state, recovery="focus_start"),
            minutes=self.config.focus_minutes,
            rounds=self.config.focus_rounds,
        )
        self._refresh_status()
        self.scheduler.repeat(
            "focus_tick", self.config.focus_poll_ms, self._focus_tick, group="focus"
        )
        return True

    def stop_focus(self) -> None:
        """End the session early. An abandoned stretch earns no affection."""
        if not self.focus_timer.active:
            self.show_dialog("没有在专注。")
            return
        self.focus_timer.stop()
        self._end_focus()

    def _focus_tick(self) -> None:
        finished = self.focus_timer.tick(self.config.focus_poll_ms)
        if finished is None:
            self._refresh_status()
            return
        if not self.focus_timer.active:
            # The last break of the run just ended - back to normal life.
            self._end_focus()
        elif finished == FOCUS:
            self._complete_focus()
        else:
            # A break rolled into the next round. This is exactly the branch
            # that did not exist when a run was one round: back then every BREAK
            # meant "done", and stopping the tick here killed round two.
            self._play_sound("focus_start")
            self.speak(
                DialogueContext(self.state, recovery="focus_next"),
                rounds=self.focus_timer.rounds_remaining(),
            )
        self._refresh_status()

    def _complete_focus(self) -> None:
        """A full stretch finished - the one affection source that is not an item.

        Only completed stretches count: quitting early must not be worth the
        same as sitting through, or the session is just a button.
        """
        self.store.bump_daily("focus")
        # The lifetime total survives a restart; the daily count does not, and
        # neither should it - that is what makes it a daily count.
        self.store.set_setting("focus_completed_total", str(self.focus_timer.completed_sessions))
        self._play_sound("focus_done")
        self.store.log_event(
            "focus",
            {
                "minutes": self.config.focus_minutes,
                "affection": self.config.focus_affection,
                "rounds_done": self.focus_timer.rounds_done,
                "total": self.focus_timer.completed_sessions,
            },
        )
        before = self.state.level
        self.state.gain_affection(self.config.focus_affection)
        # Celebrating replaces the sit pose, then ``return_idle`` sits back down
        # because the rest pose is still ``sit`` for the following break.
        self.play("happy", priority=PRIORITY_USER)
        self.speak(DialogueContext(self.state, recovery="focus_done"))
        if self.state.level > before:
            self._announce_level_up(self.state.level)
        self._refresh_status()

    def _end_focus(self) -> None:
        self.scheduler.cancel_group("focus")
        self._focus_quiet(False)

    def _focus_quiet(self, quiet: bool) -> None:
        """Focus mode: stop random behaviour and sit still instead of standing.

        The rest pose is the whole trick - every action ends with ``play(idle)``,
        so making that resolve to ``sit`` keeps the pet seated for the full
        stretch without pinning any one animation.
        """
        self._sync_rest_action(sit=quiet)
        if quiet:
            self.scheduler.cancel_group("behavior")
        self.play(IDLE)
        if not quiet:
            self.schedule_random_action()
        self._refresh_status()

    def _sync_rest_action(self, *, sit: bool | None = None) -> None:
        """Recompute the resting pose.

        One variable covers three situations, because every action ends with
        ``play(idle)``: standing on the floor, sitting through a focus session,
        and holding on to a wall or the ceiling. Keeping it in one place is what
        stops one feature from silently clobbering another.
        """
        if sit is None:
            sit = self.focus_timer.active
        if sit:
            self._rest_action = SIT
        elif self.surface.clinging:
            self._rest_action = CLING_REST_ACTIONS[self.surface]
        else:
            self._rest_action = IDLE

    # -- climbing -----------------------------------------------------------

    @property
    def surface(self) -> Surface:
        """The surface the pet is held by right now."""
        return self.motion.surface

    def _effective_bounds(self) -> Bounds:
        """The rectangle the pet may move in, for the surface it is on.

        Standing on the floor (or on a perched window) uses the full rectangle.
        A clinging surface collapses it via :func:`surface_bounds`, so "pinned
        to the wall" needs no new motion code - exactly the same trick perching
        uses, taken one step further.

        The ceiling collapses to a line (walking it means moving *along* it),
        but a wall collapses to a ``climb_band_px`` wide **band**, not a line:
        the pet may shuffle inwards and outwards inside that strip and is only
        clamped at its inner edge. See ``docs/CLIMBING_DESIGN.md`` §7.
        """
        band = 0.0
        if self.surface in WALL_SURFACES.values():
            band = float(self.config.climb_band_px)
        return surface_bounds(self._active_bounds(), self.surface, band=band)

    def climb_wall(self, side: str) -> bool:
        """Grip a screen edge and start climbing from the current height."""
        surface = WALL_SURFACES.get(side)
        if surface is None or self.surface.clinging:
            return False
        self._grip(surface, direction=random.choice(("up", "down")))
        return True

    def climb_ceiling(self) -> bool:
        """Grip the top of the screen and walk along it."""
        if self.surface.clinging:
            return False
        self._grip(Surface.CEILING, direction=random.choice(("left", "right")))
        return True

    def leave_surface(self) -> None:
        """Drop off the wall or ceiling the pet is holding on to."""
        if not self.surface.clinging:
            self.show_dialog("没在墙上。")
            return
        self._let_go()
        self.play(IDLE)
        self._ensure_physics()

    def _grip(self, surface: Surface, *, direction: str | None = None) -> None:
        """Attach to ``surface`` and begin a climb along it."""
        area, reach = self.placement, self.config.wall_reach_px
        if surface in (Surface.WALL_LEFT, Surface.WALL_RIGHT):
            x = area.left if surface is Surface.WALL_LEFT else area.right
            y = min(max(self.motion.y, area.top), area.bottom)
            position = (x, y)
            # Never start out pointing into the end of the surface the pet is
            # already standing at - that would round the corner on frame one.
            if y <= area.top + reach:
                fallback = ("down",)
            elif y >= area.bottom - reach:
                fallback = ("up",)
            else:
                fallback = ("up", "down")
        else:
            x = min(max(self.motion.x, area.left), area.right)
            position = (x, area.top)
            if x <= area.left + reach:
                fallback = ("right",)
            elif x >= area.right - reach:
                fallback = ("left",)
            else:
                fallback = ("left", "right")

        # A perched window is a floor, not a wall: let go of that first, or the
        # pet would be gripping one screen edge and standing on a window at once.
        self._leave_perch(fall=False)
        self.cancel_motion()
        self.motion = attach(replace(self.motion, x=position[0], y=position[1]), surface)
        self.climb_direction = direction or random.choice(fallback)
        self.climb_remaining = float(random.randint(*self.config.climb_distance_px))
        # A wall grip starts pressed against the edge; the ceiling has no
        # "across" axis to lean on.
        self.climb_lean = "hug" if surface.along == "y" else None
        self._sync_rest_action()
        self._apply_motion()
        self._set_climb_animation()
        self._ensure_physics()
        self.store.log_event(
            "surface", {"surface": str(surface), "direction": self.climb_direction}
        )

    def _let_go(self) -> None:
        """Stop clinging. Whatever happens next is ordinary gravity."""
        if not self.surface.clinging:
            return
        released = str(self.surface)
        self.motion = detach(self.motion)
        self.climb_direction = None
        self.climb_remaining = 0.0
        self.climb_lean = None
        self._sync_rest_action()
        self.store.log_event("surface", {"surface": released, "direction": "release"})

    def _climb_animation(self) -> str:
        if self.surface is Surface.CEILING:
            return "walk_ceiling"
        return "climb_wall_left" if self.surface is Surface.WALL_LEFT else "climb_wall_right"

    def _set_climb_animation(self) -> None:
        self._play_priority = PRIORITY_IDLE
        self.play(self._climb_animation(), priority=PRIORITY_RANDOM)

    def _advance_climb(self, before: MotionState) -> None:
        """Spend the current stretch, then turn a corner, peel off, or keep going."""
        if self.climb_direction is None:
            return
        travelled = (
            abs(self.motion.y - before.y)
            if self.surface.along == "y"
            else abs(self.motion.x - before.x)
        )
        self.climb_remaining -= travelled
        # Checked every tick, not only when the distance runs out: otherwise a
        # long stretch would press the pet into the corner forever instead of
        # carrying it onto the next surface.
        if self._reached_corner():
            self._turn_corner()
            return
        # Same reasoning for the inner edge of a wall band - see _peeled_off().
        if self._peeled_off():
            self._peel_off()
            return
        if self.climb_remaining > 0:
            return
        roll = random.random()
        if roll < self.config.climb_release_chance:
            if self.surface.along == "y":
                # Walls fall from where they are, carrying inwards.
                self._peel_off()
            else:
                # The ceiling has no band to drift out of, so it keeps the
                # older "step down to the floor" exit.
                self._drop_to_floor()
        elif self.surface.along == "y" and roll < (
            self.config.climb_release_chance + self.config.climb_lean_chance
        ):
            self._lean_inward()
        else:
            self._pick_new_stretch()

    def _peeled_off(self) -> bool:
        """True when a wall-clinging pet has been pushed out of its band.

        The band's inner edge is a clamp, not a wall, so the pet can never
        literally leave. "It has left the band" therefore has to be read as "it
        is leaning inwards and is already pressed against the inner edge" -
        that is the moment the grip gives.
        """
        if self.surface.along != "y" or self.climb_lean != "in":
            return False
        area, reach, band = (
            self.placement,
            self.config.wall_reach_px,
            self.config.climb_band_px,
        )
        if self.surface is Surface.WALL_LEFT:
            return self.motion.x >= area.left + band - reach
        return self.motion.x <= area.right - band + reach

    def _lean_inward(self) -> None:
        """Start drifting towards the screen interior, still clinging.

        The fall comes later, at the band's inner edge. That gap is the whole
        point of a band: the pet gets to move around on the wall for a while
        before it loses its grip, instead of dropping the instant it leans away.
        """
        self.climb_lean = "in"
        self.climb_remaining = float(random.randint(*self.config.climb_distance_px))

    def _peel_off(self) -> None:
        """Let go of a wall and fall, carrying inwards.

        Unlike :meth:`_drop_to_floor` this does not teleport: the pet keeps the
        height it had and gravity does the rest, which is what "爬出带外才掉落"
        should look like.
        """
        inward = 1.0 if self.surface is Surface.WALL_LEFT else -1.0
        area = self.placement
        self._let_go()
        self.motion = replace(
            self.motion,
            x=min(max(self.motion.x, area.left), area.right),
            vx=inward * self.config.climb_speed_px,
            vy=0.0,
            airborne_time=0.0,
        )
        self._play_priority = PRIORITY_IDLE
        self.play(IDLE)
        self._ensure_physics()

    def _reached_corner(self) -> bool:
        """True when the pet has run into the end of the surface *it is heading for*.

        Direction matters: standing at the bottom of a wall is only "the end"
        when climbing down. Without this, gripping a wall from the floor would
        read as having already arrived and drop the pet straight back down.
        """
        area, reach = self.placement, self.config.wall_reach_px
        if self.surface.along == "y":
            if self.climb_direction == "up":
                return self.motion.y <= area.top + reach
            if self.climb_direction == "down":
                return self.motion.y >= area.bottom - reach
            return False
        if self.climb_direction == "left":
            return self.motion.x <= area.left + reach
        if self.climb_direction == "right":
            return self.motion.x >= area.right - reach
        return False

    def _pick_new_stretch(self) -> None:
        """Keep climbing: new direction along this surface, new distance.

        Reversing is allowed, but never into the corner the pet is standing at -
        that would just round it again on the next tick and turn the climb into
        a jitter.
        """
        area, reach = self.placement, self.config.wall_reach_px
        if self.surface.along == "y":
            choices = ["up", "down"]
            if self.motion.y <= area.top + reach:
                choices = ["down"]
            elif self.motion.y >= area.bottom - reach:
                choices = ["up"]
        else:
            choices = ["left", "right"]
            if self.motion.x <= area.left + reach:
                choices = ["right"]
            elif self.motion.x >= area.right - reach:
                choices = ["left"]
        self.climb_direction = random.choice(choices)
        self.climb_remaining = float(random.randint(*self.config.climb_distance_px))
        # Back to the screen edge: drifting inwards is a separate decision
        # (_lean_inward), not something to keep doing once the stretch is over.
        self.climb_lean = "hug" if self.surface.along == "y" else None
        self._set_climb_animation()

    def _turn_corner(self) -> None:
        """Round a screen corner, or step off at the bottom of a wall."""
        surface, direction = self.surface, self.climb_direction

        if surface in (Surface.WALL_LEFT, Surface.WALL_RIGHT):
            if direction == "up":
                # Crowning the wall: carry on along the ceiling, away from it.
                inward = "right" if surface is Surface.WALL_LEFT else "left"
                self._grip(Surface.CEILING, direction=inward)
            else:
                self._drop_to_floor()
            return

        # On the ceiling, the ends of the screen are the tops of the walls.
        if direction == "left":
            self._grip(Surface.WALL_LEFT, direction="down")
        else:
            self._grip(Surface.WALL_RIGHT, direction="down")

    def _drop_to_floor(self) -> None:
        """Come down off a surface and land. Gravity and walking return."""
        area = self.placement
        self._let_go()
        self.motion = replace(
            self.motion,
            x=min(max(self.motion.x, area.left), area.right),
            y=area.bottom,
            vx=0.0,
            vy=0.0,
            grounded=True,
        )
        self._play_priority = PRIORITY_IDLE
        self.play(IDLE)
        self._play_sound("land")
        self._ensure_physics()

    # -- visibility ---------------------------------------------------------

    def toggle_visible(self) -> None:
        self.show_pet() if self.hidden else self.hide_pet()

    def hide_pet(self) -> None:
        if isinstance(self.tray, NullTray):
            # Without a tray there is no way back, so refuse instead of
            # stranding the pet off-screen.
            self.show_dialog("没有托盘，藏起来就找不回来了。")
            return
        self.hidden = True
        self.hide_status()
        self.dialog.withdraw()
        self.root.withdraw()

    def show_pet(self) -> None:
        self.hidden = False
        self.root.deiconify()

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
        self.sound_var = tk.BooleanVar(value=self.sound_enabled)
        self.menu.add_checkbutton(label="音效", variable=self.sound_var, command=self.toggle_sound)
        self.menu.add_separator()
        self.menu.add_command(label="跳到窗口", command=self.perch_on_window)
        self.menu.add_command(label="离开窗口", command=self.leave_window)
        self.menu.add_separator()
        self.menu.add_command(label="爬左墙", command=lambda: self.climb_wall("left"))
        self.menu.add_command(label="爬右墙", command=lambda: self.climb_wall("right"))
        self.menu.add_command(label="上墙（天花板）", command=self.climb_ceiling)
        self.menu.add_command(label="离开墙面", command=self.leave_surface)
        self.menu.add_separator()
        self.menu.add_command(
            label=f"专注 {self.config.focus_minutes} 分钟", command=self.start_focus
        )
        self.menu.add_command(label="结束专注", command=self.stop_focus)
        self.menu.add_command(label="专注统计", command=self.show_focus_stats)
        self.menu.add_separator()
        self.menu.add_command(label="状态面板", command=self.show_status)
        self.menu.add_command(label="隐藏到托盘", command=self.hide_pet)
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
        if self.probe.available():
            self.scheduler.repeat(
                "window_probe", self.config.perch_poll_ms, self._probe_windows, group="perch"
            )
        if not isinstance(self.tray, NullTray):
            self.scheduler.repeat("tray_poll", self.config.tray_poll_ms, self._drain_tray, group="tray")
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
        if self.focus_timer.active:
            # Focus means still and quiet; a floating mouse is not a greeting.
            return
        self.scheduler.schedule(
            "hover_wave",
            self.config.hover_delay_ms,
            self._hover_wave,
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
            if not self.dragged:
                # Grabbing the pet is how you take it off a window or a wall; a
                # plain click must not detach it.
                self._leave_perch(fall=False)
                self._let_go()
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
        handled = self._record_petting(CLICK)
        self._play_sound("click")
        if handled:
            # The petting policy already answered (affection line, level-up
            # announcement, or the daily-cap refusal); do not talk over it.
            return
        self.show_dialog(random.choice(self.config.messages))

    def _release_throw(self) -> None:
        """Turn the recorded drag gesture into a velocity and let go."""
        vx, vy = self.drag_tracker.release_velocity(time.monotonic(), self.config.physics)
        self.drag_tracker.clear()
        self.motion = replace(
            self.motion, vx=vx, vy=vy, grounded=False, airborne_time=0.0, surface=Surface.FLOOR
        )
        verb = "thrown" if math.hypot(vx, vy) >= self.config.physics.throw_threshold else "fall"
        self._play_priority = PRIORITY_IDLE
        self.play(verb, priority=PRIORITY_USER)
        self._ensure_physics()

    def play(self, action: str, *, priority: int = PRIORITY_RANDOM, duration_ms: int | None = None) -> None:
        """Start an action unless a higher-priority one is still running.

        ``idle`` always wins, otherwise the pet could get stuck mid-animation.
        Its *pose* follows context though: ``self._rest_action`` is what the pet
        does when nothing else is happening (standing, or sitting through a
        focus session).
        """
        resting = action == IDLE
        if resting:
            action = self._rest_action
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
        if not resting and action not in PHYSICS_ACTIONS and action not in LOOPING_ACTIONS:
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
        drive_vx, drive_vy = self._drive_velocity()
        before = self.motion
        self.motion, events = step(
            self.motion,
            dt,
            self._effective_bounds(),
            self.config.physics,
            drive_vx=drive_vx,
            drive_vy=drive_vy,
        )
        self._apply_motion()
        self._handle_motion_events(events, before)
        if self._should_keep_physics(drive_vx, drive_vy):
            self.scheduler.schedule(
                "physics_step", self.config.physics_interval_ms, self._physics_tick, group="physics"
            )

    def _drive_velocity(self) -> tuple[float | None, float | None]:
        """The ``(horizontal, vertical)`` drive for one step.

        A surface lets the pet travel *along* it, so exactly one axis is driven
        for the floor, the ceiling and a plain walk - ``drive_vy`` is the axis
        climbing needs, because on the floor the pet never moves itself
        vertically. Walls are the exception: they are a band, so they drive both
        axes (climb along, lean across).
        """
        if self.drag_origin is not None:
            return None, None
        if self.surface.clinging:
            speed = self.config.climb_speed_px
            vx: float | None = None
            vy: float | None = None
            if self.climb_direction is not None:
                if self.surface.along == "y":
                    vy = speed if self.climb_direction == "down" else -speed
                else:
                    vx = speed if self.climb_direction == "right" else -speed
            # Walls are a band, so they get a second, perpendicular drive: hug
            # the screen edge, or lean inwards until the grip gives.
            if self.climb_lean is not None:
                inward = 1.0 if self.surface is Surface.WALL_LEFT else -1.0
                vx = inward * (-speed if self.climb_lean == "hug" else speed)
            if vx is None and vy is None:
                # Holding on with no input: let the grip friction settle it, so
                # the physics loop can go idle instead of spinning.
                return None, None
            return vx, vy
        if self.walk_direction is not None:
            return (self.walk_speed if self.walk_direction == "right" else -self.walk_speed), None
        return self._chase_velocity(), None

    def _chase_velocity(self) -> float | None:
        if self.focus_timer.active:
            # Focus means sitting still beside the user, not following the mouse.
            return None
        if self.surface.clinging:
            # Chasing is a floor behaviour; a climbing pet already has a job.
            return None
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
        if self.surface.clinging:
            return
        velocity = self._chase_velocity()
        if velocity is None:
            return
        want = "walk_right" if velocity > 0 else "walk_left"
        if self.model.current.name != want:
            self._play_priority = PRIORITY_RANDOM
            self._set_action(self.catalog.resolve(want))
        self._ensure_physics()

    def _should_keep_physics(self, drive_vx: float | None, drive_vy: float | None) -> bool:
        if drive_vx is not None or drive_vy is not None or self.walk_direction is not None:
            return True
        return not self.motion.settled()

    def _handle_motion_events(self, events: MotionEvents, before: MotionState) -> None:
        if self.surface.clinging:
            self._advance_climb(before)
            return
        if events.landed:
            self._play_priority = PRIORITY_IDLE
            self.play(IDLE)
            self._play_sound("land")
            return
        if events.hit_wall and self._grip_adjacent_wall(events):
            return
        if self.walk_direction is None:
            return
        self.walk_remaining -= abs(self.motion.x - before.x)
        if self.walk_remaining <= 0:
            hit_wall = self.walk_will_hit_wall or events.hit_wall
            self._play_priority = PRIORITY_IDLE
            self.play("climb" if hit_wall else IDLE)

    def _grip_adjacent_wall(self, events: MotionEvents) -> bool:
        """Walking into a screen edge grabs it instead of just bumping into it.

        Only from the real floor: while perching, the physics rectangle is the
        *window*, and gripping its edge would drag the pet off onto the screen
        edge behind it.
        """
        if self.perched is not None or not self.motion.grounded:
            return False
        if events.left_wall:
            return self.climb_wall("left")
        if events.right_wall:
            return self.climb_wall("right")
        return False

    def toggle_follow_mouse(self) -> None:
        self.set_follow_mouse(not self.follow_mouse)

    def set_follow_mouse(self, value: bool) -> None:
        """Single entry point for the menu and the tray, so the two never drift."""
        self.follow_mouse = bool(value)
        self.follow_var.set(self.follow_mouse)
        self.store.set_setting("follow_mouse", "1" if self.follow_mouse else "0")
        self.tray.set_tooltip(self._tray_tooltip())
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
        if self.surface.clinging:
            # Climbing is already doing something; a random nap mid-wall would
            # fight the climb for the pose and freeze it in place.
            self.schedule_random_action()
            return
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
            self._play_sound(sound_for_refusal())
            self.play("refuse", priority=PRIORITY_USER)
            self.speak(DialogueContext(self.state, recovery=refusal))
            return False
        if self.scheduler.cooldown_remaining_ms(f"item:{item.id}") > 0:
            self._play_sound(sound_for_refusal())
            self.play("refuse", priority=PRIORITY_USER)
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
        self._play_sound(sound_for_group(item.group))
        if outcome.levelled_up:
            self._announce_level_up(outcome.level_after)
        elif outcome.dialogue_key:
            self.speak(DialogueContext(self.state, recovery=outcome.dialogue_key))
        self._refresh_status()
        return outcome

    def _announce_level_up(self, level: int) -> None:
        self._play_sound("level_up")
        self.play("level_up", priority=PRIORITY_USER)
        self.speak(DialogueContext(self.state, recovery="level_up"), title=affection_title(level))
        self.store.log_event("level_up", {"level": level, "title": affection_title(level)})

    def speak(self, context: DialogueContext, **values) -> str | None:
        """Resolve a template or future LLM response and show it when present.

        ``values`` fills ``{placeholders}`` (e.g. the current title, the chosen
        focus length) so one template tracks a changing setting.
        """
        text = self.language_provider.reply(context)
        if text and values:
            text = text.format(**values)
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
        if self.surface is Surface.CEILING:
            ground = "天花板"
        elif self.surface is Surface.WALL_LEFT:
            ground = "左墙"
        elif self.surface is Surface.WALL_RIGHT:
            ground = "右墙"
        elif self.perched is not None:
            ground = "窗口上"
        elif self.motion.grounded:
            ground = "地面"
        else:
            ground = "空中"
        remaining = affection_to_next_level(self.state.affection)
        progress = "已满" if remaining <= 0 else f"还差 {remaining:.0f}"
        petted_today = self.store.daily_count(DAILY_KEY)
        pet_line = (
            f"轻抚　　今日 {petted_today}/{self.config.pet_affection_daily_limit}\n"
            if self.config.pet_affection_daily_limit > 0
            else ""
        )
        if self.focus_timer.active:
            if self.focus_timer.phase == FOCUS:
                label = f"专注 {self.focus_timer.rounds_done + 1}/{self.focus_timer.rounds}"
            elif self.focus_timer.break_is_long():
                label = "长休"
            else:
                label = "休息"
            focus_line = f"{label}　{format_mmss(self.focus_timer.remaining_ms())}\n"
        else:
            focus_line = ""
        focus_today = self.store.daily_count("focus")
        focus_stats_line = f"专注　　今日 {focus_today} 轮 · 累计 {self.focus_timer.completed_sessions} 轮\n"
        self.status_text.set(
            f"饱腹度　{100 - stats.hunger:5.1f}\n"
            f"心情　　{stats.mood:5.1f}\n"
            f"精力　　{stats.energy:5.1f}\n"
            f"好感度　{self.state.affection:5.1f}（{self.state.title}·{progress}）\n"
            f"{pet_line}"
            f"{focus_line}"
            f"{focus_stats_line}"
            f"音效　　{'开' if self.sound_enabled else '关'}\n"
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

    def show_focus_stats(self) -> None:
        """Today / recent days / lifetime, in plain lines fit for a dialog.

        The per-day breakdown comes from the event log, which is pruned to the
        most recent 500 entries - old days may legitimately read lower than
        they were. The lifetime total comes from the settings table, which
        never forgets.
        """
        summary = summarize_focus_events(
            self.store.recent_events(limit=500),
            today=date.today(),
            days=7,
        )
        lines = [
            f"今日　　{summary.today} 轮",
            f"最近 7 天　{summary.week} 轮",
            f"累计　　{self.focus_timer.completed_sessions} 轮",
        ]
        per_day = "　".join(
            f"{day[5:]} {count}" for day, count in summary.per_day if count
        )
        if per_day:
            lines.append(f"明细　　{per_day}")
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
        self.store.set_setting("sound", "1" if self.sound_enabled else "0")

    def close(self) -> None:
        self.scheduler.cancel_all()
        self.store.log_event("shutdown", self._stats_snapshot())
        self.persist_state()
        self.tray.stop()
        self.dialog.destroy()
        self.status_window.destroy()
        self.root.destroy()
