# start.py — точка входа
# Этот файл — тонкий оркестратор; бизнес-логика — в пакете startup/.
#
# Порядок шагов важен:
#   1. Обработчик исключений (только stdlib, должен быть первым)
#   2. Проверка/установка зависимостей (только stdlib)
#   3. Настройка sys.path, консоли, загрузка .env
#   4. Monkey-patches для discord.py (после discord-импорта, до проектных импортов)
#   5. Запуск
import os
import sys
import time  # noqa: F401 — используется в startup/runner.py через импорт

# 0. Настройка sys.path (должно быть до импорта startup)
project_root = os.path.dirname(os.path.abspath(__file__))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# 1. Глобальный обработчик исключений
from startup.error_handler import install_exception_hook
install_exception_hook()

# 2. Авто-проверка зависимостей
from startup.deps import check_and_install_deps
check_and_install_deps()

if os.name == "nt":
    import ctypes
    ctypes.windll.kernel32.SetConsoleTitleW("Nexus Bot (Main Process)")

from dotenv import load_dotenv  # noqa: E402 — после dep check
env_path = os.path.join(project_root, '.env')
if os.path.exists(env_path):
    load_dotenv(env_path)

# 4. Monkey-patches (side-effects при импорте; должны быть до импортов проекта)
import startup.patches  # noqa: F401, E402

# 5. Запуск
if __name__ == "__main__":
    from startup.runner import run_forever
    run_forever(project_root)
