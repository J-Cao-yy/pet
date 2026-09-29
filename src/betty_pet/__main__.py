from __future__ import annotations

import argparse
import tkinter as tk

from .assets import AssetCatalog
from .config import default_config
from .store import SQLiteStateStore
from .window import PetWindow


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Betty Pet desktop companion")
    parser.add_argument("--asset-dir", help="素材目录，默认使用项目 assets/")
    parser.add_argument("--scale", type=float, default=1.0, help="初始缩放比例")
    parser.add_argument("--no-random", action="store_true", help="关闭随机动作")
    parser.add_argument("--check-assets", action="store_true", help="检查素材后退出")
    parser.add_argument("--db", help="SQLite 存档路径，默认 ~/.betty_pet/state.db")
    parser.add_argument("--no-persist", action="store_true", help="本次运行不读写存档")
    parser.add_argument("--status", action="store_true", help="打印存档状态与最近事件后退出")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    config = default_config(args.asset_dir, db_path=args.db, persist=not args.no_persist)
    config.scale = config.clamp_scale(args.scale)
    config.random_actions = not args.no_random

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
    PetWindow(root, config)
    root.mainloop()
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
