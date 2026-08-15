# modules_utils/mirrors_resolver.py
"""
Единая точка разрешения "зеркал" (ссылок на другие платформы, где идёт та же
трансляция/публикуется то же видео) для всех каналов уведомлений (Discord embed,
Discord текст, Telegram текст, Telegram inline-кнопки).

Поддерживает 2 формата конфига `mirrors` в JSON канала:

1) Старый плоский формат (обратная совместимость) — применяется только к стримам,
   без учёта игры:
   "mirrors": {"Twitch": "https://twitch.tv/...", "VKVideo": "https://..."}
   или список: [{"platform": "Twitch", "url": "..."}]

2) Новый формат — раздельные зеркала для стримов и видео, с опциональным
   переопределением по игре (точное совпадение названия игры, без учёта регистра):
   "mirrors": {
       "stream": {
           "default": {"Twitch": "https://twitch.tv/...", "VKVideo": "https://..."},
           "by_game": {
               "GTA V": {"Twitch": "https://twitch.tv/...-gta"},
               "Just Chatting": {"Twitch": "https://twitch.tv/...-chat"}
           }
       },
       "video": {
           "default": {"Twitch": "https://twitch.tv/videos/..."},
           "by_game": {}
       }
   }

   Если для текущей игры в `by_game` нет точного совпадения — используется `default`.
   Секции `stream`/`video` необязательны: можно задать только одну из них.
"""
from typing import Any, Dict, List, Optional, Tuple


def _normalize_mirrors(raw: Any) -> List[Tuple[str, str]]:
    """Приводит словарь {платформа: url} или список [{"platform":..,"url":..}] к списку кортежей."""
    result: List[Tuple[str, str]] = []
    if isinstance(raw, dict):
        for plat_name, plat_url in raw.items():
            if plat_url:
                result.append((str(plat_name), str(plat_url)))
    elif isinstance(raw, list):
        for item in raw:
            if isinstance(item, dict) and item.get("platform") and item.get("url"):
                result.append((str(item["platform"]), str(item["url"])))
    return result


def resolve_mirrors(config: Dict[str, Any], is_video: bool = False, game: Optional[str] = None) -> List[Tuple[str, str]]:
    """
    Возвращает список (название_платформы, url) зеркал, применимых к текущему
    уведомлению, с учётом того, стрим это или видео, и с учётом игры (если задана
    привязка по игре в новом формате конфига).
    """
    raw_mirrors = config.get("mirrors")
    if not raw_mirrors:
        return []

    is_new_format = isinstance(raw_mirrors, dict) and ("stream" in raw_mirrors or "video" in raw_mirrors)

    if is_new_format:
        section = raw_mirrors.get("video" if is_video else "stream")
        if not isinstance(section, dict):
            return []

        by_game = section.get("by_game")
        chosen = None
        if game and isinstance(by_game, dict):
            game_normalized = game.strip().lower()
            for game_key, mirrors_for_game in by_game.items():
                if isinstance(game_key, str) and game_key.strip().lower() == game_normalized:
                    chosen = mirrors_for_game
                    break

        if chosen is None:
            chosen = section.get("default")

        return _normalize_mirrors(chosen)

    # Старый плоский формат: игнорируем игру, применяем только к стримам
    # (сохраняем поведение, существовавшее до появления раздельных зеркал для видео).
    if is_video:
        return []
    return _normalize_mirrors(raw_mirrors)
