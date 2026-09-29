from __future__ import annotations

import argparse
import tkinter as tk

from . import autostart
from .assets import AssetCatalog
from .config import default_config
from .store import SQLiteStateStore
from .window import PetWindow


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Betty Pet desktop companion")
    parser.add_argument("--asset-dir", help="素材目录，默认使用项目 assets/")
    parser.add_argument("--scale", type=float, default=1.0, help="初始缩放比例")
    parser.add_argument("--no-random", action="store_true", help="关闭随机动作")
    parser.add_argument(
        "--sound", dest="sound_enabled", action="store_true", default=None,
        help="本次运行强制开启音效（覆盖存档）",
    )
    parser.add_argument(
        "--no-sound", dest="sound_enabled", action="store_false",
        help="本次运行强制关闭音效（覆盖存档）",
    )
    parser.add_argument("--check-assets", action="store_true", help="检查素材后退出")
    parser.add_argument("--db", help="SQLite 存档路径，默认 ~/.betty_pet/state.db")
    parser.add_argument("--no-persist", action="store_true", help="本次运行不读写存档")
    parser.add_argument("--focus", action="store_true", help="启动后立刻开始一次专注")
    parser.add_argument("--focus-minutes", type=int, help="专注时长（分钟），默认 25")
    parser.add_argument("--status", action="store_true", help="打印存档状态与最近事件后退出")
    parser.add_argument("--autostart-status", action="store_true", help="显示开机自启状态后退出")
    parser.add_argument("--install-autostart", action="store_true", help="安装开机自启（写入「启动」文件夹）")
    parser.add_argument("--uninstall-autostart", action="store_true", help="卸载开机自启")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    # Autostart is handled first: it needs no Tk display and no database, and it
    # is the only command that writes outside the project directory.
    if args.autostart_status:
        return _print_autostart()
    if args.install_autostart:
        return _install_autostart()
    if args.uninstall_autostart:
        return _uninstall_autostart()

    config = default_config(args.asset_dir, db_path=args.db, persist=not args.no_persist)
    config.scale = config.clamp_scale(args.scale)
    config.random_actions = not args.no_random
    config.sound_enabled = args.sound_enabled
    if args.focus_minutes is not None:
        if args.focus_minutes < 1:
            raise SystemExit("--focus-minutes 至少为 1")
        config.focus_minutes = args.focus_minutes

    catalog = AssetCatalog(config.asset_dir)
    missing = catalog.missing_files()
    if args.check_assets:
        if missing:
            for path in missing:
                print(f"missing: {path}")
            return 1
        print(f"ok: {len(catalog.actions())} actions in {config.asset_dir}")
        return 0

    if args.status:
        return _print_status(config)

    if missing:
        raise FileNotFoundError("Missing assets:\n" + "\n".join(str(path) for path in missing))
    root = tk.Tk()
    window = PetWindow(root, config)
    if args.focus:
        # Deferred so the first frame is drawn before the pet sits down.
        root.after(0, window.start_focus)
    root.mainloop()
    return 0


def _print_autostart() -> int:
    path = autostart.target_path()
    print(f"启动文件夹: {autostart.startup_dir()}")
    print(f"启动器:     {path}")
    print("状态:       " + ("已安装" if autostart.is_installed() else "未安装"))
    print("安装:       python main.py --install-autostart")
    print("卸载:       python main.py --uninstall-autostart")
    return 0


def _install_autostart() -> int:
    try:
        path = autostart.install()
    except Exception as error:
        print(f"安装失败: {error}")
        return 1
    print(f"已写入启动器: {path}")
    print("这是本项目唯一会写入项目目录之外的操作，删除该文件即可完全撤销。")
    return 0


def _uninstall_autostart() -> int:
    removed = autostart.uninstall()
    print("已删除启动器。" if removed else "没有找到启动器，无需删除。")
    return 0



def _print_status(config) -> int:
    store = SQLiteStateStore(config.db_path)
    state = store.load()
    state.update_elapsed()
    stats = state.stats
    print(f"存档: {store.db_path}")
    print(f"更新于: {state.last_updated.isoformat(timespec='seconds')}")
    print(f"饱腹度 {100 - stats.hunger:.1f} / 心情 {stats.mood:.1f} / 精力 {stats.energy:.1f}")
    events = store.recent_events(limit=10)
    if not events:
        print("事件: 无")
        return 0
    print("最近事件:")
    for ts, kind, detail in events:
        print(f"  {ts[:19]} {kind} {detail}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
