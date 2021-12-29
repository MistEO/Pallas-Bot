from nonebot import on_command
from nonebot.adapters.cqhttp import Bot, GroupMessageEvent, PrivateMessageEvent
from nonebot.adapters.cqhttp.permission import GROUP_ADMIN, GROUP_OWNER

status = {}

help = on_command("help", aliases={'Help', '帮助', '牛牛帮助', '帕拉斯帮助'})

@help.handle()
async def _(bot: Bot, event: GroupMessageEvent):
    if status.get(event.group_id, True):
        await help.send(
r'''保佑胜利的英雄，我将领受你们的祝福。
呼喊[牛牛/帕拉斯]，聆听我的呼唤。
[(牛牛/帕拉斯)(扔/丢)(瓶子/漂流瓶)]，是你的信念；
[(牛牛/帕拉斯)(捡/捞)(瓶子/漂流瓶)]，是你的渴望；
[(扔/丢)回去]，是你的宽慰。
当时机成熟时，[牛牛涩涩/牛牛我要看...涩图]，能够体会至高的荣誉和幸福。
提供{公招图片}，我们将带着胜利归来。'''
)

@help.handle()
async def _(bot: Bot, event: PrivateMessageEvent):
    await help.send("可爱")


help_mode_switch = on_command(
    "牛牛开启帮助", aliases={"牛牛关掉帮助"},
    permission=GROUP_ADMIN|GROUP_OWNER
)

@help_mode_switch.handle()
async def _(bot: Bot, event: GroupMessageEvent):
    msg = event.dict()['raw_message']
    if '关掉' in msg:
        status[event.group_id] = False
        await help_mode_switch.finish("现在可没有后悔的余地了。")
    else:
        status[event.group_id] = True
        await help_mode_switch.finish("欢呼吧！")