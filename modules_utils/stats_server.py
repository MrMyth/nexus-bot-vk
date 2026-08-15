# modules_utils/stats_server.py
import asyncio
import os
import json
from typing import Optional
from aiohttp import web

HTML_DASHBOARD = """<!DOCTYPE html>
<html lang="ru">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Nexus Discord Bot — Панель управления</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
  <style>
    body { font-family: 'Plus Jakarta Sans', sans-serif; }
    code, pre { font-family: 'JetBrains Mono', monospace; }
  </style>
</head>
<body class="bg-slate-950 text-slate-100 min-h-screen antialiased selection:bg-indigo-500 selection:text-white">
  <div class="max-w-6xl mx-auto px-4 py-8 md:py-12">
    <!-- Header -->
    <header class="flex flex-col md:flex-row md:items-center justify-between pb-8 mb-8 border-b border-slate-800 gap-4">
      <div class="flex items-center gap-4">
        <div class="w-12 h-12 rounded-xl bg-indigo-600/20 border border-indigo-500/30 flex items-center justify-center text-2xl shadow-inner">
          🤖
        </div>
        <div>
          <div class="flex items-center gap-3">
            <h1 class="text-2xl font-bold tracking-tight text-white">Nexus Discord Bot</h1>
            <span class="px-2.5 py-0.5 text-xs font-semibold rounded-full bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 flex items-center gap-1.5">
              <span class="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse"></span>
              Сервер активен
            </span>
          </div>
          <p class="text-sm text-slate-400 mt-1">Multi-Source Monitoring, Trello & PDF Sync, Protection & Analytics</p>
        </div>
      </div>
      <div class="flex items-center gap-3">
        <a href="/api/stats" target="_blank" class="px-4 py-2 text-xs font-semibold rounded-lg bg-slate-800/80 hover:bg-slate-800 text-slate-200 border border-slate-700 transition">
          JSON API
        </a>
        <a href="/health" target="_blank" class="px-4 py-2 text-xs font-semibold rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white transition">
          Health Check
        </a>
      </div>
    </header>

    <!-- Metrics Grid -->
    <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
      <div class="p-5 rounded-2xl bg-slate-900/60 border border-slate-800/80">
        <div class="text-xs font-medium text-slate-400 uppercase tracking-wider mb-2">Время работы</div>
        <div class="text-2xl font-bold text-white tracking-tight" id="uptime-display">--</div>
        <div class="text-xs text-slate-500 mt-2 flex items-center gap-1">
          <span class="text-indigo-400">⏱️</span> С момента запуска
        </div>
      </div>
      <div class="p-5 rounded-2xl bg-slate-900/60 border border-slate-800/80">
        <div class="text-xs font-medium text-slate-400 uppercase tracking-wider mb-2">Обработано постов</div>
        <div class="text-2xl font-bold text-indigo-400 tracking-tight" id="posts-count">0</div>
        <div class="text-xs text-slate-500 mt-2 flex items-center gap-1">
          <span>📝</span> VK Wall & Telegram
        </div>
      </div>
      <div class="p-5 rounded-2xl bg-slate-900/60 border border-slate-800/80">
        <div class="text-xs font-medium text-slate-400 uppercase tracking-wider mb-2">Стримы и видео</div>
        <div class="text-2xl font-bold text-violet-400 tracking-tight" id="streams-count">0</div>
        <div class="text-xs text-slate-500 mt-2 flex items-center gap-1">
          <span>📡</span> Multi-Platform Live
        </div>
      </div>
      <div class="p-5 rounded-2xl bg-slate-900/60 border border-slate-800/80">
        <div class="text-xs font-medium text-slate-400 uppercase tracking-wider mb-2">Очередь сообщений</div>
        <div class="text-2xl font-bold text-emerald-400 tracking-tight" id="queue-count">0</div>
        <div class="text-xs text-slate-500 mt-2 flex items-center gap-1">
          <span>⚡</span> Задержек нет
        </div>
      </div>
    </div>

    <!-- Main Content Layout -->
    <div class="grid grid-cols-1 lg:grid-cols-3 gap-8">
      <!-- Left Column: Active Modules & Status -->
      <div class="lg:col-span-2 space-y-6">
        <div class="p-6 rounded-2xl bg-slate-900/60 border border-slate-800/80">
          <h2 class="text-base font-semibold text-white mb-4 flex items-center gap-2">
            <span>🛠️</span> Поддерживаемые модули мониторинга
          </h2>
          <div class="grid grid-cols-1 sm:grid-cols-2 gap-3 text-sm">
            <div class="p-3 rounded-xl bg-slate-950/60 border border-slate-800/60 flex items-center justify-between">
              <span class="flex items-center gap-2"><span>🔴</span> VK Wall & Live</span>
              <span class="text-xs text-emerald-400 font-medium">Готов</span>
            </div>
            <div class="p-3 rounded-xl bg-slate-950/60 border border-slate-800/60 flex items-center justify-between">
              <span class="flex items-center gap-2"><span>📹</span> YouTube Monitoring</span>
              <span class="text-xs text-emerald-400 font-medium">Готов</span>
            </div>
            <div class="p-3 rounded-xl bg-slate-950/60 border border-slate-800/60 flex items-center justify-between">
              <span class="flex items-center gap-2"><span>🟣</span> Twitch Live (GQL/API)</span>
              <span class="text-xs text-emerald-400 font-medium">Готов</span>
            </div>
            <div class="p-3 rounded-xl bg-slate-950/60 border border-slate-800/60 flex items-center justify-between">
              <span class="flex items-center gap-2"><span>🎬</span> Rutube & Kick & Trovo</span>
              <span class="text-xs text-emerald-400 font-medium">Готов</span>
            </div>
            <div class="p-3 rounded-xl bg-slate-950/60 border border-slate-800/60 flex items-center justify-between">
              <span class="flex items-center gap-2"><span>📋</span> Trello Sync & PDF Monitor</span>
              <span class="text-xs text-emerald-400 font-medium">Готов</span>
            </div>
            <div class="p-3 rounded-xl bg-slate-950/60 border border-slate-800/60 flex items-center justify-between">
              <span class="flex items-center gap-2"><span>🛡️</span> Protection & Role Dep</span>
              <span class="text-xs text-emerald-400 font-medium">Готов</span>
            </div>
          </div>
        </div>

        <div class="p-6 rounded-2xl bg-slate-900/60 border border-slate-800/80">
          <h2 class="text-base font-semibold text-white mb-4 flex items-center gap-2">
            <span>⚙️</span> Системные данные JSON
          </h2>
          <pre id="raw-stats" class="p-4 rounded-xl bg-slate-950 text-xs text-slate-300 overflow-x-auto border border-slate-800/60">Загрузка данных...</pre>
        </div>
      </div>

      <!-- Right Column: Info & Setup -->
      <div class="space-y-6">
        <div class="p-6 rounded-2xl bg-slate-900/60 border border-slate-800/80">
          <h3 class="text-sm font-semibold text-white mb-3 flex items-center gap-2">
            <span>🔒</span> Конфигурация .env
          </h3>
          <p class="text-xs text-slate-400 leading-relaxed mb-4">
            Для полноценной отправки сообщений в Discord укажите необходимые переменные окружения в настройках или в файле <code class="text-indigo-300">.env</code>:
          </p>
          <ul class="text-xs space-y-2 text-slate-300">
            <li class="p-2 rounded-lg bg-slate-950/80 border border-slate-800 font-mono">DISCORD_BOT_TOKEN</li>
            <li class="p-2 rounded-lg bg-slate-950/80 border border-slate-800 font-mono">VK_TOKEN</li>
            <li class="p-2 rounded-lg bg-slate-950/80 border border-slate-800 font-mono">GLOBAL_LOG_CHANNEL_ID</li>
          </ul>
        </div>

        <div class="p-6 rounded-2xl bg-slate-900/60 border border-slate-800/80 text-xs text-slate-400">
          <div class="font-medium text-slate-200 mb-2">Статус HTTP-сервера</div>
          <p class="leading-relaxed">
            Веб-сервер статистики успешно слушает порт 3000 для внутренней маршрутизации AI Studio, реверс-прокси и предоставления телеметрии.
          </p>
        </div>
      </div>
    </div>
  </div>

  <script>
    async function updateStats() {
      try {
        const res = await fetch('/api/stats');
        if (res.ok) {
          const data = await res.json();
          const uptimeEl = document.getElementById('uptime-display');
          if (uptimeEl) uptimeEl.textContent = data.uptime || '00:00:00';
          const postsEl = document.getElementById('posts-count');
          if (postsEl) postsEl.textContent = data.processed_posts || 0;
          const streamsEl = document.getElementById('streams-count');
          if (streamsEl) streamsEl.textContent = (data.processed_streams || 0) + (data.processed_videos || 0);
          const queueEl = document.getElementById('queue-count');
          if (queueEl) queueEl.textContent = data.queue_size || 0;
          const rawEl = document.getElementById('raw-stats');
          if (rawEl) rawEl.textContent = JSON.stringify(data, null, 2);
        }
      } catch (err) {
        // Soft fallback for initial container spin-up
        const rawEl = document.getElementById('raw-stats');
        if (rawEl && rawEl.textContent === 'Загрузка данных...') {
          rawEl.textContent = 'Подключение к серверу статистики...';
        }
      }
    }
    updateStats();
    setInterval(updateStats, 3000);
  </script>
</body>
</html>
"""

class StatsServer:
    _runner: Optional[web.AppRunner] = None
    _site: Optional[web.TCPSite] = None

    @classmethod
    def is_running(cls) -> bool:
        """Проверяет, запущен ли веб-сервер статистики."""
        return cls._site is not None

    @classmethod
    async def start(cls):
        """Запускает веб-сервер на порту 3000 в фоновом режиме."""
        from settings.config import Config
        from log_system.logger_helper import send_to_any_log
        from constants.emojis import LogEmojis
        if Config.IS_LOCAL_LAUNCH:
            await send_to_any_log("info", "STATS-SERVER: IS_LOCAL_LAUNCH=True — запуск сервера статистики пропущен.", emoji=LogEmojis.INFO, targets=["console", "file"])
            return

        if cls._runner is not None:
            return  # Уже запущен

        @web.middleware
        async def cors_middleware(request: web.Request, handler):
            if request.method == "OPTIONS":
                response = web.Response(status=204)
            else:
                try:
                    response = await handler(request)
                except Exception as ex:
                    response = web.json_response({"error": str(ex)}, status=500)
            
            response.headers["Access-Control-Allow-Origin"] = "*"
            response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS, HEAD"
            response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization, X-Requested-With"
            return response

        app = web.Application(middlewares=[cors_middleware])
        app.router.add_route('*', '/', cls.handle_stats)
        app.router.add_route('*', '/stats', cls.handle_json_stats)
        app.router.add_route('*', '/api/stats', cls.handle_json_stats)
        app.router.add_route('*', '/health', cls.handle_health)

        # Раздача статических файлов из папки assets/
        assets_path = os.path.join(os.getcwd(), 'assets')
        if os.path.isdir(assets_path):
            app.router.add_static('/assets', assets_path, show_index=False)

        cls._runner = web.AppRunner(app)
        await cls._runner.setup()
        cls._site = web.TCPSite(cls._runner, '0.0.0.0', 3000)
        
        try:
            await cls._site.start()
            
            from log_system.logger_helper import send_to_any_log
            from constants.emojis import LogEmojis
            await send_to_any_log(
                "info", 
                "Сервер статистики запущен на порту 3000", 
                emoji=LogEmojis.INFO, 
                targets=["console", "file"]
            )
        except Exception as e:
            await send_to_any_log("error", f"STATS-SERVER: Критическая ошибка при бинде на порт 3000: {e}", emoji=LogEmojis.ERROR, targets=["console", "file"])
            await cls.stop()

    @classmethod
    async def stop(cls):
        """Мягко останавливает веб-сервер и освобождает порт."""
        try:
            if cls._site:
                await cls._site.stop()
                cls._site = None
            if cls._runner:
                await cls._runner.cleanup()
                cls._runner = None
                
                from log_system.logger_helper import send_to_any_log
                from constants.emojis import LogEmojis
                await send_to_any_log(
                    "info", 
                    "Сервер статистики остановлен", 
                    emoji=LogEmojis.INFO, 
                    targets=["console", "file"]
                )
        except Exception as e:
            await send_to_any_log("error", f"STATS-SERVER: Ошибка при остановке сервера: {e}", emoji=LogEmojis.ERROR, targets=["console", "file"])

    @classmethod
    async def handle_stats(cls, request: web.Request):
        """Обработчик главной страницы статистики (HTML для браузера, JSON по запросу)."""
        accept = request.headers.get("Accept", "")
        if "text/html" in accept:
            return web.Response(text=HTML_DASHBOARD, content_type="text/html", headers={"Access-Control-Allow-Origin": "*"})
        
        return await cls.handle_json_stats(request)

    @classmethod
    async def handle_json_stats(cls, request: web.Request):
        """Обработчик JSON эндпоинта статистики."""
        try:
            from modules_utils.stats_manager import stats_manager
            stats = stats_manager.get_stats()
            return web.json_response(stats, headers={"Access-Control-Allow-Origin": "*"})
        except Exception as e:
            return web.json_response({"error": str(e)}, status=500)

    @classmethod
    async def handle_health(cls, request: web.Request):
        """Эндпоинт для Health Check систем мониторинга платформы."""
        return web.json_response({"status": "healthy"}, headers={"Access-Control-Allow-Origin": "*"})
