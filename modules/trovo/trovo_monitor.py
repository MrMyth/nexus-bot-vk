# modules/trovo/trovo_monitor.py
import asyncio
from typing import Dict, Any, Optional, List
from log_system.logger_helper import send_to_any_log
from constants.emojis import LogEmojis
from settings.config import Config
from modules_utils.base_stream_monitor import BaseStreamMonitor
from modules_utils.generic_stream_database import GenericStreamDatabase
from settings.data_files import Files

class TrovoMonitor(BaseStreamMonitor):
    """Монитор стримов для Trovo."""

    def __init__(self, platform_name: str, config: Dict[str, Any], discord_bot, db_helper: Optional[GenericStreamDatabase] = None):
        super().__init__(platform_name, config, discord_bot, db_helper)

    async def fetch_current_streams(self) -> List[Dict[str, Any]]:
        """Получает статус стрима Trovo, заходя на страницу канала через Selenium."""
        url = f"https://trovo.live/s/{self.platform_id}"
        streams = []
        
        try:
            from modules_utils.selenium_helper import SeleniumHelper
            from bs4 import BeautifulSoup
            
            # Запускаем headless-браузер с отдельной изолированной папкой для профиля
            html_source = await asyncio.to_thread(
                SeleniumHelper.fetch_page_source, 
                url, 
                f"trovo_{self.platform_id}_profile",
                6.0  # Trovo может быть тяжелым, даем время на гидрацию и рендеринг
            )
            
            if html_source:
                soup = BeautifulSoup(html_source, "html.parser")
                
                # 1. Проверяем оффлайн-признаки на странице
                text_content = soup.get_text()
                is_offline = False
                
                # Признаки оффлайна на Trovo
                offline_markers = [
                    "Nothing to watch here",
                    "It's quiet... and lonely",
                    "it_is_quiet_and_lonely",
                    "Nothing to watch"
                ]
                for marker in offline_markers:
                    if marker in text_content:
                        is_offline = True
                        break
                
                if not is_offline:
                    # Канал онлайн!
                    # Попробуем вытащить мета-данные
                    og_title = soup.find("meta", property="og:title")
                    author = og_title.get("content") if og_title else self.platform_id
                    
                    # Попробуем найти название стрима
                    title = "Прямой эфир на Trovo"
                    # Ищем подходящие селекторы для названия стрима
                    title_el = soup.select_one(".live-title, .stream-title, .title-text, .stream-title-text, [class*='title-text'], [class*='live-title']")
                    if title_el:
                        title = title_el.get_text().strip()
                    else:
                        # Fallback на заголовок страницы
                        title_tag = soup.find("title")
                        if title_tag:
                            title_text = title_tag.get_text().strip()
                            if title_text and title_text != self.platform_id:
                                title = title_text
                    
                    # Попробуем найти категорию/игру
                    game = "Trovo Category"
                    game_el = soup.select_one(".game-name, .category-name, .game-tag, [class*='game-name'], [class*='category-name']")
                    if game_el:
                        game = game_el.get_text().strip()
                    
                    # Попробуем найти зрителей
                    viewers = 0
                    viewers_el = soup.select_one(".viewer-num, .viewers, .watching-num, [class*='viewer-num'], [class*='watcher-num']")
                    if viewers_el:
                        try:
                            # Оставляем только цифры
                            v_text = "".join(filter(str.isdigit, viewers_el.get_text()))
                            if v_text:
                                viewers = int(v_text)
                        except Exception:
                            pass
                            
                    # Попробуем найти превью-картинку
                    image = None
                    og_image = soup.find("meta", property="og:image")
                    if og_image:
                        image = og_image.get("content")
                    
                    # Сгенерируем уникальный stream_id на основе платформы и времени/айди
                    stream_id = f"trovo_{self.platform_id}"
                    
                    streams.append({
                        "stream_id": stream_id,
                        "title": title,
                        "url": url,
                        "author": author,
                        "game": game,
                        "viewers": viewers,
                        "image": image
                    })
                    
                    await send_to_any_log(
                        "success", 
                        f"[Trovo {self.platform_id}] Selenium successfully detected active stream: {title} ({game})", 
                        emoji=LogEmojis.SUCCESS
                    )
        except Exception as e:
            await send_to_any_log(
                "error", 
                f"Error monitoring Trovo via Selenium ({self.platform_id}): {e}", 
                emoji=LogEmojis.ERROR
            )
            
        return streams
