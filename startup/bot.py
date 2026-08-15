# startup/bot.py
# VKToDiscordBot — main application class.
# Manages Discord client initialization, platform managers,
# event registration, and bot lifecycle.
import asyncio
import os
import sys
import importlib
from datetime import datetime

import discord
from discord.ext import commands
from discord.utils import MISSING

from constants.emojis import LogEmojis
from constants.strings import BotStrings
from modules_utils.helpers import safe_create_task, cancel_all_tracked_tasks
from settings.config import Config
from log_system.logger_helper import send_to_any_log
from clients.discord_client import DiscordBotManager
from modules.vk_wall.monitor_manager import MonitorManager
from log_system.discord_logger import DiscordLogger
from modules_utils.restart_helper import RestartHelper

import clients.bot_instance
from modules_utils.group_cache import start_periodic_cleanup
from modules_utils.presence_manager import PresenceManager
from modules.trello.trello_boards import TRELLO_BOARDS
from modules_utils.stats_manager import stats_manager
from modules.vk_wall.group_search import load_groups
from modules_utils.http_client import HttpClient
from modules_utils.stats_server import StatsServer
from modules_utils.task_scheduler import scheduler

# Project root relative to this file (startup/bot.py -> project_root)
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class VKToDiscordBot:
    def __init__(self):
        self._started = False
        # Guard against double invocation of request_graceful_restart/shutdown
        self._graceful_exit_in_progress = False

        intents = discord.Intents.default()
        intents.message_content = Config.INTENTS_MESSAGE_CONTENT
        intents.presences = Config.INTENTS_PRESENCES
        intents.members = Config.INTENTS_MEMBERS
        intents.voice_states = Config.INTENTS_VOICE_STATES

        allowed_mentions = discord.AllowedMentions(roles=True, users=True, everyone=False)
        self.discord_client = commands.Bot(command_prefix=Config.COMMAND_PREFIX, intents=intents, allowed_mentions=allowed_mentions, help_command=None)
        self.discord_client.app = self
        clients.bot_instance.bot = self.discord_client

        self.group_mappings = {}
        self.discord_bot = DiscordBotManager(bot=self.discord_client, group_mappings=self.group_mappings)

        # Standalone modules (populated on extension loading)
        self.STANDALONE_MODULE_ATTRS = [
            "user_activity_module",
            "game_tracker_module",
            "protection_module",
            "role_dependency_module",
            "pdf_monitor_module",
            "telegram_module",
            "secret_vendors_module",
            "game_schedule_module",
            "image_forwarder_module",
        ]
        for attr in self.STANDALONE_MODULE_ATTRS:
            setattr(self, attr, None)

        # Registry of standalone Discord extensions: (config_flag, extension_name)
        self.EXTENSION_REGISTRY = [
            ("ENABLE_VOICE_REGION_MODULE", "modules.standalone.voice_region_module"),
            ("ENABLE_USER_ACTIVITY_MODULE", "modules.standalone.user_activity_module"),
            ("ENABLE_GAME_TRACKER_MODULE", "modules.standalone.game_tracker_module"),
            ("ENABLE_DISCORD_CHANNEL_PROTECTION", "modules.standalone.protection_module"),
            ("ENABLE_ROLE_DEPENDENCY_MODULE", "modules.standalone.role_dependency_module"),
            ("ENABLE_PDF_MONITOR_MODULE", "modules.standalone.pdf_module"),
            ("ENABLE_TELEGRAM_MODULE", "modules.standalone.telegram_module"),
            ("ENABLE_SECRET_VENDORS_MODULE", "modules.standalone.secret_vendors_module"),
            ("ENABLE_GAME_SCHEDULE_MODULE", "modules.standalone.game_schedule_module"),
            ("ENABLE_IMAGE_FORWARDER_MODULE", "modules.standalone.image_forwarder_module"),
        ]

        # Platform managers registry: (attribute_name, config_flag, import_path, class_name, argument_type)
        # argument_type: 'bot_manager' (pass self.discord_bot) or 'client' (pass bot=self.discord_client)
        self.MANAGER_REGISTRY = [
            ("vk_live_manager", "ENABLE_VK_LIVE_MONITORING", "modules.vk_live.live_manager", "LiveManager", "bot_manager"),
            ("trello_module", "ENABLE_TRELLO_MODULE", "modules.trello.trello_module", "TrelloModule", "client"),
            ("youtube_manager", "ENABLE_YOUTUBE_MONITORING", "modules.youtube.youtube_manager", "YouTubeManager", "bot_manager"),
            ("rutube_manager", "ENABLE_RUTUBE_MONITORING", "modules.rutube.rutube_manager", "RutubeManager", "bot_manager"),
            ("twitch_live_manager", "ENABLE_TWITCH_LIVE_MONITORING", "modules.twitch_live.twitch_manager", "TwitchLiveManager", "bot_manager"),
            ("kick_live_manager", "ENABLE_KICK_LIVE_MONITORING", "modules.kick_live.kick_manager", "KickLiveManager", "bot_manager"),
            ("trovo_live_manager", "ENABLE_TROVO_MONITORING", "modules.trovo.trovo_manager", "TrovoManager", "bot_manager"),
            ("vk_asset_manager", "ENABLE_VK_ASSETS_MONITORING", "modules.vk_assets.asset_manager", "VKAssetManager", "bot_manager"),
            ("vk_com_live_manager", "ENABLE_VK_COM_LIVE_MONITORING", "modules.vk_com_live.live_manager", "VKComLiveManager", "bot_manager"),
            ("goodgame_live_manager", "ENABLE_GOODGAME_MONITORING", "modules.goodgame.goodgame_manager", "GoodGameLiveManager", "bot_manager"),
        ]

        # Platform managers
        self.vk_wall_manager = MonitorManager(self.discord_bot)
        
        # Dynamic initialization of platform managers from registry
        for attr_name, config_flag, import_path, class_name, arg_type in self.MANAGER_REGISTRY:
            setattr(self, attr_name, None)
            if getattr(Config, config_flag, False):
                try:
                    module = importlib.import_module(import_path)
                    manager_class = getattr(module, class_name)
                    if arg_type == "client":
                        instance = manager_class(bot=self.discord_client)
                    else:
                        instance = manager_class(self.discord_bot)
                    setattr(self, attr_name, instance)
                except Exception as e:
                    print(f"[STARTUP] Error loading manager {class_name} from {import_path}: {e}")

        self.groups = []
        self.start_time = None

        self.discord_client.setup_hook = self._make_setup_hook()
        self._register_events()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _make_setup_hook(self):
        """Returns setup_hook coroutine for discord.py."""
        async def setup_hook():
            try:
                await self.discord_client.load_extension("modules.standalone.commands_module")

                for config_flag, ext_name in self.EXTENSION_REGISTRY:
                    if getattr(Config, config_flag, False):
                        await self.discord_client.load_extension(ext_name)

                await self._sync_commands_if_needed()

                start_periodic_cleanup()
            except Exception as e:
                print(f"{LogEmojis.ERROR} Error loading extensions or syncing commands: {e}")

        return setup_hook

    async def _sync_commands_if_needed(self):
        """
        Checks if slash commands need sync with Discord API.
        """
        tree = self.discord_client.tree

        def normalize_option(opt):
            res = {
                'name': opt.get('name'),
                'description': opt.get('description', ''),
                'type': opt.get('type'),
                'required': opt.get('required', False),
            }
            if 'choices' in opt and opt['choices']:
                choices = [{'name': c['name'], 'value': c['value']} for c in opt['choices']]
                res['choices'] = sorted(choices, key=lambda c: (c['name'], str(c['value'])))
            if 'options' in opt and opt['options']:
                sub_opts = [normalize_option(sub) for sub in opt['options']]
                res['options'] = sorted(sub_opts, key=lambda x: x['name'])
            return res

        def normalize_command(cmd_dict):
            opts = [normalize_option(o) for o in cmd_dict.get('options', [])]
            res = {
                'name': cmd_dict.get('name'),
                'description': cmd_dict.get('description', ''),
                'type': cmd_dict.get('type', 1),
                'options': sorted(opts, key=lambda x: x['name']),
            }
            if 'nsfw' in cmd_dict and cmd_dict['nsfw']:
                res['nsfw'] = True
            return res

        try:
            local_commands = tree.get_commands()
            fetched_commands = await tree.fetch_commands()

            need_sync = False
            if len(local_commands) != len(fetched_commands):
                need_sync = True
            else:
                local_by_name = {cmd.name: normalize_command(cmd.to_dict(tree)) for cmd in local_commands}
                fetched_by_name = {cmd.name: normalize_command(cmd.to_dict()) for cmd in fetched_commands}

                if set(local_by_name.keys()) != set(fetched_by_name.keys()):
                    need_sync = True
                else:
                    need_sync = any(local_by_name[name] != fetched_by_name[name] for name in local_by_name)

            if need_sync:
                print(f"{LogEmojis.CONNECTING} Unsynced slash commands detected. Synchronizing...")
                synced = await tree.sync()
                print(f"{LogEmojis.SUCCESS} Successfully synced {len(synced)} slash commands")
            else:
                print(f"{LogEmojis.SUCCESS} All slash commands are already synchronized ({len(local_commands)} total)")
        except Exception as err:
            print(f"{LogEmojis.CONNECTING} Sync check failed ({err}). Executing direct synchronization...")
            synced = await tree.sync()
            print(f"{LogEmojis.SUCCESS} Successfully synced {len(synced)} slash commands")

    def _register_events(self):
        """Registers Discord event listeners."""

        @self.discord_client.event
        async def on_ready():
            if self._started:
                safe_create_task(send_to_any_log("info", "on_ready event fired again — ignoring",
                                                 emoji=LogEmojis.INFO, targets=["console", "file"]))
                return
            self._started = True
            RestartHelper.reset_attempts()

            # Guild chunking
            if self.discord_client.intents.members and Config.ENABLE_GUILD_CHUNKING:
                async def chunk_guilds_task():
                    try:
                        await self.discord_client.wait_until_ready()
                        for guild in self.discord_client.guilds:
                            try:
                                await send_to_any_log("info", f"Starting member chunking for guild: {guild.name} ({guild.id})...",
                                                                 emoji=LogEmojis.INFO, targets=["console", "file"])
                                await guild.chunk()
                                await send_to_any_log("info", f"Successfully chunked {len(guild.members)} members for guild: {guild.name}",
                                                                 emoji=LogEmojis.SUCCESS, targets=["console", "file"])
                            except Exception as chunk_err:
                                await send_to_any_log("error", f"Failed member chunking for guild {guild.name}: {chunk_err}",
                                                                 emoji=LogEmojis.ERROR, targets=["console", "file"])
                    except Exception as t_err:
                        print(f"[CHUNK] Error in member chunking task: {t_err}")

                safe_create_task(chunk_guilds_task())

            try:
                safe_create_task(PresenceManager.apply_presence(self.discord_client))
            except Exception as e:
                print(f"[STARTUP] Error applying presence status: {e}")

            # Bot identity
            async def apply_bot_identity():
                try:
                    await self.discord_client.wait_until_ready()
                    bot_username = Config.BOT_USERNAME
                    bot_nickname = Config.BOT_NICKNAME

                    try:
                        import json
                        from modules_utils.files import get_config_path
                        path = get_config_path("default_embeds_config.json")
                        if os.path.exists(path):
                            with open(path, "r", encoding="utf-8") as f:
                                base_data = json.load(f)
                                if not bot_username:
                                    bot_username = base_data.get("bot_username", "")
                                if not bot_nickname:
                                    bot_nickname = base_data.get("bot_nickname", "")
                    except Exception as json_err:
                        print(f"[IDENTITY] Error reading bot identity JSON config: {json_err}")

                    # 1. Update global username
                    if bot_username and self.discord_client.user.name != bot_username:
                        try:
                            await self.discord_client.user.edit(username=bot_username)
                            await send_to_any_log("info", BotStrings.LOG_NAME_CHANGED.format(username=bot_username),
                                                             emoji=LogEmojis.SUCCESS, targets=["console", "file"])
                        except Exception as edit_err:
                            await send_to_any_log("error", BotStrings.LOG_NAME_CHANGE_ERROR.format(username=bot_username, error=edit_err),
                                                             emoji=LogEmojis.ERROR, targets=["console", "file"])

                    # 2. Update local guild nicknames
                    if bot_nickname:
                        for guild in self.discord_client.guilds:
                            member = guild.me
                            if not member:
                                try:
                                    member = await guild.fetch_member(self.discord_client.user.id)
                                except Exception:
                                    pass
                            if member and member.nick != bot_nickname:
                                try:
                                    await member.edit(nick=bot_nickname)
                                    await send_to_any_log("info", BotStrings.LOG_NICKNAME_CHANGED.format(guild=guild.name, nickname=bot_nickname),
                                                                     emoji=LogEmojis.SUCCESS, targets=["console", "file"])
                                except Exception as nick_err:
                                    await send_to_any_log("error", BotStrings.LOG_NICKNAME_CHANGE_ERROR.format(guild=guild.name, error=nick_err),
                                                                     emoji=LogEmojis.ERROR, targets=["console", "file"])
                except Exception as t_err:
                    print(f"[IDENTITY] Error updating bot identity: {t_err}")

            safe_create_task(apply_bot_identity())

            safe_create_task(send_to_any_log("info", BotStrings.LOG_DISCORD_CONNECTED.format(user=self.discord_client.user),
                                             emoji=LogEmojis.CONNECTING, targets=["console", "file"]))
            safe_create_task(self.run())

        @self.discord_client.event
        async def on_guild_join(guild):
            if self.discord_client.intents.members and Config.ENABLE_GUILD_CHUNKING:
                try:
                    await send_to_any_log("info", BotStrings.LOG_GUILD_JOIN_CHUNKING.format(guild=guild.name, guild_id=guild.id),
                                                     emoji=LogEmojis.INFO, targets=["console", "file"])
                    await guild.chunk()
                    await send_to_any_log("info", BotStrings.LOG_GUILD_JOIN_CHUNKED.format(count=len(guild.members), guild=guild.name),
                                                     emoji=LogEmojis.SUCCESS, targets=["console", "file"])
                except Exception as chunk_err:
                    await send_to_any_log("error", BotStrings.LOG_MEMBER_CACHE_ERROR.format(guild=guild.name, error=chunk_err),
                                                     emoji=LogEmojis.ERROR, targets=["console", "file"])

            # Apply nickname on new guild
            try:
                bot_nickname = Config.BOT_NICKNAME
                try:
                    import json
                    from modules_utils.files import get_config_path
                    path = get_config_path("default_embeds_config.json")
                    if os.path.exists(path):
                        with open(path, "r", encoding="utf-8") as f:
                            base_data = json.load(f)
                            if not bot_nickname:
                                bot_nickname = base_data.get("bot_nickname", "")
                except Exception:
                    pass

                if bot_nickname:
                    member = guild.me
                    if not member:
                        try:
                            member = await guild.fetch_member(self.discord_client.user.id)
                        except Exception:
                            pass
                    if member and member.nick != bot_nickname:
                        await member.edit(nick=bot_nickname)
                        await send_to_any_log("info", BotStrings.LOG_NICKNAME_NEW_GUILD_CHANGED.format(guild=guild.name, nickname=bot_nickname),
                                                         emoji=LogEmojis.SUCCESS, targets=["console", "file"])
            except Exception as nick_err:
                await send_to_any_log("error", BotStrings.LOG_NICKNAME_NEW_GUILD_ERROR.format(guild=guild.name, error=nick_err),
                                                 emoji=LogEmojis.ERROR, targets=["console", "file"])

        @self.discord_client.event
        async def on_disconnect():
            safe_create_task(send_to_any_log("info", BotStrings.LOG_DISCORD_DISCONNECTED,
                                             emoji=LogEmojis.DISCONNECTED, targets=["console", "file"]))
            if Config.USE_AUTO_RESTART and self._started:
                await RestartHelper.start_auto_restart(self)

        @self.discord_client.event
        async def on_close():
            safe_create_task(send_to_any_log("info", BotStrings.LOG_CONNECTION_CLOSED,
                                             emoji=LogEmojis.DISCONNECTED, targets=["console", "file"]))

    # ------------------------------------------------------------------
    # Startup notification
    # ------------------------------------------------------------------

    async def send_startup_notification(self):
        """Collects statistics and sends startup notification."""
        stop_reason = RestartHelper.load_stop_reason()

        startup_data = {
            'stop_reason': stop_reason,
            'group_count': len(self.groups),
            'retention_days': Config.RETENTION_DAYS,
            'timezone_region': getattr(Config, "TIMEZONE_REGION", "Europe/Moscow"),
            'disable_logger': Config.DISABLE_LOGGER,
            'use_auto_restart': Config.USE_AUTO_RESTART,
            'auto_restart_interval': Config.AUTO_RESTART_INTERVAL_MINUTES,
            'use_group_avatar_as_default': getattr(Config, "USE_GROUP_AVATAR_AS_DEFAULT", False),
            'use_group_cover_as_preview': getattr(Config, "USE_GROUP_COVER_AS_PREVIEW", False),
            'alert_role_id': getattr(Config, "ALERT_ROLE_ID", None),
            'modules_status': {
                'posts': Config.ENABLE_VK_WALL_MONITORING,
                'live': Config.ENABLE_VK_LIVE_MONITORING,
                'user_activity': Config.ENABLE_USER_ACTIVITY_MODULE,
                'channel_protection': Config.ENABLE_DISCORD_CHANNEL_PROTECTION,
                'trello': Config.ENABLE_TRELLO_MODULE,
                'pdf_monitor': Config.ENABLE_PDF_MONITOR_MODULE,
                'telegram': Config.ENABLE_TELEGRAM_MODULE,
                'youtube': Config.ENABLE_YOUTUBE_MONITORING,
                'rutube': Config.ENABLE_RUTUBE_MONITORING,
                'twitch_live': Config.ENABLE_TWITCH_LIVE_MONITORING,
                'kick_live': Config.ENABLE_KICK_LIVE_MONITORING,
                'trovo_live': Config.ENABLE_TROVO_MONITORING,
                'vk_com_live': Config.ENABLE_VK_COM_LIVE_MONITORING,
                'goodgame_live': Config.ENABLE_GOODGAME_MONITORING,
                'vk_assets': Config.ENABLE_VK_ASSETS_MONITORING,
                'role_dependency': Config.ENABLE_ROLE_DEPENDENCY_MODULE,
                'game_tracker': Config.ENABLE_GAME_TRACKER_MODULE,
                'voice_region': Config.ENABLE_VOICE_REGION_MODULE,
                'secret_vendors': Config.ENABLE_SECRET_VENDORS_MODULE,
                'game_schedule': Config.ENABLE_GAME_SCHEDULE_MODULE,
                'image_forwarder': Config.ENABLE_IMAGE_FORWARDER_MODULE,
                'stats_server': (lambda: __import__('modules_utils.stats_server', fromlist=['StatsServer']).StatsServer.is_running())(),
            },
        }

        if self.protection_module:
            protected_channels = await self.protection_module.get_protected_channels()
            startup_data['protected_count'] = len(protected_channels)
        else:
            startup_data['protected_count'] = 0

        startup_data['vk_wall_count'] = len(self.vk_wall_manager.monitors) if self.vk_wall_manager else 0
        startup_data['vk_live_count'] = len(self.vk_live_manager.monitors) if self.vk_live_manager else 0

        youtube_manager = getattr(self, "youtube_manager", None)
        rutube_manager = getattr(self, "rutube_manager", None)

        youtube_live_count = youtube_video_count = 0
        youtube_api_count = youtube_rss_count = 0
        if youtube_manager:
            for m in youtube_manager.monitors.values():
                if getattr(m, 'monitor_live', True):
                    youtube_live_count += 1
                if getattr(m, 'monitor_video', True):
                    youtube_video_count += 1
                # Tracking type: by API token or pure RSS
                if getattr(m, 'api_key', None):
                    youtube_api_count += 1
                else:
                    youtube_rss_count += 1
        startup_data['youtube_live_count'] = youtube_live_count
        startup_data['youtube_video_count'] = youtube_video_count
        startup_data['youtube_api_count'] = youtube_api_count
        startup_data['youtube_rss_count'] = youtube_rss_count

        rutube_live_count = rutube_video_count = 0
        if rutube_manager:
            for m in rutube_manager.monitors.values():
                if getattr(m, 'monitor_live', True):
                    rutube_live_count += 1
                if getattr(m, 'monitor_video', True):
                    rutube_video_count += 1
        startup_data['rutube_live_count'] = rutube_live_count
        startup_data['rutube_video_count'] = rutube_video_count

        startup_data['twitch_count'] = len(self.twitch_live_manager.monitors) if self.twitch_live_manager else 0

        # Human-readable Twitch check type
        twitch_enabled = Config.ENABLE_TWITCH_LIVE_MONITORING
        has_twitch_keys = bool(Config.TWITCH_CLIENT_ID and Config.TWITCH_CLIENT_SECRET)
        use_scraper_primary = getattr(Config, "TWITCH_USE_SCRAPER_PRIMARY", True)

        if twitch_enabled:
            if has_twitch_keys:
                if use_scraper_primary:
                    twitch_check_type = BotStrings.STARTUP_TWITCH_CHECK_GQL_API
                else:
                    twitch_check_type = BotStrings.STARTUP_TWITCH_CHECK_API
            else:
                twitch_check_type = BotStrings.STARTUP_TWITCH_CHECK_NO_KEYS
        else:
            twitch_check_type = ""

        startup_data['twitch_check_type'] = twitch_check_type
        startup_data['kick_count'] = len(self.kick_live_manager.monitors) if self.kick_live_manager else 0
        startup_data['trovo_count'] = len(self.trovo_live_manager.monitors) if self.trovo_live_manager else 0
        startup_data['vk_com_count'] = len(self.vk_com_live_manager.monitors) if self.vk_com_live_manager else 0
        startup_data['goodgame_count'] = len(self.goodgame_live_manager.monitors) if self.goodgame_live_manager else 0
        startup_data['vk_assets_count'] = len(self.vk_asset_manager.monitors) if self.vk_asset_manager else 0

        if self.trello_module:
            startup_data['trello_count'] = len(TRELLO_BOARDS)
        else:
            startup_data['trello_count'] = 0

        startup_data['pdf_count'] = len(self.pdf_monitor_module.configs) if self.pdf_monitor_module else 0
        startup_data['role_dependency_count'] = (
            len(self.role_dependency_module.dependencies) if self.role_dependency_module else 0
        )

        await DiscordLogger.send_startup_notification(startup_data)

    # ------------------------------------------------------------------
    # Main run loop
    # ------------------------------------------------------------------

    async def run(self):
        """Main bot loop: loads groups and starts all modules."""
        self.start_time = datetime.now()

        try:
            stats_manager.reset()
        except Exception as e:
            print(f"[STATS] Error resetting statistics on startup: {e}")

        for _attempt in range(1, 4):
            try:
                self.groups = await load_groups()
                break
            except Exception as e:
                safe_create_task(send_to_any_log("critical",
                    f"Error loading groups (attempt {_attempt}/3): {e}",
                    emoji=LogEmojis.CRITICAL, targets=["console", "file"]))
                if _attempt < 3:
                    await asyncio.sleep(30)
                else:
                    reason = f"Failed to load groups after 3 attempts: {e}"
                    await self.request_graceful_restart(reason, delay=30.0)
                    return

        for group in self.groups:
            screen_name = group.get('platform_id')
            channel_id = group.get('discord_channel_id')
            if screen_name and channel_id:
                self.group_mappings[screen_name] = int(channel_id)
                channel = self.discord_client.get_channel(int(channel_id))
                channel_info = f"'{channel.name}' ({channel_id})" if channel else str(channel_id)
                safe_create_task(send_to_any_log("info", f"Channel {channel_info} linked to group {screen_name}",
                                                 emoji=LogEmojis.INFO, targets=["console", "file"]))
            else:
                safe_create_task(send_to_any_log("error",
                    f"No screen_name or channel_id for group {group.get('name')}",
                    emoji=LogEmojis.ERROR, targets=["console", "file"]))

        if Config.ENABLE_VK_LIVE_MONITORING:
            try:
                from modules.vk_live.live_config import load_live_configs
                live_configs = await load_live_configs()
                for live_config in live_configs:
                    screen_name = live_config.get('platform_id')
                    channel_id = live_config.get('discord_channel_id')
                    if screen_name and channel_id:
                        self.group_mappings[screen_name] = int(channel_id)
                        channel = self.discord_client.get_channel(int(channel_id))
                        channel_info = f"'{channel.name}' ({channel_id})" if channel else str(channel_id)
                        safe_create_task(send_to_any_log("info",
                            f"Channel {channel_info} linked to stream {screen_name}",
                            emoji=LogEmojis.INFO, targets=["console", "file"]))
                    else:
                        safe_create_task(send_to_any_log("error",
                            f"No screen_name or channel_id for stream {live_config.get('name')}",
                            emoji=LogEmojis.ERROR, targets=["console", "file"]))
            except Exception as e:
                safe_create_task(send_to_any_log("error", f"Error loading stream configs: {e}",
                                                 emoji=LogEmojis.ERROR, targets=["console", "file"]))

        await self.discord_client.wait_until_ready()
        safe_create_task(send_to_any_log("info", BotStrings.LOG_CLIENT_READY,
                                         emoji=LogEmojis.CONNECTING, targets=["console", "file"]))

        self.discord_bot.start()

        if Config.ENABLE_VK_WALL_MONITORING:
            await self.vk_wall_manager.start_all()

        # Standalone modules
        for attr in self.STANDALONE_MODULE_ATTRS:
            module = getattr(self, attr, None)
            if module and hasattr(module, "start"):
                await module.start()

        # Platform managers
        for attr_name, _, _, _, _ in self.MANAGER_REGISTRY:
            manager = getattr(self, attr_name, None)
            if manager:
                if hasattr(manager, "start_all"):
                    await manager.start_all()
                elif hasattr(manager, "start"):
                    await manager.start()

        await self.send_startup_notification()

        from modules_utils.heartbeat_manager import HeartbeatManager
        HeartbeatManager.start(self)
        safe_create_task(self._auto_restart_on_zero_monitors())
        safe_create_task(self._scheduled_periodic_restart())

        try:
            from modules_utils.selenium_helper import SeleniumHelper
            safe_create_task(SeleniumHelper.run_periodic_cleanup_task())
        except Exception as e:
            print(f"[Selenium Auto-Clean] Failed to start cleanup worker: {e}")

        while True:
            await asyncio.sleep(60)

    # ------------------------------------------------------------------
    # Maintenance workers
    # ------------------------------------------------------------------

    async def _auto_restart_on_zero_monitors(self):
        """Restarts bot if all monitors stopped."""
        from modules_utils.task_scheduler import scheduler

        await asyncio.sleep(300)

        check_interval = 60
        while True:
            try:
                expected_any = Config.ENABLE_VK_WALL_MONITORING or any(
                    getattr(Config, config_flag, False)
                    for _, config_flag, _, _, _ in self.MANAGER_REGISTRY
                    if config_flag != "ENABLE_TRELLO_MODULE"
                )
                if not expected_any:
                    await asyncio.sleep(check_interval)
                    continue

                all_tasks = scheduler.tasks
                active_tasks = [name for name, t in all_tasks.items() if not t.done()]

                if len(all_tasks) > 0 and len(active_tasks) == 0:
                    reason = "Emergency restart: 0 active monitors detected while tasks exist in scheduler."
                    await send_to_any_log("critical", reason, emoji=LogEmojis.CRITICAL,
                                         targets=["console", "file"])
                    await self.request_graceful_restart(reason, delay=30.0)
            except Exception as e:
                print(f"[AUTO-RESTART] Error in check loop: {e}")

            await asyncio.sleep(check_interval)

    async def _scheduled_periodic_restart(self):
        """Scheduled periodic restart."""
        if not Config.USE_AUTO_RESTART:
            return

        interval_min = Config.AUTO_RESTART_INTERVAL_MINUTES
        if not interval_min or interval_min <= 0:
            return

        interval_sec = interval_min * 60
        await send_to_any_log("info",
            BotStrings.LOG_SCHEDULED_RESTART.format(interval_min=interval_min, interval_sec=interval_sec),
            emoji=LogEmojis.INFO, targets=["console", "file"])

        await asyncio.sleep(interval_sec)

        reason = BotStrings.LOG_SCHEDULED_RESTART_REASON.format(interval_min=interval_min)
        await send_to_any_log("info", reason, emoji=LogEmojis.INFO, targets=["console", "file"])
        await self.request_graceful_restart(reason)

    # ------------------------------------------------------------------
    # Shutdown
    # ------------------------------------------------------------------

    async def stop(self, reason: str = None):
        """Stops bot and all modules."""
        self._started = False

        from modules_utils.heartbeat_manager import HeartbeatManager
        HeartbeatManager.stop()

        if reason:
            RestartHelper.save_stop_reason(reason)

        await self.vk_wall_manager.stop_all()

        # Stop standalone modules
        for attr in self.STANDALONE_MODULE_ATTRS:
            module = getattr(self, attr, None)
            if module and hasattr(module, "stop"):
                await module.stop()

        # Stop managers
        for attr_name, _, _, _, _ in self.MANAGER_REGISTRY:
            manager = getattr(self, attr_name, None)
            if manager:
                if hasattr(manager, "stop_all"):
                    await manager.stop_all()
                elif hasattr(manager, "stop"):
                    await manager.stop()

        await HttpClient.close_session()

        if not Config.IS_LOCAL_LAUNCH:
            try:
                await StatsServer.stop()
            except Exception as e:
                print(f"DEBUG: Error in StatsServer.stop(): {e}")

        await cancel_all_tracked_tasks()

        await scheduler.stop_all()

        if self.discord_client:
            try:
                if getattr(self.discord_client, "loop", MISSING) is not MISSING:
                    if not self.discord_client.is_closed():
                        await self.discord_client.close()
                else:
                    await send_to_any_log("debug",
                        "Discord client loop not initialized, close skipped",
                        targets=["console"])
            except Exception as e:
                print(f"DEBUG: Error closing discord_client: {e}")

    # ------------------------------------------------------------------
    # Graceful restart / shutdown
    # ------------------------------------------------------------------

    async def request_graceful_restart(self, reason: str, delay: float = 0.0) -> None:
        """Graceful restart: stops bot and signals run_forever() to restart main()."""
        if self._graceful_exit_in_progress:
            return
        self._graceful_exit_in_progress = True

        await send_to_any_log("info",
            BotStrings.LOG_GRACEFUL_RESTART.format(reason=reason),
            emoji=LogEmojis.INFO, targets=["console", "file"])

        RestartHelper.save_stop_reason(reason)
        RestartHelper._restart_requested = True
        RestartHelper._delay_before_start = max(0.0, delay)

        await asyncio.sleep(1)
        await self.stop()

    async def request_graceful_shutdown(self, reason: str) -> None:
        """Graceful shutdown: stops bot without relaunching."""
        if self._graceful_exit_in_progress:
            return
        self._graceful_exit_in_progress = True

        await send_to_any_log("info",
            BotStrings.LOG_GRACEFUL_SHUTDOWN.format(reason=reason),
            emoji=LogEmojis.INFO, targets=["console", "file"])

        RestartHelper.save_stop_reason(reason)
        RestartHelper._shutdown_requested = True

        await asyncio.sleep(1)
        await self.stop()
