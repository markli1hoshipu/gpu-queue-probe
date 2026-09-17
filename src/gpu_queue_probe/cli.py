from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

from .config import Config
from .controller import Controller


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(prog="gpu-queue-probe")
    result.add_argument("--config", default="config/local.json")
    sub = result.add_subparsers(dest="command", required=True)
    sub.add_parser("run", help="Run the continuous controller")
    sub.add_parser("once", help="Run one reconciliation and publication cycle")
    sub.add_parser("status", help="Print the most recent local snapshot")
    sub.add_parser("cancel", help="Cancel only tracked probe jobs")
    return result


def main() -> None:
    args = parser().parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    config_path = Path(args.config).resolve()
    config = Config.load(config_path)
    root = config_path.parent.parent
    controller = Controller(config, root)
    if args.command == "run":
        controller.run_forever()
    elif args.command == "once":
        controller.reconcile()
        controller.maybe_publish(force=True)
    elif args.command == "status":
        print((config.state_dir / "latest.json").read_text(encoding="utf-8"))
    elif args.command == "cancel":
        controller.cancel_owned()


if __name__ == "__main__":
    main()
