# modules_utils/selenium_helper.py
import os
import shutil
import time
import asyncio
from datetime import datetime
from typing import Dict, Any, List, Optional

from settings.data_files import Files
from log_system.logger_helper import send_to_any_log
from constants.emojis import LogEmojis
from modules_utils.helpers import safe_create_task

class SeleniumHelper:
    """Утилита для настройки Selenium и управления кешем браузера Chromium."""

    @staticmethod
    def get_chrome_options(profile_name: str = "default_profile") -> Any:
        """
        Возвращает настроенные ChromeOptions для Selenium.
        Переносит пути к профилю и кешу в директорию проекта.
        """
        try:
            from selenium.webdriver.chrome.options import Options
        except ImportError:
            # Возвращаем None или обертку, если selenium не установлен, для предотвращения критической ошибки импорта
            return None

        options = Options()
        
        # Основные флаги оптимизации и лимитирования ресурсов
        options.add_argument("--headless=new")  # Запуск в фоновом режиме (Chrome >= 109)
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")
        options.add_argument("--disable-software-rasterizer")
        options.add_argument("--disable-extensions")
        options.add_argument("--mute-audio")
        
        # Определяем директорию для профиля внутри нашего проекта
        user_data_dir = os.path.join(Files.SELENIUM_CACHE_FOLDER, profile_name)
        disk_cache_dir = os.path.join(user_data_dir, "Default", "Cache")
        
        # Указываем Chrome использовать локальную директорию профиля проекта
        options.add_argument(f"--user-data-dir={user_data_dir}")
        options.add_argument(f"--disk-cache-dir={disk_cache_dir}")
        
        # Отключаем лишний мусор и сброс дампов ошибок
        options.add_argument("--disable-logging")
        options.add_argument("--log-level=3")
        options.add_argument("--disable-crash-reporter")
        options.add_argument("--disable-breakpad")

        # Тонкие настройки скрытности (Stealth) и оптимизации трафика
        # 1. Отключаем признак автоматизации (усложняет детекцию со стороны Cloudflare/зашит)
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option("useAutomationExtension", False)

        # 2. Устанавливаем стандартный User-Agent, чтобы выглядеть как реальный пользователь
        options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")

        # 3. Отключаем загрузку картинок для экономии трафика, ускорения загрузки и меньшего расхода RAM
        # Поскольку нам нужен только HTML/JSON контент, картинки нам не требуются!
        chrome_prefs = {
            "profile.managed_default_content_settings.images": 2,
            "profile.default_content_setting_values.notifications": 2
        }
        options.add_experimental_option("prefs", chrome_prefs)
        
        # Автоматическое определение бинарника браузера Chromium/Chrome
        for binary_path in ["/usr/bin/chromium", "/usr/bin/chromium-browser", "/usr/bin/google-chrome"]:
            if os.path.isfile(binary_path):
                options.binary_location = binary_path
                break

        return options

    @staticmethod
    def _fetch_page_http_fallback(url: str) -> Optional[str]:
        """Резервный метод загрузки страницы через HTTP-запрос (urllib), если Selenium недоступен."""
        try:
            import urllib.request
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9,ru;q=0.8"
            }
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=15) as response:
                return response.read().decode("utf-8", errors="ignore")
        except Exception as http_err:
            safe_create_task(send_to_any_log("error", f"SeleniumHelper: HTTP fallback error for {url}: {http_err}", emoji=LogEmojis.ERROR))
            return None

    @staticmethod
    def fetch_page_source(url: str, profile_name: str = "default_profile", wait_time: float = 3.0) -> Optional[str]:
        """
        Блокирующий метод: запускает Chrome через Selenium, загружает страницу,
        ждет wait_time секунд для завершения рендеринга скриптов и возвращает page_source.
        При возникновении ошибки взаимодействия с браузером осуществляет резервный запрос по HTTP.
        """
        driver = None
        try:
            from selenium import webdriver
            from selenium.webdriver.chrome.service import Service

            options = SeleniumHelper.get_chrome_options(profile_name=profile_name)
            if not options:
                return SeleniumHelper._fetch_page_http_fallback(url)
            
            # Попытка поиска существующего файла chromedriver
            chromedriver_path = None
            for path in ["/usr/bin/chromedriver", "/usr/bin/chromium-chromedriver", "/usr/local/bin/chromedriver"]:
                if os.path.isfile(path):
                    chromedriver_path = path
                    break

            if chromedriver_path:
                service = Service(chromedriver_path)
                driver = webdriver.Chrome(service=service, options=options)
            else:
                driver = webdriver.Chrome(options=options)

            driver.set_page_load_timeout(20)
            driver.get(url)
            # Ждем выполнения JS-скриптов и загрузки контента
            time.sleep(wait_time)
            source = driver.page_source
            return source
        except Exception as e:
            safe_create_task(send_to_any_log("warning", f"SeleniumHelper: ошибка при загрузке {url} через Selenium ({e}). Используем резервный HTTP запуск.", emoji=LogEmojis.WARNING))
            return SeleniumHelper._fetch_page_http_fallback(url)
        finally:
            if driver:
                try:
                    driver.quit()
                except Exception:
                    pass

    @staticmethod
    def clean_selenium_cache(max_age_days: int = 30, preserve_essential: bool = True) -> Dict[str, Any]:
        """
        Выполняет очистку кеша Selenium.
        
        :param max_age_days: Очищает файлы, к которым не обращались более этого количества дней.
        :param preserve_essential: Если True, оставляет важные файлы сессий (куки, Local Storage),
                                   удаляя только тяжелый балласт (Cache, ShaderCache, Code Cache).
                                   Если False, удаляет весь профиль полностью.
        :return: Словарь со статистикой очистки.
        """
        stats = {
            "deleted_files_count": 0,
            "deleted_bytes": 0,
            "deleted_dirs_count": 0,
            "errors": []
        }
        
        base_dir = Files.SELENIUM_CACHE_FOLDER
        if not os.path.exists(base_dir):
            return stats

        # Список директорий кеша и ресурсов для избирательного удаления (балласт)
        bloated_dir_names = {
            "Cache",
            "Code Cache",
            "GPUCache",
            "ShaderCache",
            "ScriptCache",
            "CacheStorage",
            "BrowserMetrics",
            "Crash Reports",
            "GrShaderCache",
            "Dictionaries",
            "HTTP Cache"
        }

        now = time.time()
        max_age_sec = max_age_days * 86400

        # Способ 1: Очистка только балласта (оставляя важный кэш / сессии)
        if preserve_essential:
            for root, dirs, files in os.walk(base_dir, topdown=False):
                # 1. Сначала ищем и полностью удаляем папки с тяжелым мусором
                for d in list(dirs):
                    if d in bloated_dir_names:
                        dir_path = os.path.join(root, d)
                        try:
                            # Считаем размер перед удалением
                            dir_size = 0
                            for r_sub, _, f_sub in os.walk(dir_path):
                                for file in f_sub:
                                    try:
                                        file_path = os.path.join(r_sub, file)
                                        dir_size += os.path.getsize(file_path)
                                        stats["deleted_files_count"] += 1
                                    except Exception:
                                        pass
                            
                            shutil.rmtree(dir_path, ignore_errors=True)
                            stats["deleted_bytes"] += dir_size
                            stats["deleted_dirs_count"] += 1
                            dirs.remove(d) # Убираем из обхода, так как удалили
                        except Exception as e:
                            stats["errors"].append(f"Ошибка удаления папки {dir_path}: {e}")

                # 2. Очищаем старые файлы в оставшихся подпапках
                for f in files:
                    # Пропускаем критически важные файлы сессии
                    if f in ("Cookies", "Cookies-journal", "Preferences", "Secure Preferences"):
                        continue
                        
                    file_path = os.path.join(root, f)
                    try:
                        # Если файл старый, удаляем его
                        mtime = os.path.getmtime(file_path)
                        if (now - mtime) > max_age_sec:
                            file_size = os.path.getsize(file_path)
                            os.remove(file_path)
                            stats["deleted_files_count"] += 1
                            stats["deleted_bytes"] += file_size
                    except Exception as e:
                        pass

                # 3. Удаляем пустые директории
                for d in dirs:
                    dir_path = os.path.join(root, d)
                    try:
                        if not os.listdir(dir_path):
                            os.rmdir(dir_path)
                            stats["deleted_dirs_count"] += 1
                    except Exception:
                        pass
        else:
            # Способ 2: Полное удаление папки для стопроцентного сброса
            try:
                for item in os.listdir(base_dir):
                    item_path = os.path.join(base_dir, item)
                    if os.path.isdir(item_path):
                        # Считаем размер перед удалением
                        dir_size = 0
                        for r_sub, _, f_sub in os.walk(item_path):
                            for file in f_sub:
                                try:
                                    dir_size += os.path.getsize(os.path.join(r_sub, file))
                                    stats["deleted_files_count"] += 1
                                except Exception:
                                    pass
                        shutil.rmtree(item_path, ignore_errors=True)
                        stats["deleted_bytes"] += dir_size
                        stats["deleted_dirs_count"] += 1
            except Exception as e:
                stats["errors"].append(f"Ошибка тотальной очистки: {e}")

        return stats

    @staticmethod
    def kill_zombie_processes():
        """Принудительно завершает зависшие процессы Chrome и Chromedriver."""
        import subprocess
        for proc_name in ("chrome", "chromedriver", "chromium"):
            try:
                subprocess.run(["pkill", "-9", "-f", proc_name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except Exception:
                pass

    @classmethod
    async def run_periodic_cleanup_task(cls):
        """Фоновый цикл проверки и очистки кеша Selenium раз в сутки."""
        await send_to_any_log("info", "Запущен фоновый планировщик автоочистки кеша и завершения зомби-процессов Selenium.", emoji=LogEmojis.STARTUP)

        while True:
            try:
                # Первоначально спим 12 часов, затем каждые 24 часа проводим очистку
                await asyncio.sleep(43200)
                
                await send_to_any_log(
                    "info", 
                    "Запуск ежедневной гигиенической очистки Selenium и завершения зомби-процессов...", 
                    emoji=LogEmojis.INFO
                )
                
                # Завершаем зависшие процессы
                await asyncio.to_thread(cls.kill_zombie_processes)
                
                # Выполняем очистку кеша в отдельном потоке (удаляем кеш старше 3 дней)
                stats = await asyncio.to_thread(cls.clean_selenium_cache, max_age_days=3, preserve_essential=True)
                
                size_mb = round(stats["deleted_bytes"] / (1024 * 1024), 2)
                success_msg = (
                    f"Ежедневная очистка Selenium завершена успешно!\n"
                    f"• Удалено временных файлов: {stats['deleted_files_count']}\n"
                    f"• Удалено папок кеша: {stats['deleted_dirs_count']}\n"
                    f"• Освобождено памяти: {size_mb} MB\n"
                    f"• Зависшие процессы Chrome/Chromedriver принудительно завершены."
                )
                await send_to_any_log("info", success_msg, emoji=LogEmojis.INFO)
            except Exception as e:
                await send_to_any_log("error", f"Ошибка в фоновом планировщике очистки Selenium: {e}", emoji=LogEmojis.ERROR)
                await asyncio.sleep(1800)

