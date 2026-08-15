# content_processing/attachment_counter.py
from typing import Dict, Any, List, Tuple

def count_attachments_by_type(attachments: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    """
    Группирует вложения по их типу и возвращает словарь.
    Ключ - тип вложения (photo, video, audio и т.д.), значение - список всех вложений этого типа.
    """
    grouped = {}
    for att in attachments:
        att_type = att["type"]
        if att_type not in grouped:
            grouped[att_type] = []
        grouped[att_type].append(att)
    return grouped

def get_attachment_index_info(att_type: str, current_attachment: Dict[str, Any], grouped_attachments: Dict[str, List[Dict[str, Any]]]) -> Tuple[int, int]:
    """
    Возвращает кортеж (current_index, total_count) для данного вложения в его группе.
    Например, для второго видео из трех вернет (2, 3).
    Индексация начинается с 1.
    """
    if att_type not in grouped_attachments:
        return 1, 1

    att_list = grouped_attachments[att_type]
    total_count = len(att_list)

    # Находим индекс текущего вложения в списке.
    try:
        # Пробуем найти по уникальному идентификатору
        if att_type in ["photo", "video", "clip", "audio", "doc", "market"] and "id" in current_attachment:
            current_index = next(i for i, att in enumerate(att_list, 1) if att.get("id") == current_attachment.get("id"))
        else:
            # Fallback: поиск по позиции в списке
            current_index = att_list.index(current_attachment) + 1
    except (StopIteration, ValueError):
        # Если не удалось определить точный индекс, используем 1.
        current_index = 1

    return current_index, total_count