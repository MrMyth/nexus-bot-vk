# startup/runner.py
# main() and run_forever() — entry point into asyncio and outer restart supervisor loop.
import asyncio
import os
import sys
import time
from datetime import datetime

import discord

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


async def main():
    """Initializes the bot and runs discord_client.start()."""
    from settings.data_files import Files
    from settings.config_validator import validate_config
    from settings.config import Config
    from log_system.logger_helper import send_to_any_log
    from constants.emojis import LogEmojis
    from modules_utils.helpers import safe_create_task
    from startup.bot import VKToDiscordBot

    Files.ensure_directories()
    await validate_config()

    replit_domain = os.environ.get("REPLIT_DEV_DOMAIN", "")
    if replit_domain and not Config.ASSETS_BASE_URL:
        Config.ASSETS_BASE_URL = f"https://{replit_domain}"
        print(f"[ASSETS] ASSETS_BASE_URL automatically set: {Config.ASSETS_BASE_URL}")

    # Launch stats web-server (port 3000) unless local launch mode is enabled
    if not Config.IS_LOCAL_LAUNCH:
        try:
            from modules_utils.stats_server import StatsServer
            await StatsServer.start()
        except Exception as server_err:
            print(f"[STATS-SERVER] Failed to start stats server: {server_err}")
    else:
        print("[STATS-SERVER] Local launch mode (IS_LOCAL_LAUNCH=True) — stats server skipped.")

    if Config.DISABLE_BOT:
        await send_to_any_log("warning",
            f"{LogEmojis.BOT} BOT IS DISABLED (DISABLE_BOT=True). All modules stopped. Entering sleep mode.",
            emoji=LogEmojis.WARNING)
        while True:
            await asyncio.sleep(3600)

    max_rate_limit_retries = 5
    bot = None
    try:
        for attempt in range(max_rate_limit_retries):
            bot = VKToDiscordBot()

            async def monitor_connection():
                try:
                    await asyncio.sleep(6)
                    if not bot._started:
                        await send_to_any_log("info",
                            f"{LogEmojis.CONNECTING} Connecting to Discord... Authenticating token.",
                            emoji=LogEmojis.CONNECTING, targets=["console", "file"])
                    await asyncio.sleep(12)
                    if not bot._started:
                        await send_to_any_log("info",
                            f"{LogEmojis.CONNECTING} Still attempting connection. Verify token and network connectivity.",
                            emoji=LogEmojis.CONNECTING, targets=["console", "file"])
                    await asyncio.sleep(22)
                    if not bot._started:
                        await send_to_any_log("warning",
                            f"{LogEmojis.WARNING} Discord connection delayed. Potential causes:\n"
                            "1. Invalid DISCORD_BOT_TOKEN in .env file.\n"
                            "2. Missing privileged Gateway Intents (Presence, Server Members, Message Content).\n"
                            "3. Network firewall or proxy restriction.",
                            emoji=LogEmojis.WARNING, targets=["console", "file"])
                except asyncio.CancelledError:
                    pass

            monitor_task = safe_create_task(monitor_connection())
            try:
                await bot.discord_client.start(Config.DISCORD_BOT_TOKEN)
                break
            except asyncio.CancelledError:
                await send_to_any_log("info",
                    "Connection closed: Bot start task was cancelled (graceful shutdown or restart).",
                    emoji=LogEmojis.INFO, targets=["console", "file"])
                break
            except Exception as e:
                error_msg = str(e)
                if isinstance(e, discord.HTTPException) and e.status == 429:
                    retry_after = getattr(e, 'retry_after', 60)
                    safe_create_task(send_to_any_log("critical",
                        f"Discord Rate Limit! Waiting {retry_after}s before retry (attempt {attempt + 1})",
                        emoji=LogEmojis.CRITICAL, targets=["console", "file"]))
                    await asyncio.sleep(retry_after)
                    continue

                await send_to_any_log("critical", f"Startup error: {error_msg}",
                                      emoji=LogEmojis.CRITICAL, targets=["console", "file"])
                if bot:
                    try:
                        await bot.stop(reason=f"Startup failure: {error_msg}")
                    except Exception as stop_error:
                        print(f"DEBUG: Error during bot.stop(): {stop_error}")
                else:
                    from modules_utils.http_client import HttpClient
                    await HttpClient.close_session()

                await asyncio.sleep(15)
                continue
            finally:
                monitor_task.cancel()
    finally:
        if not Config.IS_LOCAL_LAUNCH:
            try:
                from modules_utils.stats_server import StatsServer
                await StatsServer.stop()
            except Exception as e:
                print(f"[shutdown] Error stopping StatsServer: {e}")
        if bot and bot._started:
            await bot.stop(reason="main() process terminated")


def run_forever(project_root: str):
    """Outer restart supervisor loop around asyncio.run(main()).
    Handles KeyboardInterrupt, critical errors, and retry delays."""
    import signal
    from settings.config import Config
    from modules_utils.helpers import cleanup_pycache
    from modules_utils.restart_helper import RestartHelper
    from log_system.logger_helper import send_to_any_log
    from constants.emojis import LogEmojis

    if Config.KEYBOARD_INTERRUPT_MODE.lower() == "ignore":
        signal.signal(signal.SIGINT, signal.SIG_IGN)

    while True:
        try:
            cleanup_pycache(project_root)

            if getattr(RestartHelper, "_delay_before_start", 0.0) > 0.0:
                delay = RestartHelper._delay_before_start
                RestartHelper._delay_before_start = 0.0
                time.sleep(delay)

            asyncio.run(main())

            # Check graceful termination flags
            if RestartHelper._shutdown_requested:
                RestartHelper._shutdown_requested = False
                async def _log_shutdown():
                    await send_to_any_log("info",
                        "Bot gracefully shutdown. Goodbye!",
                        emoji=LogEmojis.INFO, targets=["console", "file"])
                asyncio.run(_log_shutdown())
                break

            if RestartHelper._restart_requested:
                RestartHelper._restart_requested = False
                continue

            # Unexpected main() exit
            async def _log_unexpected():
                await send_to_any_log("warning",
                    "Main loop exited unexpectedly. Restarting in 10s...",
                    emoji=LogEmojis.WARNING, targets=["console", "file"])
            asyncio.run(_log_unexpected())
            time.sleep(10)

        except KeyboardInterrupt:
            mode = Config.KEYBOARD_INTERRUPT_MODE.lower()
            if mode == "restart":
                async def _log_restart():
                    await send_to_any_log("warning",
                        "Received Ctrl+C signal, ignoring (KEYBOARD_INTERRUPT_MODE=restart). Restarting...",
                        emoji=LogEmojis.WARNING, targets=["console", "file"])
                asyncio.run(_log_restart())
                continue
            elif mode == "ignore":
                continue
            else:
                async def _log_stop():
                    await send_to_any_log("info", "Bot stopped by user (Ctrl+C)",
                                          emoji=LogEmojis.INFO, targets=["console", "file"])
                asyncio.run(_log_stop())
                break

        except Exception as e:
            async def _handle_critical():
                try:
                    from log_system.logger_helper import send_to_any_log as _log
                    from constants.emojis import LogEmojis as _LE
                    await _log("critical", f"Critical error: {e}", emoji=_LE.CRITICAL,
                               targets=["console", "file"])
                    from log_system.discord_logger import DiscordLogger
                    await DiscordLogger.send_restore_alert(str(e))
                except Exception as inner_e:
                    print(f"[critical] Error logging critical exception: {inner_e}")
            try:
                asyncio.run(_handle_critical())
            except Exception as run_e:
                print(f"Critical error: {e} (Handler error: {run_e})")

            print("\n" + "=" * 50)
            print("PROGRAM PAUSED DUE TO CRITICAL ERROR")
            print(f"Error: {e}")
            print("=" * 50)

            critical_mode = getattr(Config, "CRITICAL_ERROR_MODE", "interactive").lower()

            if critical_mode in ("restart", "stop"):
                auto_delay = getattr(Config, "CRITICAL_ERROR_AUTO_DELAY", 10)
                action = "restart" if critical_mode == "restart" else "shutdown"
                print(f"[CRITICAL_ERROR_MODE={critical_mode}] Automatic reaction: {action} in {auto_delay}s.")
                time.sleep(auto_delay)
                if critical_mode == "stop":
                    print("Shutting down (CRITICAL_ERROR_MODE=stop).")
                    break
                print("Restarting bot...")
                continue

            try:
                now_str = datetime.now().strftime('%H:%M:%S')
                print(f"[{now_str}] Waiting 1 minute...")
                time.sleep(60)

                now_str = datetime.now().strftime('%H:%M:%S')
                print(f"[{now_str}] Waiting 5 more minutes before prompt...")
                time.sleep(300)

                print("\n" + "!" * 40)
                print("PROMPT: STOP or RESTART bot?")
                print("Type 'stop' or 's' to terminate.")
                print("If no input within 60 seconds, the bot will automatically RESTART.")
                print("!" * 40)

                user_response = None
                timeout = 60

                if os.name == 'nt':
                    import msvcrt
                    print(f"Waiting for input ({timeout}s): ", end='', flush=True)
                    prompt_start = time.time()
                    input_str = ""
                    while time.time() - prompt_start < timeout:
                        if msvcrt.kbhit():
                            char = msvcrt.getwche()
                            if char in ['\r', '\n']:
                                user_response = input_str
                                print()
                                break
                            elif char == '\b':
                                if input_str:
                                    input_str = input_str[:-1]
                                    print('\b \b', end='', flush=True)
                            else:
                                input_str += char
                        time.sleep(0.05)
                    if user_response is None:
                        print("\n[Timeout] No input received.")
                else:
                    import select
                    print(f"Waiting for input ({timeout}s): ", end='', flush=True)
                    rlist, _, _ = select.select([sys.stdin], [], [], timeout)
                    if rlist:
                        user_response = sys.stdin.readline().strip()
                    else:
                        print("\n[Timeout] No input received.")

                if user_response and user_response.lower() in ['stop', 's', 'exit', 'q', 'quit']:
                    print("Shutdown requested by user.")
                    break
            except Exception as loop_err:
                print(f"Error in restart wait loop: {loop_err}")

            print("Restarting bot...")
            time.sleep(2)
            continue
