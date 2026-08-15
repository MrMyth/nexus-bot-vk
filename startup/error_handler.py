# startup/error_handler.py
# Глобальный обработчик необработанных исключений.
# Использует только stdlib — устанавливается до любых других импортов.
import sys
import time
import traceback


def handle_exception(exc_type, exc_value, exc_traceback):
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return

    # Только stdlib — этот обработчик устанавливается до любых импортов проекта,
    # поэтому не пытаемся импортировать emoji-константы.
    crit = "!!!"
    debug = "[DEBUG]"

    print("\n" + crit * 20)
    print(f"{crit} CRITICAL ERROR ON STARTUP OR EXECUTION:")
    print(crit * 20)
    print(f"Error Type: {exc_type.__name__}")
    print(f"Message: {exc_value}")
    print(f"\n{debug} FULL STACKTRACE:")
    traceback.print_exception(exc_type, exc_value, exc_traceback)
    print(crit * 20)

    print("\n" + "=" * 60)
    print("CONSOLE WINDOW PAUSED FOR DIAGNOSTICS (STARTUP ERROR).")
    print("Press Enter to close this window...")
    print("=" * 60)
    try:
        input()
    except Exception:
        time.sleep(60)


def install_exception_hook():
    """Устанавливает handle_exception как глобальный обработчик исключений."""
    sys.excepthook = handle_exception
