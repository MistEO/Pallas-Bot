from nonebot import on_message
from nonebot.adapters.cqhttp import MessageSegment, Message
from nonebot.rule import to_me
from nonebot.rule import startswith
from nonebot.rule import regex
from nonebot.typing import T_State
from nonebot.adapters import Bot, Event

hello = on_message()
@hello.handle()
async def handle_first_receive(bot: Bot, event: Event, state: T_State):
    msg = event.get_message()
    plainText = event.get_plaintext()
    msgStr = str(msg)
    msgStr = msgStr.replace(plainText, "")
    msgStr = msgStr.replace("]", "]::")
    cqList = msgStr.split("::")
    for cq in cqList:
        cqPropertyList = cq.replace("[", "").replace("]", "").split(",")
        for cqp in cqPropertyList:
            # print(cqp)
            if "url" in cqp:
                picLink = cqp.replace("url=", "")
                # TODO baidu api
                # doImgCheck()    
        # print(cq)
    #await hello.send(msgStr)