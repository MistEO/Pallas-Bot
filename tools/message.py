import json
from nonebot.adapters.cqhttp import MessageSegment, Message


def msg2str(msg: dict) -> str:
    res = []
    item: MessageSegment
    for item in msg['message']:
        data: dict = item.__dict__
        if data['type'] == 'image':
            del data['data']['url']
        res.append(data)
    return json.dumps(res)


def str2msg(s: str) -> Message:
    items: list = json.loads(s)
    msg = Message()
    item: dict
    for item in items:
        msg.append(MessageSegment(type=item['type'], data=item['data']))
    return msg

