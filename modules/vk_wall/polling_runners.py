# modules/vk_wall/polling_runners.py
# Три режима опроса, вынесенных из GroupMonitor для уменьшения размера monitor.py.
# Каждая функция принимает GroupMonitor как первый аргумент и работает с его состоянием.
import asyncio
import random
import time

import aiohttp

from constants.emojis import LogEmojis
from log_system.logger_helper import send_to_any_log
from settings.config import Config


async def run_standard_polling(monitor) -> None:
    """Стандартный опрос через wall.get с адаптивным интервалом и circuit breaker."""
    from modules_utils.task_scheduler import scheduler

    while monitor.is_running:
        try:
            name = monitor.group_config.get('name', monitor.platform_id)

            # --- Circuit breaker ---
            if Config.VK_CIRCUIT_BREAKER_ENABLED and monitor._circuit_open_until > 0:
                remaining = monitor._circuit_open_until - time.time()
                if remaining > 0:
                    await asyncio.sleep(min(60, remaining))
                    continue
                monitor._circuit_open_until = 0.0
                await send_to_any_log("info",
                    f"[{name}] Circuit breaker closed — resuming monitoring",
                    emoji=LogEmojis.INFO)

            lock = scheduler.get_check_lock()
            prev_processed = monitor.processed_count

            async with lock:
                try:
                    await asyncio.wait_for(monitor.check_group(), timeout=300)
                except asyncio.TimeoutError:
                    await send_to_any_log("error",
                        f"Group check for {name} timed out (300s)",
                        emoji=LogEmojis.ERROR)
                except Exception as e:
                    await send_to_any_log("error",
                        f"Unexpected error in loop for group {name}: {e}",
                        emoji=LogEmojis.ERROR)

            # --- Обновление circuit breaker и адаптивного интервала ---
            if monitor.last_request_success:
                if monitor._consecutive_errors > 0:
                    monitor._consecutive_errors = 0
                    await send_to_any_log("info",
                        f"[{name}] Circuit breaker reset — connection restored",
                        emoji=LogEmojis.INFO)

                if Config.VK_ADAPTIVE_POLLING_ENABLED:
                    if monitor.processed_count > prev_processed:
                        if monitor._interval_multiplier > 1.0:
                            monitor._interval_multiplier = 1.0
                            await send_to_any_log("info",
                                f"[{name}] Adaptive polling: new posts → interval reset",
                                emoji=LogEmojis.INFO)
                        monitor._last_new_post_time = time.time()
                    elif monitor._last_new_post_time > 0:
                        idle_hours = (time.time() - monitor._last_new_post_time) / 3600
                        if idle_hours >= Config.VK_ADAPTIVE_POLLING_IDLE_HOURS:
                            new_mult = min(
                                monitor._interval_multiplier * 2.0,
                                float(Config.VK_ADAPTIVE_POLLING_MAX_MULTIPLIER)
                            )
                            if new_mult != monitor._interval_multiplier:
                                monitor._interval_multiplier = new_mult
                                base = monitor.group_config.get('check_interval', Config.VK_WALL_CHECK_INTERVAL)
                                await send_to_any_log("info",
                                    f"[{name}] Adaptive polling: no posts for {idle_hours:.1f}h "
                                    f"→ interval ×{monitor._interval_multiplier:.0f} "
                                    f"({int(base * monitor._interval_multiplier)}s)",
                                    emoji=LogEmojis.INFO)
            else:
                monitor._consecutive_errors += 1
                if (Config.VK_CIRCUIT_BREAKER_ENABLED
                        and monitor._consecutive_errors >= Config.VK_CIRCUIT_BREAKER_THRESHOLD
                        and monitor._circuit_open_until == 0.0):
                    pause_secs = Config.VK_CIRCUIT_BREAKER_PAUSE_MINUTES * 60
                    monitor._circuit_open_until = time.time() + pause_secs
                    from modules_utils.stats_manager import stats_manager
                    stats_manager.log_circuit_breaker()
                    await send_to_any_log("warning",
                        f"[{name}] Circuit breaker: {monitor._consecutive_errors} consecutive errors "
                        f"→ pausing for {Config.VK_CIRCUIT_BREAKER_PAUSE_MINUTES} min.",
                        emoji=LogEmojis.WARNING)

            if monitor.is_first_run:
                monitor.is_first_run = False

            base_interval = monitor.group_config.get('check_interval', Config.VK_WALL_CHECK_INTERVAL)
            effective = base_interval * monitor._interval_multiplier
            await asyncio.sleep(effective * random.uniform(0.9, 1.1))

        except asyncio.CancelledError:
            break
        except Exception as e:
            import traceback
            monitor.error_count += 1
            tb = traceback.format_exc()
            await send_to_any_log("error",
                f"Polling loop error in group {monitor.group_config['name']}: {str(e)[:200]}\n{tb[:600]}",
                emoji=LogEmojis.ERROR)
            await asyncio.sleep(60)


async def run_bots_longpoll(monitor) -> None:
    """Режим Bots Long Poll API (для групп с групповым токеном)."""
    from modules_utils.vk_api_client import VKApiClient, VKAPIException
    from modules_utils.http_client import HttpClient

    await send_to_any_log("info",
        f"[{monitor.group_config['name']}] Starting Bots Long Poll API...",
        emoji=LogEmojis.INFO)

    server = None
    key = None
    ts = None

    async def get_lp_server():
        nonlocal server, key, ts
        try:
            response = await VKApiClient.call_api(
                "groups.getLongPollServer",
                {"group_id": abs(monitor.group_id)},
                session=monitor.session,
                token=monitor.group_config.get("vk_token"),
                raise_on_error=True
            )
            if response:
                server = response.get("server")
                key = response.get("key")
                ts = response.get("ts")
                if server and not server.startswith("http"):
                    server = f"https://{server}"
                return server is not None and key is not None and ts is not None
        except VKAPIException as e:
            is_permanent = e.error_code in [5, 15, 27, 28, 100]
            if is_permanent:
                raise e
            await send_to_any_log("warning",
                f"[{monitor.group_config['name']}] Temporary error getting Long Poll server: {e.error_msg}",
                emoji=LogEmojis.WARNING)
        except Exception as e:
            await send_to_any_log("error",
                f"[{monitor.group_config['name']}] Failed to initialize Bots Long Poll: {e}",
                emoji=LogEmojis.ERROR)
        return False

    lp_ok = False
    while monitor.is_running:
        try:
            if await get_lp_server():
                lp_ok = True
                break
        except Exception as e:
            await send_to_any_log("warning",
                f"[{monitor.group_config['name']}] Permanent error initializing Bots Long Poll ({e}). "
                f"Automatically switching to standard polling...",
                emoji=LogEmojis.WARNING)
            monitor.real_tracking_method = "polling"
            await run_standard_polling(monitor)
            return

        await send_to_any_log("warning",
            f"[{monitor.group_config['name']}] Error initializing Bots Long Poll. "
            f"Retrying in 60 seconds...",
            emoji=LogEmojis.WARNING)
        await asyncio.sleep(60)

    if not monitor.is_running or not lp_ok:
        return

    # Предварительная проверка стены до начала LP
    has_local_token = bool(monitor.group_config.get("vk_token"))
    if has_local_token and not Config.VK_TOKEN:
        await send_to_any_log("info",
            f"[{monitor.group_config['name']}] Initial wall check skipped — "
            f"group operates on local token only (bots_longpoll)",
            emoji=LogEmojis.INFO, targets=["console", "file"])
        monitor.is_first_run = False
    else:
        try:
            await monitor.check_group()
            monitor.is_first_run = False
        except Exception as e:
            await send_to_any_log("error",
                f"[{monitor.group_config['name']}] Initial wall check failed: {e}",
                emoji=LogEmojis.ERROR)

    if has_local_token:
        monitor.last_used_token_type = "local (group token)"
        token_origin_info = ("used shared token" if Config.VK_TOKEN
                             else "check skipped, as shared token is missing")
        message_text = (
            f"{LogEmojis.GEAR} **[{monitor.group_config['name']}]** First check passed ({token_origin_info}).\n"
            f"{LogEmojis.PLUG} Local token configured — switching to Bots Long Poll via local token."
        )
        await send_to_any_log("info", message_text, emoji=LogEmojis.SUCCESS)
        from log_system.discord_logger import DiscordLogger
        await DiscordLogger.send_to_channel(content=f"{LogEmojis.SUCCESS} {message_text}")

    retry_count = 0
    while monitor.is_running:
        try:
            timeout = aiohttp.ClientTimeout(total=40)
            params = {"act": "a_check", "key": key, "ts": ts, "wait": 25}

            # 'Connection: close' лечит дропы сокетов long-poll
            data = await HttpClient.get(
                server,
                params=params,
                timeout=timeout,
                max_retries=1,
                headers={"Connection": "close"},
                suppress_errors=True
            )

            if data is None or not isinstance(data, dict):
                retry_count += 1
                if retry_count > 5:
                    await send_to_any_log("warning",
                        f"[{monitor.group_config['name']}] Re-fetching Bots Long Poll settings after series of failures...",
                        emoji=LogEmojis.WARNING)
                    if not await get_lp_server():
                        await asyncio.sleep(15)
                    retry_count = 0
                else:
                    await asyncio.sleep(5)
                continue

            retry_count = 0

            if "failed" in data:
                failed = data["failed"]
                if failed == 1:
                    ts = data.get("ts", ts)
                elif failed in (2, 3):
                    await get_lp_server()
                elif failed == 4:
                    await send_to_any_log("error",
                        f"[{monitor.group_config['name']}] Critical Bots Long Poll error (failed=4)",
                        emoji=LogEmojis.ERROR)
                    await asyncio.sleep(30)
                    await get_lp_server()
                continue

            ts = data.get("ts", ts)
            updates = data.get("updates", [])

            for update in updates:
                if not isinstance(update, dict):
                    continue
                event_type = update.get("type")
                if event_type == "wall_post_new":
                    post = update.get("object")
                    if post:
                        await send_to_any_log("info",
                            f"[{monitor.group_config['name']}] Detected new post via Bots Long Poll!",
                            emoji=LogEmojis.SUCCESS)
                        await asyncio.sleep(3)  # Даем VK серверам обновить кэш контента
                        await monitor.process_post(post)

            await monitor.retry_failed_posts()

        except asyncio.CancelledError:
            break
        except Exception as e:
            await send_to_any_log("error",
                f"[{monitor.group_config['name']}] Exception in Bots Long Poll loop: {e}",
                emoji=LogEmojis.ERROR)
            await asyncio.sleep(10)


async def run_user_longpoll(monitor) -> None:
    """Режим User Long Poll API с дублирующим фоновым периодическим опросом."""
    from modules_utils.http_client import HttpClient

    await send_to_any_log("info",
        f"[{monitor.group_config['name']}] Starting User Long Poll API for user profile...",
        emoji=LogEmojis.INFO)

    server = None
    key = None
    ts = None

    async def get_lp_server():
        nonlocal server, key, ts
        try:
            from modules_utils.vk_api_client import VKApiClient
            response = await VKApiClient.call_api(
                "messages.getLongPollServer",
                {"lp_version": 3},
                session=monitor.session,
                token=monitor.group_config.get("vk_token")
            )
            if response:
                server = response.get("server")
                key = response.get("key")
                ts = response.get("ts")
                if server and not server.startswith("http"):
                    server = f"https://{server}"
                return server is not None and key is not None and ts is not None
        except Exception as e:
            await send_to_any_log("error",
                f"[{monitor.group_config['name']}] Failed to initialize User Long Poll: {e}",
                emoji=LogEmojis.ERROR)
        return False

    # Фоновый опрос запускается только если Long Poll молчит дольше порога
    _LP_SILENCE_THRESHOLD = 200  # секунд
    _last_lp_event_time: list = [time.time()]  # list-обёртка для изменения из closure

    async def backup_polling():
        await asyncio.sleep(10)
        while monitor.is_running:
            silence = time.time() - _last_lp_event_time[0]
            if silence >= _LP_SILENCE_THRESHOLD:
                try:
                    await send_to_any_log("debug",
                        f"[{monitor.group_config['name']}] Backup polling: Long Poll silent for {silence:.0f}s, performing wall check",
                        emoji=LogEmojis.DEBUG)
                    await monitor.check_group()
                    monitor.is_first_run = False
                except Exception as e:
                    await send_to_any_log("error",
                        f"[{monitor.group_config['name']}] Error in backup polling during User Long Poll: {e}",
                        emoji=LogEmojis.ERROR)
            await asyncio.sleep(180)

    # Предварительная проверка стены
    try:
        await monitor.check_group()
        monitor.is_first_run = False
    except Exception as e:
        await send_to_any_log("error",
            f"[{monitor.group_config['name']}] Initial wall check failed: {e}",
            emoji=LogEmojis.ERROR)

    from modules_utils.helpers import safe_create_task
    backup_polling_task = safe_create_task(backup_polling())

    try:
        if not await get_lp_server():
            await send_to_any_log("warning",
                f"[{monitor.group_config['name']}] Switching to standard polling "
                f"due to User Long Poll initialization error",
                emoji=LogEmojis.WARNING)
            monitor.real_tracking_method = "polling"
            await run_standard_polling(monitor)
            return

        retry_count = 0
        while monitor.is_running:
            try:
                timeout = aiohttp.ClientTimeout(total=40)
                params = {
                    "act": "a_check", "key": key, "ts": ts,
                    "wait": 25, "mode": 2, "version": 3
                }

                # 'Connection: close' лечит дропы сокетов long-poll
                data = await HttpClient.get(
                    server,
                    params=params,
                    timeout=timeout,
                    max_retries=1,
                    headers={"Connection": "close"},
                    suppress_errors=True
                )

                if data is None or not isinstance(data, dict):
                    retry_count += 1
                    if retry_count > 5:
                        await send_to_any_log("warning",
                            f"[{monitor.group_config['name']}] Re-fetching User Long Poll settings after series of failures...",
                            emoji=LogEmojis.WARNING)
                        if not await get_lp_server():
                            await asyncio.sleep(15)
                        retry_count = 0
                    else:
                        await asyncio.sleep(5)
                    continue

                retry_count = 0

                if "failed" in data:
                    failed = data["failed"]
                    if failed == 1:
                        ts = data.get("ts", ts)
                    elif failed in (2, 3):
                        await get_lp_server()
                    elif failed == 4:
                        await send_to_any_log("error",
                            f"[{monitor.group_config['name']}] Critical User Long Poll error (failed=4)",
                            emoji=LogEmojis.ERROR)
                        await asyncio.sleep(30)
                        await get_lp_server()
                    continue

                ts = data.get("ts", ts)
                updates = data.get("updates", [])

                if updates:
                    _last_lp_event_time[0] = time.time()
                    await send_to_any_log("info",
                        f"[{monitor.group_config['name']}] Detected socket activity "
                        f"(User Long Poll events: {len(updates)}). Performing fast wall check",
                        emoji=LogEmojis.SUCCESS)
                    await monitor.check_group()
                else:
                    await monitor.retry_failed_posts()

            except asyncio.CancelledError:
                break
            except Exception as e:
                await send_to_any_log("error",
                    f"[{monitor.group_config['name']}] Exception in User Long Poll loop: {e}",
                    emoji=LogEmojis.ERROR)
                await asyncio.sleep(10)
    finally:
        backup_polling_task.cancel()
        try:
            await backup_polling_task
        except asyncio.CancelledError:
            pass
        except Exception as e:
            await send_to_any_log("error",
                f"[{monitor.group_config['name']}] Error stopping backup polling task: {e}",
                emoji=LogEmojis.ERROR)
