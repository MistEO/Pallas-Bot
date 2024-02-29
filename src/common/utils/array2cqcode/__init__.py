import json

from .message_segment import BaseMessageSegment
from typing import Any


def try_convert_to_cqcode(data: Any) -> str | Any:
    try:
        msg = json.loads(data)
        if not isinstance(msg, list):
            return msg
    except TypeError:
        if not isinstance(data, list):
            return data
        msg = data
    except json.JSONDecodeError:
        return data
    except:
        return data
    cqmessage = ''
    for seg in msg:
        cqmessage += BaseMessageSegment(**seg).cqcode
    return cqmessage
