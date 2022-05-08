import pymongo

from dataclasses import dataclass
from typing import Any

from pyparsing import And

mongo_client = pymongo.MongoClient('127.0.0.1', 27017, w=0)
mongo_db = mongo_client['PallasBot']
config_mongo = mongo_db['config']
config_mongo.create_index(name='accounts_index',
                          keys=[('account', pymongo.HASHED)])


@dataclass
class BotConfig:
    def __init__(self, bot_id: int) -> None:
        self.bot_id = bot_id
        self._mongo_find_key = {
            'account': bot_id
        }

    def _find_key(self, key: str) -> Any:
        info = config_mongo.find_one(self._mongo_find_key)
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
