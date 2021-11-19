# encoding:utf-8

import requests
import json
from nonebot import permission as perm
from nonebot import on_command
from nonebot import on_message
from nonebot.adapters.cqhttp import MessageSegment, Message
from nonebot.rule import to_me
from nonebot.rule import startswith
from nonebot.rule import regex
from nonebot.typing import T_State
from nonebot.adapters import Bot, Event
from .config import Config
import nonebot
from aip import AipNlp

door = True
hello = on_message(block=False)
@hello.handle()
async def handle_first_receive(bot: Bot, event: Event, state: T_State):
    global door
    if event.dict()['message_type'] == 'group':
        for msg in event.dict()['message']:
            if(msg['type'] == 'text') & door:
              print(event.dict())
              r = doTextAnalyse(msg['data']['text'])
              await hello.send(r)
    # await hello.send(msgStr)
    return False

switch = on_command("对话情绪识别", rule=to_me(), priority=5)
@switch.handle()
async def handle__first_receive(bot: Bot, event: Event, state: T_State):
    # print("in setu check")
    args = str(event.get_message()).strip()
    if args:
        state["param"] = args

@switch.got("param", prompt="开启或关闭")
async def handle_param(bot: Bot, event: Event, state: T_State):
    global door
    param = state["param"]
    if param not in ["开启", "关闭"]:
        await switch.reject("参数错误！")
    if param in "开启":
        door = True
    if param in  "关闭":
        door = False
    await switch.finish("已"+str(param))

def doTextAnalyse(msg:str()):
  print(msg)
  """ 你的 APPID AK SK """
  APP_ID = '1'
  API_KEY = '1'
  SECRET_KEY = '1'
  client = AipNlp(APP_ID, API_KEY, SECRET_KEY)
  text = msg
  """ 调用对话情绪识别接口 """
  client.emotion(text)
  """ 如果有可选参数 """
  options = {}
  # options["scene"] = "talk"
  """ 带参数调用对话情绪识别接口 """
  reply = client.emotion(text, options)
  print(str(reply))
  return reply.json()['items'][0]['replies']
def doImgCheck(picUrl: str):
    # print("in img check function")
    request_url = "https://aip.baidubce.com/rest/2.0/solution/v1/img_censor/v2/user_defined"
    params = {"imgUrl":picUrl}
    access_token = plugin_config.baidu_api_ak
    request_url = request_url + "?access_token=" + access_token
    headers = {'content-type': 'application/x-www-form-urlencoded'}
    response = requests.post(request_url, data=params, headers=headers)
    if response:
        # print (response.json())
        # print(response.json()['data'][0]['probability'])
        try:
            if response.json()['conclusion'] != "合规":
                conclusion = response.json()['data'][0]['msg']
                deep = response.json()['data'][0]['probability']
                reply = {'conclusion':str(conclusion),'probability':str(deep)}
                return reply
        except KeyError:
            print('KeyError')
            return
        else:    
            return
    return


async def doRecall(bot: Bot, event: Event, state: T_State):
    # do recall
    # print(event.dict())
    msgId = event.dict()['message_id']
    # print(msgId)
    await bot.call_api('delete_msg',message_id=msgId)