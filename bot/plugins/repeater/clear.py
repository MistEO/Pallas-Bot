import time
from .database import Context as ContextModel
from nonebot import require

clear_sched = require('nonebot_plugin_apscheduler').scheduler

@clear_sched.scheduled_job('interval', days=3)
async def clear_context():
    """
    定时清理冗余的学习数据
    """

    ContextModel.delete().where(
        ContextModel.count == 1,
        ContextModel.latest_time < time.time() - 7 * 24 * 3600
    ).execute()

    # # 正常一句话不可能学50次以上，除非是别的 bot，直接重置一下，不然别的都学不进去了
    # ContextModel.update(
    #     count = -114514
    # ).where(
    #     ContextModel.count > 50,
    # )