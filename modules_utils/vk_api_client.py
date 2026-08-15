# modules_utils/vk_api_client.py
import aiohttp
import asyncio
import re
from typing import Dict, Any, List, Optional
from log_system.logger_helper import send_to_any_log
from constants.emojis import LogEmojis
from settings.config import Config
from constants.base import VKAPI, VKConstants
from modules_utils.group_cache import get_cached_id, cache_id

class VKAPIException(Exception):
    """Исключение для ошибок VK API."""
    def __init__(self, error_code: int, error_msg: str):
        self.error_code = error_code
        self.error_msg = error_msg
        super().__init__(f"VK API Error {error_code}: {error_msg}")


class VKApiClient:
    """Универсальный клиент для работы с VK API (официальным и VK Video/Live)."""

    @staticmethod
    async def call_api(method: str, params: Dict[str, Any], session: Optional[aiohttp.ClientSession] = None, token: Optional[str] = None, silent_errors: bool = False, raise_on_error: bool = False, _rate_limit_attempt: int = 0) -> Optional[Dict[str, Any]]:
        """Универсальный метод для вызова официального VK API с использованием общего HttpClient."""
        from modules_utils.helpers import clean_vk_token
        actual_token = clean_vk_token(token or Config.VK_TOKEN)
        if not actual_token:
            return None

        from modules_utils.http_client import HttpClient
        url = f"{VKAPI.BASE_URL}/{method}"
        api_params = params.copy()
        api_params["access_token"] = actual_token
        api_params["v"] = getattr(VKAPI, "VERSION", "5.199")

        max_retries = getattr(VKAPI, "MAX_RETRIES", 3)
        
        # Используем HttpClient.get который уже умеет в ретраи по 429 и 5xx
        data = await HttpClient.get(url, params=api_params, max_retries=max_retries)
        
        if not data or not isinstance(data, dict):
            return None

        if "error" in data:
            error = data["error"]
            error_code = error.get("error_code")
            error_msg = error.get("error_msg", "Unknown error")
            
            # If authorization/access error occurred when calling with custom token,
            # and this custom token differs from global token, retry the request with global token
            if token and token != Config.VK_TOKEN and Config.VK_TOKEN and not raise_on_error:
                is_auth_error = error_code in [5, 15, 27, 28] or "group auth" in error_msg.lower() or "revoke" in error_msg.lower()
                if is_auth_error:
                    if not silent_errors:
                        await send_to_any_log("warning", f"VK API call ({method}) failed with custom token auth error ({error_msg}). Retrying with global VK token...", emoji=LogEmojis.WARNING)
                    return await VKApiClient.call_api(method, params, session=session, token=Config.VK_TOKEN, silent_errors=silent_errors, raise_on_error=raise_on_error)

            if raise_on_error:
                raise VKAPIException(error_code, error_msg)

            # VK rate limit errors (come as 200 OK + error in JSON, not HTTP 429)
            if error_code in [6, 29] and _rate_limit_attempt < 2:
                delay = Config.VK_RATE_LIMIT_RETRY_DELAY * (2 ** _rate_limit_attempt)
                if not silent_errors:
                    await send_to_any_log("warning",
                        f"VK API Rate Limit ({method}): {error_msg}. Retry in {delay}s (attempt {_rate_limit_attempt + 1}/2)...",
                        emoji=LogEmojis.WARNING)
                await asyncio.sleep(delay)
                return await VKApiClient.call_api(
                    method, params,
                    session=session, token=token,
                    silent_errors=silent_errors, raise_on_error=raise_on_error,
                    _rate_limit_attempt=_rate_limit_attempt + 1
                )
            elif error_code in [6, 29]:
                if not silent_errors:
                    await send_to_any_log("warning",
                        f"VK API Rate Limit ({method}): retry attempts exhausted",
                        emoji=LogEmojis.WARNING)
                return None
            
            if not silent_errors:
                await send_to_any_log("error", f"VK API Error ({method}): {error_msg}", emoji=LogEmojis.ERROR)
            return None
            
        return data.get("response")

    @staticmethod
    def normalize_group_id(screen_name: str) -> Optional[int]:
        """Normalizes group or user ID, handling prefixes and numeric values."""
        if screen_name is None:
            return None
        s = str(screen_name).strip()
        pattern = rf'^(?:{"|".join(VKConstants.GROUP_PREFIXES)})(\d+)

    @staticmethod
    async def get_group_avatar(group_id: Any, session: Optional[aiohttp.ClientSession] = None, token: Optional[str] = None) -> Optional[str]:
        """Получает аватар группы или пользователя по ID."""
        try:
            val_id = int(group_id) if group_id is not None else None
        except (ValueError, TypeError):
            return None
            
        if val_id is None:
            return None
            
        cached = get_cached_id(str(val_id), namespace="avatar")
        if cached:
            return cached

        if val_id < 0:
            # Отрицательный ID -> Группа
            g_id = str(abs(val_id))
            params = {
                "group_ids": g_id,
                "fields": VKAPI.GROUP_PHOTO_FIELD
            }
            response = await VKApiClient.call_api("groups.getById", params, session=session, token=token)
            if response and len(response) > 0:
                group_info = response[0]
                avatar_url = group_info.get(VKAPI.GROUP_PHOTO_FIELD)
                if avatar_url:
                    cache_id(str(val_id), avatar_url, namespace="avatar")
                    return avatar_url
        else:
            # Положительный ID -> Пользователь
            u_id = str(val_id)
            params = {
                "user_ids": u_id,
                "fields": "photo_200"
            }
            response = await VKApiClient.call_api("users.get", params, session=session, token=token)
            if response and len(response) > 0:
                user_info = response[0]
                avatar_url = user_info.get("photo_200")
                if avatar_url:
                    cache_id(str(val_id), avatar_url, namespace="avatar")
                    return avatar_url
        return None

    @staticmethod
    async def is_live_video(video_owner_id: int, video_id: int, session: Optional[aiohttp.ClientSession] = None) -> bool:
        """Проверяет, идет ли сейчас прямой эфир (для конкретного видео)."""
        params = {
            "videos": f"{video_owner_id}_{video_id}"
        }
        response = await VKApiClient.call_api("video.get", params, session=session)
        
        if response and response.get("count", 0) > 0:
            video = response["items"][0]
            if video.get("owner_id") == video_owner_id:
                return video.get("is_live", False) and video.get("live_status") == "started"
        return False

    @staticmethod
    async def get_vk_com_live_streams(
        owner_id: int,
        session: Optional[aiohttp.ClientSession] = None,
        token: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Получает текущие активные трансляции для группы или пользователя ВКонтакте через официальный API."""
        params = {
            "owner_id": owner_id,
            "count": 10,
            "filters": "live",
            "extended": 1
        }
        
        response = await VKApiClient.call_api("video.get", params, session=session, token=token, silent_errors=True)
        if not response:
            return []
            
        items = response.get("items", [])
        streams = []
        for item in items:
            is_live = item.get("is_live") == 1 or item.get("live_status") == "started"
            if is_live and item.get("live_status") != "finished":
                stream_id = str(item.get("id"))
                owner_id_val = item.get("owner_id")
                
                preview_url = None
                image_items = item.get("image") or []
                if image_items:
                    preview_url = image_items[-1].get("url")
                elif item.get("first_frame"):
                    first_frame_items = item.get("first_frame") or []
                    if first_frame_items:
                        preview_url = first_frame_items[-1].get("url")
                
                viewers = item.get("spectators", item.get("views", 0))
                
                streams.append({
                    "stream_id": stream_id,
                    "title": item.get("title", "Прямой эфир VK.com"),
                    "url": f"https://vk.com/video{owner_id_val}_{stream_id}",
                    "author": item.get("owner_name") or str(owner_id),
                    "game": "VK.com Live",
                    "viewers": viewers,
                    "image": preview_url,
                    "description": item.get("description", "")
                })
        return streams

    @staticmethod
    async def get_live_status_with_session(
        session: Any, # Оставляем для совместимости подписи, но не используем
        screen_name: str
    ) -> Optional[Dict[str, Any]]:
        """Проверяет статус стрима через новый API vkvideo.ru/vklive."""
        from modules_utils.http_client import HttpClient
        url = f"https://api.{VKAPI.BASE_URL_VK_LIVE}/v1/channel/{screen_name}/stream/all/"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "application/json"
        }
        
        try:
            data = await HttpClient.get(url, headers=headers, timeout=10)
            if data and isinstance(data, dict):
                return data
            return None
        except Exception:
            return None

    @staticmethod
    async def get_channel_videos_with_session(
        session: Any,
        channel_id: int,
        count: int = 5
    ) -> List[Dict[str, Any]]:
        """Получает видео канала через vkvideo.ru API."""
        from modules_utils.http_client import HttpClient
        url = f"https://{VKAPI.BASE_URL_VK_VIDEO}/api/v1/channels/{channel_id}/videos"
        params = {"limit": count}
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        try:
            data = await HttpClient.get(url, params=params, headers=headers, timeout=15)
            if data and isinstance(data, dict):
                return data.get("items", [])
            return []
        except Exception:
            return []

    # Остальные методы (get_channel_videos_vk_api, get_channel_info_with_session, get_video_by_id)
    # уже вызывают call_api(), который теперь использует HttpClient.

    @staticmethod
    async def get_channel_videos_vk_api(
        session: aiohttp.ClientSession, 
        owner_id: Any, 
        count: int = 1
    ) -> List[Dict[str, Any]]:
        """Получает последние видео канала используя официальный VK API."""
        if isinstance(owner_id, str) and not owner_id.lstrip('-').isdigit():
            info = await VKApiClient.get_channel_info_with_session(session, owner_id)
            if not info:
                return []
            owner_param = str(info['id'])
            if info['type'] == 'group':
                owner_param = f"-{owner_param}"
        else:
            owner_param = str(owner_id) if owner_id else ""

        params = {
            'owner_id': owner_param,
            'count': count,
            'extended': 1
        }
        
        response = await VKApiClient.call_api("video.get", params, session=session)
        if response:
            items = response.get('items', [])
            profiles = response.get('profiles', [])
            groups = response.get('groups', [])
            
            for video in items:
                v_owner_id = video.get('owner_id', 0)
                if v_owner_id > 0:
                    owner_info = next((p for p in profiles if p.get('id') == v_owner_id), {})
                    video['owner_name'] = f"{owner_info.get('first_name', '')} {owner_info.get('last_name', '')}".strip()
                else:
                    group_info = next((g for g in groups if g.get('id') == abs(v_owner_id)), {})
                    video['owner_name'] = group_info.get('name', '')
            return items
        return []

    @staticmethod
    async def get_channel_info_with_session(
        session: aiohttp.ClientSession, 
        screen_name: str
    ) -> Optional[Dict[str, Any]]:
        """Получает расширенную информацию о канале/пользователе (ID, тип, имя)."""
        params = {'screen_name': screen_name}
        resolved = await VKApiClient.call_api("utils.resolveScreenName", params, session=session, silent_errors=True)
        
        if not resolved:
            # Fallback для групповых токенов
            try:
                g_resp = await VKApiClient.call_api("groups.getById", {"group_ids": screen_name, "fields": "name,screen_name"}, session=session, silent_errors=True)
                if g_resp and len(g_resp) > 0:
                    return {
                        'id': g_resp[0]['id'],
                        'name': g_resp[0]['name'],
                        'screen_name': g_resp[0]['screen_name'],
                        'type': 'group'
                    }
            except Exception:
                pass

            try:
                u_resp = await VKApiClient.call_api("users.get", {"user_ids": screen_name, "fields": "first_name,last_name,screen_name"}, session=session, silent_errors=True)
                if u_resp and len(u_resp) > 0:
                    return {
                        'id': u_resp[0]['id'],
                        'name': f"{u_resp[0]['first_name']} {u_resp[0]['last_name']}",
                        'screen_name': u_resp[0].get('screen_name', ''),
                        'type': 'user'
                    }
            except Exception:
                pass
            return None
            
        obj_id = resolved.get('object_id')
        obj_type = resolved.get('type')
        
        if obj_type == 'group':
            group_params = {
                'group_ids': obj_id,
                'fields': 'name,screen_name'
            }
            g_resp = await VKApiClient.call_api("groups.getById", group_params, session=session)
            if g_resp:
                return {
                    'id': g_resp[0]['id'],
                    'name': g_resp[0]['name'],
                    'screen_name': g_resp[0]['screen_name'],
                    'type': 'group'
                }
        elif obj_type == 'user':
            user_params = {
                'user_ids': obj_id,
                'fields': 'first_name,last_name,screen_name'
            }
            u_resp = await VKApiClient.call_api("users.get", user_params, session=session)
            if u_resp:
                return {
                    'id': u_resp[0]['id'],
                    'name': f"{u_resp[0]['first_name']} {u_resp[0]['last_name']}",
                    'screen_name': u_resp[0].get('screen_name', ''),
                    'type': 'user'
                }
        return None

    @staticmethod
    async def get_video_by_id(
        session: aiohttp.ClientSession,
        videos: str,
        owner_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Получает информацию о видео по его идентификатору(ам)."""
        params = {
            'videos': videos,
            'extended': 1
        }
        if owner_id and '_' not in videos:
            params['owner_id'] = owner_id
            
        response = await VKApiClient.call_api("video.get", params, session=session)
        if response:
            return response.get('items', [])
        return []

        m = re.match(pattern, s, re.IGNORECASE)
        if m:
            return -abs(int(m.group(1)))
        
        user_pattern = rf'^(?:{"|".join(VKConstants.USER_PREFIXES)})(\d+)

    @staticmethod
    async def get_group_avatar(group_id: Any, session: Optional[aiohttp.ClientSession] = None, token: Optional[str] = None) -> Optional[str]:
        """Получает аватар группы или пользователя по ID."""
        try:
            val_id = int(group_id) if group_id is not None else None
        except (ValueError, TypeError):
            return None
            
        if val_id is None:
            return None
            
        cached = get_cached_id(str(val_id), namespace="avatar")
        if cached:
            return cached

        if val_id < 0:
            # Отрицательный ID -> Группа
            g_id = str(abs(val_id))
            params = {
                "group_ids": g_id,
                "fields": VKAPI.GROUP_PHOTO_FIELD
            }
            response = await VKApiClient.call_api("groups.getById", params, session=session, token=token)
            if response and len(response) > 0:
                group_info = response[0]
                avatar_url = group_info.get(VKAPI.GROUP_PHOTO_FIELD)
                if avatar_url:
                    cache_id(str(val_id), avatar_url, namespace="avatar")
                    return avatar_url
        else:
            # Положительный ID -> Пользователь
            u_id = str(val_id)
            params = {
                "user_ids": u_id,
                "fields": "photo_200"
            }
            response = await VKApiClient.call_api("users.get", params, session=session, token=token)
            if response and len(response) > 0:
                user_info = response[0]
                avatar_url = user_info.get("photo_200")
                if avatar_url:
                    cache_id(str(val_id), avatar_url, namespace="avatar")
                    return avatar_url
        return None

    @staticmethod
    async def is_live_video(video_owner_id: int, video_id: int, session: Optional[aiohttp.ClientSession] = None) -> bool:
        """Проверяет, идет ли сейчас прямой эфир (для конкретного видео)."""
        params = {
            "videos": f"{video_owner_id}_{video_id}"
        }
        response = await VKApiClient.call_api("video.get", params, session=session)
        
        if response and response.get("count", 0) > 0:
            video = response["items"][0]
            if video.get("owner_id") == video_owner_id:
                return video.get("is_live", False) and video.get("live_status") == "started"
        return False

    @staticmethod
    async def get_vk_com_live_streams(
        owner_id: int,
        session: Optional[aiohttp.ClientSession] = None,
        token: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Получает текущие активные трансляции для группы или пользователя ВКонтакте через официальный API."""
        params = {
            "owner_id": owner_id,
            "count": 10,
            "filters": "live",
            "extended": 1
        }
        
        response = await VKApiClient.call_api("video.get", params, session=session, token=token, silent_errors=True)
        if not response:
            return []
            
        items = response.get("items", [])
        streams = []
        for item in items:
            is_live = item.get("is_live") == 1 or item.get("live_status") == "started"
            if is_live and item.get("live_status") != "finished":
                stream_id = str(item.get("id"))
                owner_id_val = item.get("owner_id")
                
                preview_url = None
                image_items = item.get("image") or []
                if image_items:
                    preview_url = image_items[-1].get("url")
                elif item.get("first_frame"):
                    first_frame_items = item.get("first_frame") or []
                    if first_frame_items:
                        preview_url = first_frame_items[-1].get("url")
                
                viewers = item.get("spectators", item.get("views", 0))
                
                streams.append({
                    "stream_id": stream_id,
                    "title": item.get("title", "Прямой эфир VK.com"),
                    "url": f"https://vk.com/video{owner_id_val}_{stream_id}",
                    "author": item.get("owner_name") or str(owner_id),
                    "game": "VK.com Live",
                    "viewers": viewers,
                    "image": preview_url,
                    "description": item.get("description", "")
                })
        return streams

    @staticmethod
    async def get_live_status_with_session(
        session: Any, # Оставляем для совместимости подписи, но не используем
        screen_name: str
    ) -> Optional[Dict[str, Any]]:
        """Проверяет статус стрима через новый API vkvideo.ru/vklive."""
        from modules_utils.http_client import HttpClient
        url = f"https://api.{VKAPI.BASE_URL_VK_LIVE}/v1/channel/{screen_name}/stream/all/"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "application/json"
        }
        
        try:
            data = await HttpClient.get(url, headers=headers, timeout=10)
            if data and isinstance(data, dict):
                return data
            return None
        except Exception:
            return None

    @staticmethod
    async def get_channel_videos_with_session(
        session: Any,
        channel_id: int,
        count: int = 5
    ) -> List[Dict[str, Any]]:
        """Получает видео канала через vkvideo.ru API."""
        from modules_utils.http_client import HttpClient
        url = f"https://{VKAPI.BASE_URL_VK_VIDEO}/api/v1/channels/{channel_id}/videos"
        params = {"limit": count}
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        try:
            data = await HttpClient.get(url, params=params, headers=headers, timeout=15)
            if data and isinstance(data, dict):
                return data.get("items", [])
            return []
        except Exception:
            return []

    # Остальные методы (get_channel_videos_vk_api, get_channel_info_with_session, get_video_by_id)
    # уже вызывают call_api(), который теперь использует HttpClient.

    @staticmethod
    async def get_channel_videos_vk_api(
        session: aiohttp.ClientSession, 
        owner_id: Any, 
        count: int = 1
    ) -> List[Dict[str, Any]]:
        """Получает последние видео канала используя официальный VK API."""
        if isinstance(owner_id, str) and not owner_id.lstrip('-').isdigit():
            info = await VKApiClient.get_channel_info_with_session(session, owner_id)
            if not info:
                return []
            owner_param = str(info['id'])
            if info['type'] == 'group':
                owner_param = f"-{owner_param}"
        else:
            owner_param = str(owner_id) if owner_id else ""

        params = {
            'owner_id': owner_param,
            'count': count,
            'extended': 1
        }
        
        response = await VKApiClient.call_api("video.get", params, session=session)
        if response:
            items = response.get('items', [])
            profiles = response.get('profiles', [])
            groups = response.get('groups', [])
            
            for video in items:
                v_owner_id = video.get('owner_id', 0)
                if v_owner_id > 0:
                    owner_info = next((p for p in profiles if p.get('id') == v_owner_id), {})
                    video['owner_name'] = f"{owner_info.get('first_name', '')} {owner_info.get('last_name', '')}".strip()
                else:
                    group_info = next((g for g in groups if g.get('id') == abs(v_owner_id)), {})
                    video['owner_name'] = group_info.get('name', '')
            return items
        return []

    @staticmethod
    async def get_channel_info_with_session(
        session: aiohttp.ClientSession, 
        screen_name: str
    ) -> Optional[Dict[str, Any]]:
        """Получает расширенную информацию о канале/пользователе (ID, тип, имя)."""
        params = {'screen_name': screen_name}
        resolved = await VKApiClient.call_api("utils.resolveScreenName", params, session=session, silent_errors=True)
        
        if not resolved:
            # Fallback для групповых токенов
            try:
                g_resp = await VKApiClient.call_api("groups.getById", {"group_ids": screen_name, "fields": "name,screen_name"}, session=session, silent_errors=True)
                if g_resp and len(g_resp) > 0:
                    return {
                        'id': g_resp[0]['id'],
                        'name': g_resp[0]['name'],
                        'screen_name': g_resp[0]['screen_name'],
                        'type': 'group'
                    }
            except Exception:
                pass

            try:
                u_resp = await VKApiClient.call_api("users.get", {"user_ids": screen_name, "fields": "first_name,last_name,screen_name"}, session=session, silent_errors=True)
                if u_resp and len(u_resp) > 0:
                    return {
                        'id': u_resp[0]['id'],
                        'name': f"{u_resp[0]['first_name']} {u_resp[0]['last_name']}",
                        'screen_name': u_resp[0].get('screen_name', ''),
                        'type': 'user'
                    }
            except Exception:
                pass
            return None
            
        obj_id = resolved.get('object_id')
        obj_type = resolved.get('type')
        
        if obj_type == 'group':
            group_params = {
                'group_ids': obj_id,
                'fields': 'name,screen_name'
            }
            g_resp = await VKApiClient.call_api("groups.getById", group_params, session=session)
            if g_resp:
                return {
                    'id': g_resp[0]['id'],
                    'name': g_resp[0]['name'],
                    'screen_name': g_resp[0]['screen_name'],
                    'type': 'group'
                }
        elif obj_type == 'user':
            user_params = {
                'user_ids': obj_id,
                'fields': 'first_name,last_name,screen_name'
            }
            u_resp = await VKApiClient.call_api("users.get", user_params, session=session)
            if u_resp:
                return {
                    'id': u_resp[0]['id'],
                    'name': f"{u_resp[0]['first_name']} {u_resp[0]['last_name']}",
                    'screen_name': u_resp[0].get('screen_name', ''),
                    'type': 'user'
                }
        return None

    @staticmethod
    async def get_video_by_id(
        session: aiohttp.ClientSession,
        videos: str,
        owner_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Получает информацию о видео по его идентификатору(ам)."""
        params = {
            'videos': videos,
            'extended': 1
        }
        if owner_id and '_' not in videos:
            params['owner_id'] = owner_id
            
        response = await VKApiClient.call_api("video.get", params, session=session)
        if response:
            return response.get('items', [])
        return []

        mu = re.match(user_pattern, s, re.IGNORECASE)
        if mu:
            return abs(int(mu.group(1)))

        if re.fullmatch(r'-?\d+', s):
            return int(s)
        return None

    @staticmethod
    async def get_group_id(screen_name: str, session: Optional[aiohttp.ClientSession] = None, token: Optional[str] = None) -> Optional[int]:
        """Converts screen_name to numeric group or user ID."""
        s_name = str(screen_name).strip()
        
        cached = get_cached_id(s_name, namespace="group")
        if cached is not None:
            return cached
            
        normalized = VKApiClient.normalize_group_id(s_name)
        if isinstance(normalized, int):
            cache_id(s_name, normalized, namespace="group")
            return normalized

        params = {"screen_name": s_name}
        result = await VKApiClient.call_api("utils.resolveScreenName", params, session=session, token=token, silent_errors=True)
        
        if result:
            obj_type = result.get("type")
            obj_id = result.get("object_id")
            if obj_type == "group":
                resolved_id = -abs(obj_id)
                cache_id(s_name, resolved_id, namespace="group")
                return resolved_id
            elif obj_type == "user":
                resolved_id = abs(obj_id)
                cache_id(s_name, resolved_id, namespace="group")
                return resolved_id
            
        try:
            g_resp = await VKApiClient.call_api("groups.getById", {"group_ids": s_name}, session=session, token=token, silent_errors=True)
            if g_resp and len(g_resp) > 0:
                obj_id = g_resp[0].get("id")
                if obj_id:
                    resolved_id = -abs(obj_id)
                    cache_id(s_name, resolved_id, namespace="group")
                    return resolved_id
        except Exception:
            pass

        try:
            u_resp = await VKApiClient.call_api("users.get", {"user_ids": s_name}, session=session, token=token, silent_errors=True)
            if u_resp and len(u_resp) > 0:
                obj_id = u_resp[0].get("id")
                if obj_id:
                    resolved_id = abs(obj_id)
                    cache_id(s_name, resolved_id, namespace="group")
                    return resolved_id
        except Exception:
            pass
            
        await send_to_any_log("warning", f"Failed to find VK object ID for: {s_name}", emoji=LogEmojis.WARNING)
        return None

    @staticmethod
    async def get_group_avatar(group_id: Any, session: Optional[aiohttp.ClientSession] = None, token: Optional[str] = None) -> Optional[str]:
        """Получает аватар группы или пользователя по ID."""
        try:
            val_id = int(group_id) if group_id is not None else None
        except (ValueError, TypeError):
            return None
            
        if val_id is None:
            return None
            
        cached = get_cached_id(str(val_id), namespace="avatar")
        if cached:
            return cached

        if val_id < 0:
            # Отрицательный ID -> Группа
            g_id = str(abs(val_id))
            params = {
                "group_ids": g_id,
                "fields": VKAPI.GROUP_PHOTO_FIELD
            }
            response = await VKApiClient.call_api("groups.getById", params, session=session, token=token)
            if response and len(response) > 0:
                group_info = response[0]
                avatar_url = group_info.get(VKAPI.GROUP_PHOTO_FIELD)
                if avatar_url:
                    cache_id(str(val_id), avatar_url, namespace="avatar")
                    return avatar_url
        else:
            # Положительный ID -> Пользователь
            u_id = str(val_id)
            params = {
                "user_ids": u_id,
                "fields": "photo_200"
            }
            response = await VKApiClient.call_api("users.get", params, session=session, token=token)
            if response and len(response) > 0:
                user_info = response[0]
                avatar_url = user_info.get("photo_200")
                if avatar_url:
                    cache_id(str(val_id), avatar_url, namespace="avatar")
                    return avatar_url
        return None

    @staticmethod
    async def is_live_video(video_owner_id: int, video_id: int, session: Optional[aiohttp.ClientSession] = None) -> bool:
        """Проверяет, идет ли сейчас прямой эфир (для конкретного видео)."""
        params = {
            "videos": f"{video_owner_id}_{video_id}"
        }
        response = await VKApiClient.call_api("video.get", params, session=session)
        
        if response and response.get("count", 0) > 0:
            video = response["items"][0]
            if video.get("owner_id") == video_owner_id:
                return video.get("is_live", False) and video.get("live_status") == "started"
        return False

    @staticmethod
    async def get_vk_com_live_streams(
        owner_id: int,
        session: Optional[aiohttp.ClientSession] = None,
        token: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Получает текущие активные трансляции для группы или пользователя ВКонтакте через официальный API."""
        params = {
            "owner_id": owner_id,
            "count": 10,
            "filters": "live",
            "extended": 1
        }
        
        response = await VKApiClient.call_api("video.get", params, session=session, token=token, silent_errors=True)
        if not response:
            return []
            
        items = response.get("items", [])
        streams = []
        for item in items:
            is_live = item.get("is_live") == 1 or item.get("live_status") == "started"
            if is_live and item.get("live_status") != "finished":
                stream_id = str(item.get("id"))
                owner_id_val = item.get("owner_id")
                
                preview_url = None
                image_items = item.get("image") or []
                if image_items:
                    preview_url = image_items[-1].get("url")
                elif item.get("first_frame"):
                    first_frame_items = item.get("first_frame") or []
                    if first_frame_items:
                        preview_url = first_frame_items[-1].get("url")
                
                viewers = item.get("spectators", item.get("views", 0))
                
                streams.append({
                    "stream_id": stream_id,
                    "title": item.get("title", "Прямой эфир VK.com"),
                    "url": f"https://vk.com/video{owner_id_val}_{stream_id}",
                    "author": item.get("owner_name") or str(owner_id),
                    "game": "VK.com Live",
                    "viewers": viewers,
                    "image": preview_url,
                    "description": item.get("description", "")
                })
        return streams

    @staticmethod
    async def get_live_status_with_session(
        session: Any, # Оставляем для совместимости подписи, но не используем
        screen_name: str
    ) -> Optional[Dict[str, Any]]:
        """Проверяет статус стрима через новый API vkvideo.ru/vklive."""
        from modules_utils.http_client import HttpClient
        url = f"https://api.{VKAPI.BASE_URL_VK_LIVE}/v1/channel/{screen_name}/stream/all/"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "application/json"
        }
        
        try:
            data = await HttpClient.get(url, headers=headers, timeout=10)
            if data and isinstance(data, dict):
                return data
            return None
        except Exception:
            return None

    @staticmethod
    async def get_channel_videos_with_session(
        session: Any,
        channel_id: int,
        count: int = 5
    ) -> List[Dict[str, Any]]:
        """Получает видео канала через vkvideo.ru API."""
        from modules_utils.http_client import HttpClient
        url = f"https://{VKAPI.BASE_URL_VK_VIDEO}/api/v1/channels/{channel_id}/videos"
        params = {"limit": count}
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        try:
            data = await HttpClient.get(url, params=params, headers=headers, timeout=15)
            if data and isinstance(data, dict):
                return data.get("items", [])
            return []
        except Exception:
            return []

    # Остальные методы (get_channel_videos_vk_api, get_channel_info_with_session, get_video_by_id)
    # уже вызывают call_api(), который теперь использует HttpClient.

    @staticmethod
    async def get_channel_videos_vk_api(
        session: aiohttp.ClientSession, 
        owner_id: Any, 
        count: int = 1
    ) -> List[Dict[str, Any]]:
        """Получает последние видео канала используя официальный VK API."""
        if isinstance(owner_id, str) and not owner_id.lstrip('-').isdigit():
            info = await VKApiClient.get_channel_info_with_session(session, owner_id)
            if not info:
                return []
            owner_param = str(info['id'])
            if info['type'] == 'group':
                owner_param = f"-{owner_param}"
        else:
            owner_param = str(owner_id) if owner_id else ""

        params = {
            'owner_id': owner_param,
            'count': count,
            'extended': 1
        }
        
        response = await VKApiClient.call_api("video.get", params, session=session)
        if response:
            items = response.get('items', [])
            profiles = response.get('profiles', [])
            groups = response.get('groups', [])
            
            for video in items:
                v_owner_id = video.get('owner_id', 0)
                if v_owner_id > 0:
                    owner_info = next((p for p in profiles if p.get('id') == v_owner_id), {})
                    video['owner_name'] = f"{owner_info.get('first_name', '')} {owner_info.get('last_name', '')}".strip()
                else:
                    group_info = next((g for g in groups if g.get('id') == abs(v_owner_id)), {})
                    video['owner_name'] = group_info.get('name', '')
            return items
        return []

    @staticmethod
    async def get_channel_info_with_session(
        session: aiohttp.ClientSession, 
        screen_name: str
    ) -> Optional[Dict[str, Any]]:
        """Получает расширенную информацию о канале/пользователе (ID, тип, имя)."""
        params = {'screen_name': screen_name}
        resolved = await VKApiClient.call_api("utils.resolveScreenName", params, session=session, silent_errors=True)
        
        if not resolved:
            # Fallback для групповых токенов
            try:
                g_resp = await VKApiClient.call_api("groups.getById", {"group_ids": screen_name, "fields": "name,screen_name"}, session=session, silent_errors=True)
                if g_resp and len(g_resp) > 0:
                    return {
                        'id': g_resp[0]['id'],
                        'name': g_resp[0]['name'],
                        'screen_name': g_resp[0]['screen_name'],
                        'type': 'group'
                    }
            except Exception:
                pass

            try:
                u_resp = await VKApiClient.call_api("users.get", {"user_ids": screen_name, "fields": "first_name,last_name,screen_name"}, session=session, silent_errors=True)
                if u_resp and len(u_resp) > 0:
                    return {
                        'id': u_resp[0]['id'],
                        'name': f"{u_resp[0]['first_name']} {u_resp[0]['last_name']}",
                        'screen_name': u_resp[0].get('screen_name', ''),
                        'type': 'user'
                    }
            except Exception:
                pass
            return None
            
        obj_id = resolved.get('object_id')
        obj_type = resolved.get('type')
        
        if obj_type == 'group':
            group_params = {
                'group_ids': obj_id,
                'fields': 'name,screen_name'
            }
            g_resp = await VKApiClient.call_api("groups.getById", group_params, session=session)
            if g_resp:
                return {
                    'id': g_resp[0]['id'],
                    'name': g_resp[0]['name'],
                    'screen_name': g_resp[0]['screen_name'],
                    'type': 'group'
                }
        elif obj_type == 'user':
            user_params = {
                'user_ids': obj_id,
                'fields': 'first_name,last_name,screen_name'
            }
            u_resp = await VKApiClient.call_api("users.get", user_params, session=session)
            if u_resp:
                return {
                    'id': u_resp[0]['id'],
                    'name': f"{u_resp[0]['first_name']} {u_resp[0]['last_name']}",
                    'screen_name': u_resp[0].get('screen_name', ''),
                    'type': 'user'
                }
        return None

    @staticmethod
    async def get_video_by_id(
        session: aiohttp.ClientSession,
        videos: str,
        owner_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Получает информацию о видео по его идентификатору(ам)."""
        params = {
            'videos': videos,
            'extended': 1
        }
        if owner_id and '_' not in videos:
            params['owner_id'] = owner_id
            
        response = await VKApiClient.call_api("video.get", params, session=session)
        if response:
            return response.get('items', [])
        return []
