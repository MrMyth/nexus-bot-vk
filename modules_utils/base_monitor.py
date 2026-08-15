# modules_utils/base_monitor.py
# Общий абстрактный базовый класс для всех мониторов (постов и стримов).
#
# Выносит общие поля и жизненный цикл в одно место, устраняя дублирование между
# GroupMonitor (vk_wall) и BaseStreamMonitor (все платформенные стрим-мониторы).
from abc import ABC, abstractmethod
from typing import Optional
import aiohttp


class BaseMonitor(ABC):
    """Общий базовый класс для мониторов.

    Содержит:
    - стандартные поля идентификации и состояния,
    - счётчики статистики,
    - протокол start() / stop().

    Детали алгоритма проверки (circuit breaker, adaptive polling, fetch-логика)
    реализуются в подклассах, т.к. механизмы существенно различаются для постов и стримов.
    """

    def __init__(self, platform_name: str, platform_id: str, discord_bot):
        self.platform_name: str = platform_name
        self.platform_id: str = str(platform_id)
        self.discord_bot = discord_bot

        # Состояние жизненного цикла
        self.is_running: bool = False
        self.session: Optional[aiohttp.ClientSession] = None

        # Статистика
        self.last_check_time = None    # datetime | None
        self.last_success_time = None  # datetime | None
        self.processed_count: int = 0
        self.error_count: int = 0

    @abstractmethod
    async def start(self):
        """Запускает мониторинг. Реализуется в подклассе."""
        ...

    async def stop(self):
        """Штатная остановка монитора."""
        self.is_running = False
