#!/usr/bin/env python
import os
import sys
from pathlib import Path


def main() -> None:
    current_dir = Path(__file__).resolve().parent
    project_root = current_dir.parent
    sys.path.insert(0, str(project_root))
    sys.path.insert(0, str(current_dir))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "stock_trading.config.settings")
    from django.core.management import execute_from_command_line

    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
