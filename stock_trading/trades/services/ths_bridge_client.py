from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import tempfile
from typing import Callable

import easytrader
import pywinauto
from pywinauto import Desktop
from easytrader.grid_strategies import Copy, WMCopy, Xls
from PIL import Image
import easytrader.grid_strategies as grid_strategies


def build_user(window_title_keyword: str):
    target = next(
        window
        for window in Desktop(backend="win32").windows()
        if window_title_keyword in (window.window_text() or "")
    )
    user = easytrader.use("ths")
    user._app = pywinauto.Application(backend="win32").connect(handle=target.handle, timeout=10)
    user._main = user._app.window(handle=target.handle)
    user._init_toolbar()
    return user, target


def run_grid_reader(user, reader: Callable[[], list], strategies: list[type], payload_name: str) -> list:
    last_error: Exception | None = None
    original_strategy = getattr(user, "grid_strategy", None)
    original_instance = getattr(user, "_grid_strategy_instance", None)

    for strategy in strategies:
        try:
            user.grid_strategy = strategy
            user._grid_strategy_instance = None
            rows = reader()
            if rows is None:
                raise RuntimeError(f"{payload_name} returned null via {strategy.__name__}")
            return list(rows or [])
        except Exception as exc:
            last_error = exc
            print(
                json.dumps(
                    {
                        "bridge_warning": f"{payload_name} via {strategy.__name__} failed",
                        "error_type": exc.__class__.__name__,
                        "error": str(exc),
                    },
                    ensure_ascii=False,
                ),
                file=sys.stderr,
            )
        finally:
            user.grid_strategy = original_strategy
            user._grid_strategy_instance = None

    if original_instance is not None:
        user._grid_strategy_instance = original_instance

    if last_error is not None:
        raise RuntimeError(f"Unable to read {payload_name} via all strategies") from last_error
    raise RuntimeError(f"Unable to read {payload_name} via all strategies")


def read_today_trades(user) -> list:
    return run_grid_reader(user, lambda: user.today_trades, [WMCopy, Copy, Xls], "today_trades")


def recognize_captcha(img_path: str) -> str:
    try:
        import pytesseract  # type: ignore
    except ModuleNotFoundError:
        pytesseract = None

    image = Image.open(img_path).convert("L")
    threshold = 200
    table = [0 if i < threshold else 1 for i in range(256)]
    binary_image = image.point(table, "1")

    if pytesseract is not None:
        try:
            return pytesseract.image_to_string(binary_image)
        except FileNotFoundError:
            pass

    try:
        import ddddocr  # type: ignore
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "THS captcha recognition requires pytesseract+tesseract or ddddocr in the bridge Python environment."
        ) from exc

    ocr = ddddocr.DdddOcr(show_ad=False)
    with open(img_path, "rb") as handle:
        return ocr.classification(handle.read())


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    grid_strategies.captcha_recognize = recognize_captcha

    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["probe", "today_trades", "positions"], required=True)
    parser.add_argument("--window-title-keyword", default="\u80a1\u7968\u4ea4\u6613\u7cfb\u7edf")
    args = parser.parse_args()

    user, target = build_user(args.window_title_keyword)
    if args.mode == "probe":
        print(json.dumps({"ok": True, "window_title": target.window_text()}, ensure_ascii=False))
        return 0
    if args.mode == "positions":
        positions = list(user.position or [])
        if not positions:
            strategy = Xls(tmp_folder=tempfile.gettempdir())
            strategy.set_trader(user)
            positions = strategy.get(user.config.COMMON_GRID_CONTROL_ID) or []
        print(json.dumps(positions, ensure_ascii=False))
        return 0

    print(json.dumps(read_today_trades(user), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
