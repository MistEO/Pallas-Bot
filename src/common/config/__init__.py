import pymongo
import time
from pymongo.collection import Collection
from collections import defaultdict

from typing import Any, Optional


class BotConfig:
    __config_mongo: Optional[Collection] = None

    @classmethod
    def _get_config_mongo(cls) -> Collection:
        if cls.__config_mongo is None:
            mongo_client = pymongo.MongoClient('127.0.0.1', 27017, w=0)
            mongo_db = mongo_client['PallasBot']
            cls.__config_mongo = mongo_db['config']
            cls.__config_mongo.create_index(name='accounts_index',
                                            keys=[('account', pymongo.HASHED)])
        return cls.__config_mongo

    def __init__(self, bot_id: int, group_id: int = 0) -> None:
        self.bot_id = bot_id
        self.group_id = group_id
        self._mongo_find_key = {
            'account': bot_id
        }
        self.cooldown = 5   # 单位秒

    def _find_key(self, key: str) -> Any:
        info = self._get_config_mongo().find_one(self._mongo_find_key)
        if info and key in info:
            return info[key]
        else:
            return None

    def security(self) -> bool:
        '''
        账号是否安全（不处于风控等异常状态）
        '''
        security = self._find_key('security')
        return security if security is not None else False

    def auto_accept(self) -> bool:
        '''
        是否自动接受加群、加好友请求
        '''
        accept = self._find_key('auto_accept')
        return accept if accept is not None else False

    def is_admin(self, user_id: int) -> bool:
        '''
        是否是管理员
        '''
        admins = self._find_key('admins')
        return user_id in admins if admins is not None else False

    def add_admin(self, user_id: int) -> None:
        '''
        添加管理员
        '''
        self._get_config_mongo().update_one(
            self._mongo_find_key,
            {'$push': {'admins': user_id}},
            upsert=True
        )

    _cooldown_data = {}

    def is_cooldown(self, action_type: str) -> bool:
        '''
        是否冷却完成
        '''
        if self.bot_id not in BotConfig._cooldown_data:
            return True

        if self.group_id not in BotConfig._cooldown_data[self.bot_id]:
            return True

        if action_type not in BotConfig._cooldown_data[self.bot_id][self.group_id]:
            return True

        cd = BotConfig._cooldown_data[self.bot_id][self.group_id][action_type]
        return cd + self.cooldown < time.time()

    def refresh_cooldown(self, action_type: str) -> None:
        '''
        刷新冷却时间
        '''
        if self.bot_id not in BotConfig._cooldown_data:
            BotConfig._cooldown_data[self.bot_id] = {}

        if self.group_id not in BotConfig._cooldown_data[self.bot_id]:
            BotConfig._cooldown_data[self.bot_id][self.group_id] = {}

        BotConfig._cooldown_data[self.bot_id][self.group_id][action_type] = time.time(
        )

    _drunk_data = defaultdict(int)          # 醉酒程度，不同群应用不同的数值

    def drink(self) -> None:
        '''
        喝酒功能，增加牛牛的混沌程度（bushi
        '''
        BotConfig._drunk_data[self.group_id] += 1

    def sober_up(self) -> bool:
        '''
        醒酒，降低醉酒程度，返回是否完全醒酒
        '''
        BotConfig._drunk_data[self.group_id] -= 1
        return BotConfig._drunk_data[self.group_id] <= 0

    def drunkenness(self) -> int:
        '''
        获取醉酒程度
        '''
        return BotConfig._drunk_data[self.group_id]

    @staticmethod
    def completely_sober():
        for key in BotConfig._drunk_data.keys():
            BotConfig._drunk_data[key] = 0


class GroupConfig:
    __config_mongo: Optional[Collection] = None

    @classmethod
    def _get_config_mongo(cls) -> Collection:
        if cls.__config_mongo is None:
            mongo_client = pymongo.MongoClient('127.0.0.1', 27017, w=0)
            mongo_db = mongo_client['PallasBot']
            cls.__config_mongo = mongo_db['group_config']
            cls.__config_mongo.create_index(name='group_index',
                                            keys=[('group_id', pymongo.HASHED)])
        return cls.__config_mongo

    def __init__(self, group_id: int) -> None:
        self.group_id = group_id
        self._mongo_find_key = {
            'group_id': group_id
        }

    def _find_key(self, key: str) -> Any:
        info = self._get_config_mongo().find_one(self._mongo_find_key)
        if info and key in info:
            return info[key]
        else:
            return None

    _roulette_mode = {}    # 0 踢人 1 禁言

    def roulette_mode(self) -> int:
        '''
        获取轮盘模式

        :return: 0 踢人 1 禁言
        '''
        if self.group_id not in GroupConfig._roulette_mode:
            mode = self._find_key('roulette_mode')
            GroupConfig._roulette_mode[self.group_id] = mode if mode is not None else 0

        return GroupConfig._roulette_mode[self.group_id]

    def set_roulette_mode(self, mode: int) -> None:
        '''
        设置轮盘模式

        :param mode: 0 踢人 1 禁言
        '''
        GroupConfig._roulette_mode[self.group_id] = mode
        self._get_config_mongo().update_one(
            self._mongo_find_key,
            {'$set': {'roulette_mode': mode}},
            upsert=True
        )
