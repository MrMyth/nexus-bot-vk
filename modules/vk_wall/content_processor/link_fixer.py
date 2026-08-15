# content_processing/link_fixer.py
import regex

class LinkFixer:
    """
    Статический класс для нормализации ссылок в тексте поста.
    """

    @staticmethod
    def fix_vk_links(text: str) -> str:
        if not text:
            return text

        # Замена http на https для доменов vk.com и vk.ru
        text = regex.sub(r'http://(vk\.com/)', r'https://\1', text, flags=regex.IGNORECASE)
        text = regex.sub(r'http://(vk\.ru/)', r'https://\1', text, flags=regex.IGNORECASE)
        
        # Замена мобильных версий на десктопные для доменов .com и .ru
        text = regex.sub(r'https?://m\.vk\.com/', r'https://vk.com/', text, flags=regex.IGNORECASE)
        text = regex.sub(r'https?://m\.vk\.ru/', r'https://vk.ru/', text, flags=regex.IGNORECASE)
        
        # Добавление https для незавершенных ссылок vk.com
        text = regex.sub(r'(?<!https?://)\b(vk\.com/[^\s<]+)', r'https://\1', text, flags=regex.IGNORECASE)
        text = regex.sub(r'(?<!https?://)\b(vk\.ru/[^\s<]+)', r'https://\1', text, flags=regex.IGNORECASE)
        
        # Обработка коротких ссылок vk.cc
        text = regex.sub(r'(?<!https?://)\b(vk\.cc/[^\s<]+)', r'https://\1', text, flags=regex.IGNORECASE)

        # Восстановление обрезанных ссылок на любые домены
        text = LinkFixer._restore_cut_links(text)

        return text

    @staticmethod
    def _restore_cut_links(text: str) -> str:
        """
        Восстанавливает обрезанные ссылки (без http/https) для любых доменов.
        Использует протокол https:// для корректного отображения и рендеринга превью в Discord.
        """
        # Паттерн для обнаружения обрезанных ссылок
        pattern = r'''
            (?:^|\s|\(|\[)  # начало строки, пробел или скобка
            (
                (?:[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)  # поддомен (опционально)
                [a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?        # домен 2-го уровня
                \.[a-zA-Z]{2,}                                       # домен верхнего уровня
                (?:/[^\s<>()\[\]{}"'\.,!?;]*)?                       # путь (опционально)
            )
            (?:$|\s|\)|\]|\.|,|!|\?)  # конец строки, пробел или пунктуация
        '''
        
        def restore_protocol(match):
            domain_with_path = match.group(1)
            
            # Пропускаем уже обработанные VK ссылки и email адреса
            if domain_with_path.startswith(('vk.com/', 'vk.ru/', 'vk.cc/')) or '@' in domain_with_path:
                return match.group(0)
            
            # Проверяем, не является ли это уже полной ссылкой
            if regex.match(r'^https?://', domain_with_path, regex.IGNORECASE):
                return match.group(0)
            
            # ВАЖНОЕ ИЗМЕНЕНИЕ: используем https:// вместо протокол-относительных URL (//),
            # так как Discord не всегда рендерит превью для // префиксов.
            restored_link = f'https://{domain_with_path}'
            
            # Заменяем в оригинальном тексте
            original_match = match.group(0)
            return original_match.replace(domain_with_path, restored_link)
        
        # Применяем восстановление ко всем найденным обрезанным ссылкам
        text = regex.sub(pattern, restore_protocol, text, flags=regex.VERBOSE | regex.IGNORECASE)
        
        return text