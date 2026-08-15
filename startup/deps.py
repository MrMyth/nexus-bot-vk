# startup/deps.py
# Авто-проверка и установка зависимостей до любых импортов проекта.
# Использует только stdlib.
import os
import sys
import subprocess


def check_and_install_deps():
    """Checks for critical dependencies and launches pip installer if missing."""
    try:
        import discord  # noqa: F401
        import aiohttp  # noqa: F401
        import dotenv  # noqa: F401
        import aiosqlite  # noqa: F401
        import psutil  # noqa: F401
        import watchdog  # noqa: F401
    except ImportError:
        print("[AUTOPREP] Some required dependencies are missing (discord, aiohttp, dotenv, aiosqlite, psutil, watchdog).")
        print("[AUTOPREP] Installing dependencies from requirements.txt...")
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        req_file = os.path.join(project_root, "requirements.txt")
        if os.path.exists(req_file):
            try:
                subprocess.run(
                    [sys.executable, "-m", "pip", "install", "--break-system-packages", "-r", req_file],
                    check=False
                )
            except Exception as e:
                print(f"[AUTOPREP] Error installing packages via pip: {e}", file=sys.stderr)
        else:
            print(f"[AUTOPREP] Error: requirements.txt not found at: {req_file}", file=sys.stderr)
