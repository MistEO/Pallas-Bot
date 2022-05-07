from nonebot import on_command
from nonebot.adapters.onebot.v11 import Bot, GroupMessageEvent, PrivateMessageEvent
from nonebot.adapters.onebot.v11.permission import GROUP_ADMIN, GROUP_OWNER

status = {}
help_text = r'''“战争女神”的故事经历，就交给前赴后继渴望解放的人们好好使用吧！

「漂流瓶」的命运是被传承，还是就此遗弃呢；「扔回去」则是应当被传颂下去的。
「涩涩」是幸福的和平到来前的宁静。
「公招图片」中伟大的战士们啊，我会在你们身边，与你们一同奋勇搏杀。

而我所拥有的，不过是这染病的身体，和不会改变的信仰。'''


help = on_command("牛牛帮助", aliases={'牛牛功能', '帕拉斯帮助', '帕拉斯功能'})


@help.handle()
async def _(bot: Bot, event: GroupMessageEvent):
    if status.get(event.group_id, True):
        await help.finish(help_text)


@help.handle()
async def _(bot: Bot, event: PrivateMessageEvent):
    await help.finish(help_text)


help_mode_switch = on_command(
    "牛牛开启帮助", aliases={"牛牛关闭帮助"},
    permission=GROUP_ADMIN | GROUP_OWNER
)


@help_mode_switch.handle()
async def _(bot: Bot, event: GroupMessageEvent):
    msg = event.dict()['raw_message']
    if '关闭' in msg:
        status[event.group_id] = False
        await help_mode_switch.finish("承受长期的悲痛以至于麻木，可怜的被压迫的人们，如果心中没有希望，是无法燃烧起怒火的。")
    else:
        status[event.group_id] = True
        await help_mode_switch.finish("人们若向往成为勇士，需要一份信仰，一点星火，一处滥觞。")
