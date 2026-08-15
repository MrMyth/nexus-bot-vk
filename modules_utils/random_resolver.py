import random
from typing import Any, Union, List

def resolve_random_value(value: Union[Any, List[Any]]) -> Any:
    """
    Если значение — непустой список, возвращает случайный элемент.
    Иначе — возвращает само значение (даже если None).
    """
    if isinstance(value, list) and value:
        return random.choice(value)
    return value