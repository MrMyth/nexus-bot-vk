# modules_utils/stats_manager.py
import time
from datetime import datetime
from typing import Dict, Any

class StatsManager:
    def __init__(self):
        self.start_time = time.time()
        self.processed_posts = 0
        self.processed_streams = 0
        self.processed_videos = 0
        self.processed_assets = 0
        self.errors = 0
        self.active_monitors = 0
        self.platform_stats: Dict[str, int] = {}
        self.total_processing_time = 0.0
        self.processing_time_count = 0
        self.circuit_breakers_triggered = 0

    def reset(self):
        self.start_time = time.time()
        self.processed_posts = 0
        self.processed_streams = 0
        self.processed_videos = 0
        self.processed_assets = 0
        self.errors = 0
        self.active_monitors = 0
        self.platform_stats.clear()
        self.total_processing_time = 0.0
        self.processing_time_count = 0
        self.circuit_breakers_triggered = 0

    # Максимальное число уникальных ключей в platform_stats.
    # Ограничивает медленную утечку памяти при необычно большом наборе платформ/типов.
    _MAX_PLATFORM_KEYS = 100

    def _increment_platform_stat(self, key: str) -> None:
        """Безопасно увеличивает счётчик ключа, не давая словарю расти бесконечно."""
        if key in self.platform_stats:
            self.platform_stats[key] += 1
        elif len(self.platform_stats) < self._MAX_PLATFORM_KEYS:
            self.platform_stats[key] = 1
        # else: новый ключ сверх лимита молча игнорируется

    def log_post(self, platform: str = "vk_wall"):
        self.processed_posts += 1
        self._increment_platform_stat(platform)

    def log_processing_time(self, duration: float):
        self.total_processing_time += duration
        self.processing_time_count += 1

    def log_circuit_breaker(self):
        self.circuit_breakers_triggered += 1

    def log_stream(self, platform: str):
        self.processed_streams += 1
        self._increment_platform_stat(platform)

    def log_video(self, platform: str):
        self.processed_videos += 1
        self._increment_platform_stat(platform)

    def log_asset(self, asset_type: str):
        self.processed_assets += 1
        self._increment_platform_stat(f"asset_{asset_type}")

    def log_error(self):
        self.errors += 1

    def set_active_monitors(self, count: int):
        self.active_monitors = count

    def get_stats(self) -> Dict[str, Any]:
        uptime_seconds = int(time.time() - self.start_time)
        days, rem = divmod(uptime_seconds, 86400)
        hours, rem = divmod(rem, 3600)
        minutes, seconds = divmod(rem, 60)
        
        uptime_str = f"{int(days)}d {int(hours)}h {int(minutes)}m {int(seconds)}s"

        # Пытаемся получить размер очереди из бота
        queue_size = 0
        try:
            from clients.bot_instance import bot
            if (bot is not None
                    and hasattr(bot, 'app')
                    and hasattr(bot.app, 'discord_bot')
                    and hasattr(bot.app.discord_bot, '_message_queue')):
                queue_size = bot.app.discord_bot._message_queue.qsize()
        except Exception:
            pass

        avg_time = self.total_processing_time / self.processing_time_count if self.processing_time_count > 0 else 0.0

        return {
            "uptime": uptime_str,
            "processed_posts": self.processed_posts,
            "processed_streams": self.processed_streams,
            "processed_videos": self.processed_videos,
            "processed_assets": self.processed_assets,
            "errors": self.errors,
            "active_monitors": self.active_monitors,
            "platform_breakdown": self.platform_stats,
            "queue_size": queue_size,
            "start_time": datetime.fromtimestamp(self.start_time).strftime("%Y-%m-%d %H:%M:%S"),
            "avg_processing_time": avg_time,
            "circuit_breakers_triggered": self.circuit_breakers_triggered
        }

# Global instance
stats_manager = StatsManager()
