from __future__ import annotations

import random
import tkinter as tk
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
from .model import PetModel
from .state import PetState, RecoveryMethod, RecoveryResult


class PetWindow:
    """Tkinter presentation layer for the desktop pet."""

    TRANSPARENT = "#ff00ff"

    def __init__(self, root: tk.Tk, config: AppConfig) -> None:
        self.root, self.config = root, config
        self.catalog = AssetCatalog(config.asset_dir)
        self.model = PetModel(self.catalog.actions())
        self.state = PetState()
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
            }
        )
        self.scale = config.clamp_scale(config.scale)
        self.drag_origin: tuple[int, int] | None = None
        self.dragged = False

        root.overrideredirect(True)
        root.attributes("-topmost", True)
        root.attributes("-transparentcolor", self.TRANSPARENT)
        root.configure(bg=self.TRANSPARENT)
        self.canvas = tk.Canvas(root, bg=self.TRANSPARENT, highlightthickness=0)
        self.canvas.pack()
        self.sprite = self.canvas.create_image(0, 0, anchor="nw")

        self.dialog = tk.Toplevel(root)
        self.dialog.withdraw()
        self.dialog.overrideredirect(True)
        self.dialog.attributes("-topmost", True)
        self.dialog_label = tk.Label(self.dialog, bg="white", fg="#222222", font=("Microsoft YaHei UI", 10), relief="solid", bd=1, padx=8, pady=4)
        self.dialog_label.pack()

        self.menu = Menu(root, tearoff=0)
        self.menu.add_command(label="放大", command=lambda: self.change_scale(0.1))
        self.menu.add_command(label="缩小", command=lambda: self.change_scale(-0.1))
        self.menu.add_separator()
        self.menu.add_command(label="检查素材", command=self.check_assets)
        self.menu.add_command(label="退出", command=self.close)

        self.canvas.bind("<ButtonPress-1>", self.on_mouse_down)
        self.canvas.bind("<B1-Motion>", self.on_mouse_move)
        self.canvas.bind("<ButtonRelease-1>", self.on_mouse_up)
        self.canvas.bind("<Button-3>", self.show_menu)
        self.canvas.bind("<MouseWheel>", self.on_wheel)
        self.canvas.bind("<Button-4>", lambda _event: self.change_scale(0.1))
        self.canvas.bind("<Button-5>", lambda _event: self.change_scale(-0.1))
        self.root.protocol("WM_DELETE_WINDOW", self.close)

        self._load_images()
        self._render()
        self._animate()
        self.schedule_random_action()

    @property
    def size(self) -> tuple[int, int]:
        edge = int(self.config.base_size * self.scale)
        return edge, edge

    def _load_images(self) -> None:
        self.images: dict[str, list[ImageTk.PhotoImage]] = {}
        for action in self.catalog.actions():
            self.images[action] = [ImageTk.PhotoImage(frame) for frame in self.catalog.load_frames(action, self.size)]

    def _render(self) -> None:
        width, height = self.size
        self.root.geometry(f"{width}x{height}")
        self.canvas.configure(width=width, height=height)
        frames = self.images.get(self.model.current.name) or self.images["idle"]
        self.canvas.itemconfigure(self.sprite, image=frames[self.model.frame_index % len(frames)])

    def _animate(self) -> None:
        frames = self.images.get(self.model.current.name) or self.images["idle"]
        self.model.next_frame(len(frames))
        self._render()
        self.root.after(180, self._animate)

    def change_scale(self, delta: float) -> None:
        self.scale = self.config.clamp_scale(self.scale + delta)
        self._load_images()
        self._render()

    def on_wheel(self, event: tk.Event) -> None:
        self.change_scale(0.1 if getattr(event, "delta", 0) > 0 else -0.1)

    def on_mouse_down(self, event: tk.Event) -> None:
        self.drag_origin, self.dragged = (event.x, event.y), False

    def on_mouse_move(self, event: tk.Event) -> None:
        if self.drag_origin is None:
            return
        dx, dy = event.x - self.drag_origin[0], event.y - self.drag_origin[1]
        if abs(dx) + abs(dy) > 3:
            self.dragged = True
        self.root.geometry(f"+{self.root.winfo_x() + dx}+{self.root.winfo_y() + dy}")

    def on_mouse_up(self, _event: tk.Event) -> None:
        was_dragged = self.dragged
        self.drag_origin, self.dragged = None, False
        if not was_dragged:
            self.play("click")
            self.show_dialog(random.choice(self.config.messages))

    def play(self, action: str) -> None:
        self.model.set_action(action, once=action != "idle")
        self._render()
        if action != "idle":
            self.root.after(self.config.action_duration_ms, lambda: self.play("idle"))

    def show_dialog(self, text: str) -> None:
        self.dialog_label.configure(text=text)
        self.dialog.update_idletasks()
        x = self.root.winfo_x() + self.size[0] // 2 - self.dialog.winfo_width() // 2
        y = max(0, self.root.winfo_y() - self.dialog.winfo_height() - 6)
        self.dialog.geometry(f"+{x}+{y}")
        self.dialog.deiconify()
        self.root.after(self.config.dialog_duration_ms, self.dialog.withdraw)

    def schedule_random_action(self) -> None:
        if self.config.random_actions:
            self.root.after(random.randint(*self.config.idle_delay_ms), self._random_action)

    def _random_action(self) -> None:
        self.state.update_elapsed()
        action = self.behavior_engine.choose(self.state)
        self.play(action.animation_name)
        self.speak(DialogueContext(self.state, action=action))
        self.schedule_random_action()

    def recover(self, method: RecoveryMethod) -> RecoveryResult:
        """Apply food/rest/toy effects; UI controls can call this method."""
        result = method.apply(self.state)
        if result.dialogue_key:
            self.speak(DialogueContext(self.state, recovery=result.dialogue_key))
        return result

    def speak(self, context: DialogueContext) -> str | None:
        """Resolve a template or future LLM response and show it when present."""
        text = self.language_provider.reply(context)
        if text:
            self.show_dialog(text)
        return text

    def show_menu(self, event: tk.Event) -> None:
        self.menu.post(event.x_root, event.y_root)

    def check_assets(self) -> None:
        missing = self.catalog.missing_files()
        if missing:
            messagebox.showwarning("素材检查", "缺少文件：\n" + "\n".join(path.name for path in missing), parent=self.root)
        else:
            messagebox.showinfo("素材检查", "素材完整。", parent=self.root)

    def close(self) -> None:
        self.dialog.destroy()
        self.root.destroy()
