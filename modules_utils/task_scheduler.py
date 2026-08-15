# modules_utils/task_scheduler.py
import asyncio
from typing import List, Dict, Any, Callable, Coroutine, Optional
try:
    from log_system.logger_helper import send_to_any_log
except ModuleNotFoundError:
    import sys
    import os
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from log_system.logger_helper import send_to_any_log
from constants.emojis import LogEmojis
from settings.config import Config
from modules_utils.helpers import safe_create_task

class TaskScheduler:
    """Centralized task scheduler for monitors."""
    
    def __init__(self):
        self.tasks: Dict[str, asyncio.Task] = {}
        # NOTE: semaphore and lock are created lazily (see _get_semaphore/_get_add_lock),
        # as asyncio.Semaphore/Lock bind to the event loop on first use.
        self._semaphore: Optional[asyncio.Semaphore] = None
        self._semaphore_loop: Optional[asyncio.AbstractEventLoop] = None
        self._add_lock: Optional[asyncio.Lock] = None
        self._add_lock_loop: Optional[asyncio.AbstractEventLoop] = None

    def _get_add_lock(self) -> asyncio.Lock:
        loop = asyncio.get_running_loop()
        if self._add_lock is None or self._add_lock_loop is not loop:
            self._add_lock = asyncio.Lock()
            self._add_lock_loop = loop
        return self._add_lock

    async def add_monitor(self, monitor_name: str, start_coro: Coroutine):
        """Adds a monitor and starts its task (atomically)."""
        async with self._get_add_lock():
            if monitor_name in self.tasks:
                await self.remove_monitor(monitor_name)

            task = safe_create_task(start_coro)
            if task:
                task.set_name(monitor_name)
                self.tasks[monitor_name] = task

                def on_task_done(t):
                    try:
                        name = t.get_name()
                        if t.cancelled():
                            pass
                        elif t.exception():
                            exc = t.exception()
                            safe_create_task(send_to_any_log("critical", f"CRITICAL TASK FAILURE {name}: {exc}", emoji=LogEmojis.CRITICAL))
                        else:
                            safe_create_task(send_to_any_log("warning", f"Task {name} unexpectedly finished without error", emoji=LogEmojis.WARNING))
                    except Exception:
                        pass

                task.add_done_callback(on_task_done)

    async def remove_monitor(self, monitor_name: str):
        """Stops and removes a task by name."""
        if monitor_name in self.tasks:
            task = self.tasks[monitor_name]
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            del self.tasks[monitor_name]

    def get_check_lock(self):
        """Gets semaphore to limit concurrent heavy operations (API requests)."""
        loop = asyncio.get_running_loop()
        if self._semaphore is None or self._semaphore_loop is not loop:
            self._semaphore = asyncio.Semaphore(15)  # Limit of concurrently active checks
            self._semaphore_loop = loop
        return self._semaphore

    async def stop_all(self):
        """Stops all running tasks."""
        for name, task in self.tasks.items():
            task.cancel()
            await send_to_any_log("info", f"Stopping task: {name}", emoji=LogEmojis.INFO)
        
        if self.tasks:
            await asyncio.gather(*self.tasks.values(), return_exceptions=True)
        
        self.tasks.clear()
        await send_to_any_log("info", "All scheduler tasks stopped", emoji=LogEmojis.INFO)

# Global scheduler instance
scheduler = TaskScheduler()
