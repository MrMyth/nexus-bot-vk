# hash_utils.py
import re
import difflib

def normalize_text(text: str) -> str:
    """
    Нормализует текст для сравнения:
    - Удаляет пробелы по краям
    - Заменяет все виды переносов строк на \n
    - Удаляет невидимые символы (BOM, zero-width space и т.д.)
    """
    if not text:
        return ""
    
    # Удаляем невидимые символы
    text = re.sub(r'[\u200b\u200c\u200d\ufeff]', '', text)
    
    # Нормализуем переносы строк
    text = text.replace('\r\n', '\n').replace('\r', '\n')
    
    # Удаляем лишние пробелы в конце строк
    text = "\n".join([line.rstrip() for line in text.split('\n')])
    
    return text.strip()

def get_added_text(old_text: str, new_text: str) -> str:
    """
    Возвращает текст, который был добавлен в new_text по сравнению с old_text.
    Использует построчный diff: возвращает только строки, присутствующие в новой версии,
    но отсутствующие в старой.
    """
    old_lines = old_text.splitlines(keepends=True)
    new_lines = new_text.splitlines(keepends=True)

    added_parts = []
    for line in difflib.ndiff(old_lines, new_lines):
        if line.startswith('+ '):
            added_parts.append(line[2:])

    return "".join(added_parts).strip()


def get_attachments_hash(attachments) -> str:
    """
    Генерирует строковый хеш вложений для сравнения.
    Используется для определения, изменились ли вложения поста.
    """
    if not attachments:
        return ""
    
    # Сортируем по типу и ID для стабильности
    # Для ссылок используем URL, так как у них нет ID
    def get_att_id(a):
        if not isinstance(a, dict):
            return str(a)[:50]
        att_type = a['type']
        att_data = a.get(att_type, {})
        if not isinstance(att_data, dict):
            return str(att_data)[:50]
        if att_type == 'link':
            return att_data.get('url', '0')
        return str(att_data.get('id', a.get('id', '0')))

    valid_atts = [a for a in attachments if isinstance(a, dict) and 'type' in a]
    sorted_atts = sorted(valid_atts, key=lambda x: (x['type'], get_att_id(x)))
    
    hash_parts = [f"{a['type']}:{get_att_id(a)}" for a in sorted_atts]
    return "|".join(hash_parts)
