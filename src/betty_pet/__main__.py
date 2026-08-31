from __future__ import annotations

import argparse
import tkinter as tk

from .assets import AssetCatalog
from .config import default_config
from .window import PetWindow


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Betty Pet desktop companion")
    parser.add_argument("--asset-dir", help="素材目录，默认使用项目 assets/")
    parser.add_argument("--scale", type=float, default=1.0, help="初始缩放比例")
    parser.add_argument("--no-random", action="store_true", help="关闭随机动作")
    parser.add_argument("--check-assets", action="store_true", help="检查素材后退出")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    config = default_config(args.asset_dir)
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
    if missing:
        raise FileNotFoundError("Missing assets:\n" + "\n".join(str(path) for path in missing))
    root = tk.Tk()
    PetWindow(root, config)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

