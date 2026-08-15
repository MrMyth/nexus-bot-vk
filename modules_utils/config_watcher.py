# modules_utils/config_watcher.py
import os
import asyncio
import time
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from log_system.logger_helper import send_to_any_log
from constants.emojis import LogEmojis
from modules_utils.helpers import safe_create_task

class ConfigHandler(FileSystemEventHandler):
    def __init__(self, reload_callback, loop, allowed_extensions=('.json',)):
        self.reload_callback = reload_callback
        self.loop = loop
        self.allowed_extensions = allowed_extensions
        self.last_reload_times = {}

    def _should_trigger(self, path: str) -> bool:
        """Проверяет кулдаун в 1 секунду для предотвращения множественного срабатывания на одно сохранение."""
        now = time.time()
        last_time = self.last_reload_times.get(path, 0.0)
        if now - last_time < 1.0:
            return False
        self.last_reload_times[path] = now
        return True

    def on_modified(self, event):
        if not event.is_directory and any(event.src_path.endswith(ext) for ext in self.allowed_extensions):
            if self._should_trigger(event.src_path):
                asyncio.run_coroutine_threadsafe(self.reload_callback(), self.loop)

    def on_created(self, event):
        if not event.is_directory and any(event.src_path.endswith(ext) for ext in self.allowed_extensions):
            if self._should_trigger(event.src_path):
                asyncio.run_coroutine_threadsafe(self.reload_callback(), self.loop)

    def on_deleted(self, event):
        if not event.is_directory and any(event.src_path.endswith(ext) for ext in self.allowed_extensions):
            if self._should_trigger(event.src_path):
                asyncio.run_coroutine_threadsafe(self.reload_callback(), self.loop)

class ConfigWatcher:
    def __init__(self):
        self.observer = Observer()
        self._started = False

    def watch_directory(self, path, reload_callback, allowed_extensions=('.json',)):
        if not os.path.exists(path):
            os.makedirs(path, exist_ok=True)
        
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = asyncio.get_event_loop()
            
        handler = ConfigHandler(reload_callback, loop, allowed_extensions)
        self.observer.schedule(handler, path, recursive=False)
        safe_create_task(send_to_any_log("info", f"ConfigWatcher: отслеживание папки: {path} для {allowed_extensions}", emoji=LogEmojis.INFO))

    def start(self):
        if not self._started:
            self.observer.start()
            self._started = True

    def stop(self):
        if self._started:
            try:
                self.observer.stop()
                if self.observer.is_alive():
                    self.observer.join(timeout=2)
            except Exception as e:
                safe_create_task(send_to_any_log("error", f"ConfigWatcher: ошибка при остановке: {e}", emoji=LogEmojis.ERROR))
            self._started = False
