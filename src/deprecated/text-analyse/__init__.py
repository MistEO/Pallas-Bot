# encoding:utf-8

import requests
import json
from nonebot import permission as perm
from nonebot import on_command
from nonebot import on_message
from nonebot.adapters.onebot.v11 import MessageSegment, Message, permission
from nonebot.rule import to_me
from nonebot.rule import startswith
from nonebot.rule import regex
from nonebot.typing import T_State
from nonebot.adapters import Bot, Event
from .config import Config
import nonebot
from aip import AipNlp
import time

global_config = nonebot.get_driver().config
plugin_config = Config(**global_config.dict())


textAnalyse = on_message(
    block=False,
    priority=20,
    permission=permission.GROUP)


@textAnalyse.handle()
async def handle_first_receive(bot: Bot, event: Event, state: T_State):
    door = plugin_config.textAnalyseSwitch
    if not door:
        return False
    nicknameList = plugin_config.nicknameList
    keyWordsList = ["涩涩"]
    # print(event.dict())
    nl = nicknameList.split(',')
    if event.dict()['message_type'] == 'group':
        if len(event.dict()['message']) == 1:
            for msg in event.dict()['message']:
                if(msg['type'] == 'text') and door:
                    # print(event.dict())
                    try:
                        msgContent = msg['data']['text']
                        isCallBot = False
                        isNotOtherKeyWords = True
                        for nickname in nl:
                            if nickname in msgContent:
                                isCallBot = True
                                msgContent = msgContent.replace(nickname, '')
                        for keyWords in keyWordsList:
                            if keyWords in msgContent:
                                isNotOtherKeyWords = False
                        if isCallBot != True:
                            receiveTime = event.dict()['time']
                            t = int(time.time())
                            # 防止发言频率过高 冻结 封号
                            if t - receiveTime < 1:
                                time.sleep(1)
                            isCallBot = event.dict()['to_me']

                        # print(isCallBot)
                        if isCallBot and isNotOtherKeyWords:
                            r = doTextAnalyse(msgContent)
                            await textAnalyse.send(r)
                    except Exception as e:
                        # print(e)
                        return
                    else:
                        return
    # await hello.send(msgStr)
    return False

switch = on_command('对话情绪识别', rule=to_me(), priority=5)


@switch.handle()
async def handle__first_receive(bot: Bot, event: Event, state: T_State):
    # print("in setu check")
    args = str(event.get_message()).strip()
    if args:
        state['param'] = args


@switch.got('param', prompt='开启或关闭')
async def handle_param(bot: Bot, event: Event, state: T_State):
    global door
    param = state['param']
    if param not in ['开启', '关闭']:
        await switch.reject('参数错误！')
    if param in '开启':
        door = True
    if param in '关闭':
        door = False
    await switch.finish('已'+str(param))


def doTextAnalyse(msg: str()):
    # print(msg)
    """ 你的 APPID AK SK """
    APP_ID = plugin_config.APP_ID
    API_KEY = plugin_config.API_KEY
    SECRET_KEY = plugin_config.SECRET_KEY
    client = AipNlp(APP_ID, API_KEY, SECRET_KEY)
    text = msg
    """ 调用对话情绪识别接口 """
#   client.emotion(text)
    """ 如果有可选参数 """
    options = {}
    # options["scene"] = "talk"
    """ 带参数调用对话情绪识别接口 """
    reply = client.emotion(text, options)
    # print(str(reply))
    return reply['items'][0]['replies'][0]
