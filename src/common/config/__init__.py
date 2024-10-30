import pymongo
import time
from pymongo.collection import Collection
from abc import ABC
from typing import Any, Optional, List
from pydantic import BaseModel, Extra

try:
    # pydantic v2
    from nonebot import get_plugin_config
except ImportError:
    # pydantic v1
    from nonebot import get_driver

KEY_JOINER = '.'


class PluginConfig(BaseModel, extra=Extra.ignore):
    # 是否使用云端数据库
    use_rpc: bool = False
    # 远程数据库token
    rpc_token: str = ''
    # 默认轮盘模式
    default_roulette_mode: int = 0
    # mongodb host
    mongo_host: str = '127.0.0.1'
    # mongodb port
    mongo_port: int = 27017
    # answer 相关阈值，值越大，牛牛废话越少；越小，牛牛废话越多
    answer_threshold: int = 3
    # answer 阈值权重
    answer_threshold_weights: List[int] = [7, 23, 70]
    # 上下文联想，记录多少个关键词（每个群）
    topics_size: int = 16
    # 上下文命中后，额外的权重系数
    topics_importance: int = 10000
    # N 个群有相同的回复，就跨群作为全局回复
    cross_group_threshold: int = 2
    # 复读的阈值，群里连续多少次有相同的发言，就复读
    repeat_threshold: int = 3
    # 主动发言的阈值，越小废话越多
    speak_threshold: int = 5
    # 说过的话，接下来多少次不再说
    duplicate_reply: int = 10
    # 按逗号分割回复语的概率
    split_probability: float = 0.5
    # 喝醉之后，超过多长的文本全部转换成语音发送
    drunk_tts_threshold: int = 6
    # 连续主动说话的概率
    speak_continuously_probability: float = 0.5
    # 主动说话加上随机戳一戳群友的概率
    speak_poke_probability: float = 0.6
    # 连续主动说话最多几句话
    speak_continuously_max_len: int = 2
    # 每隔多久进行一次持久化 ( 秒 )
    save_time_threshold: int = 3600
    # 单个群超过多少条聊天记录就进行一次持久化，与时间是或的关系
    save_count_threshold: int = 1000
    # 保存时，给内存中保留的大小
    save_reserved_size: int = 100
    # sing 每次发送的语音长度，单位：秒
    sing_length: int = 120
    # 模型对应词
    sing_speakers: dict = {
        "帕拉斯": "pallas",
        "牛牛": "pallas",
    }
    # sing cuda 设备指定
    sing_cuda_device: str = ''
    # 歌曲缓存大小
    song_cache_size: int = 100
    # 歌曲缓存天数
    song_cache_days: int = 30
    # tts 声码器
    tts_vocoder: str = 'pwgan_aishell3'
    # chat 模型的strategy
    chat_strategy: str = ''
    # chat 是否使用本地api
    chat_use_local_api: bool = False
    # chat api超时时间
    chat_timeout: int = 15
    # chat api重试次数
    chat_retry: int = 3


try:
    # pydantic v2
    plugin_config = get_plugin_config(PluginConfig)
except:
    # pydantic v1
    plugin_config = PluginConfig.parse_obj(get_driver().config)

if plugin_config.use_rpc:
    from src.common.utils.rpc import MongoClient
else:
    from pymongo import MongoClient


class Config(ABC):
    _config_mongo: Optional[Collection] = None
    _table: Optional[str] = None
    _key: Optional[str] = None

    @classmethod
    def _get_config_mongo(cls) -> Collection:
        if cls._config_mongo is None:
            mongo_client = MongoClient(
                plugin_config.mongo_host, plugin_config.mongo_port)
            mongo_db = mongo_client['PallasBot']
            cls._config_mongo = mongo_db[cls._table]
        return cls._config_mongo

    _document_cache: Optional[dict] = None

    def _find(self, key: str) -> Any:
        if self._document_key not in self._document_cache:
            # 获取这个 key_id（bot_id 或 group_id）的所有配置（document）
            info = self._get_config_mongo().find_one(self._db_filter)
            self._document_cache[self._document_key] = info

        cache = self._document_cache[self._document_key]
        for k in key.split(KEY_JOINER):
            if cache and k in cache:
                cache = cache[k]
            else:
                return None

        return cache

    def _update(self, key: str, value: Any, db: bool = True) -> None:
        if db:
            self._get_config_mongo().update_one(
                self._db_filter, {'$set': {key: value}})

        if self._document_key not in self._document_cache or \
                not self._document_cache[self._document_key]:
            self._document_cache[self._document_key] = {}
        cache = self._document_cache[self._document_key]
        splited_keys = key.split(KEY_JOINER)
        for k in splited_keys[:-1]:
            if k not in cache:
                cache[k] = {}
            cache = cache[k]
        cache[splited_keys[-1]] = value

    @classmethod
    def _update_all(cls, key: str, value: Any, db: bool = True) -> None:
        splited_keys = key.split(KEY_JOINER)
        for cache_key, cache in cls._document_cache.items():
            if db:
                cls._get_config_mongo().update_one(
                    {cls._key: cache_key}, {'$set': {key: value}})

            if not cache:
                cls._document_cache[cache_key] = {}
                cache = cls._document_cache[cache_key]

            for k in splited_keys[:-1]:
                if k not in cache:
                    cache[k] = {}
                cache = cache[k]
            cache[splited_keys[-1]] = value

    def __init__(self, table: str, key: str, key_id: int) -> None:
        self._document_key = key_id
        self._db_filter = {key: key_id}
        if self.__class__._document_cache is None:
            self.__class__._document_cache = {}
            self.__class__._table = table
            self.__class__._key = key


class BotConfig(Config):
    def __init__(self, bot_id: int, group_id: int = 0, cooldown: int = 5) -> None:
        super().__init__(
            table='config',
            key='account',
            key_id=bot_id)

        self.bot_id = bot_id
        self.group_id = group_id
        self.cooldown = cooldown

    def security(self) -> bool:
        '''
        账号是否安全（不处于风控等异常状态）
        '''
        security = self._find('security')
        return True if security else False

    def auto_accept(self) -> bool:
        '''
        是否自动接受加群、加好友请求
        '''
        accept = self._find('auto_accept')
        return True if accept else False

    def is_admin_of_bot(self, user_id: int) -> bool:
        '''
        是否是管理员
        '''
        admins = self._find('admins')
        return user_id in admins if admins else False

    def is_cooldown(self, action_type: str) -> bool:
        '''
        是否冷却完成
        '''
        cd = self._find(
            f'cooldown{KEY_JOINER}{action_type}{KEY_JOINER}{self.group_id}')
        return cd + self.cooldown < time.time() if cd else True

    def refresh_cooldown(self, action_type: str) -> None:
        '''
        刷新冷却时间
        '''
        self._update(
            f'cooldown{KEY_JOINER}{action_type}{KEY_JOINER}{self.group_id}', time.time(), db=False)

    def reset_cooldown(self, action_type: str) -> None:
        '''
        重置冷却时间
        '''
        self._update(
            f'cooldown{KEY_JOINER}{action_type}{KEY_JOINER}{self.group_id}', 0, db=False)

    _drink_handlers = []
    _sober_up_handlers = []

    @classmethod
    def handle_drink(cls, func):
        '''
        注册喝酒回调函数
        '''
        cls._drink_handlers.append(func)
        return func

    @classmethod
    def handle_sober_up(cls, func):
        '''
        注册醒酒回调函数
        '''
        cls._sober_up_handlers.append(func)
        return func

    def drink(self) -> None:
        '''
        喝酒功能，增加牛牛的混沌程度（bushi
        '''
        value = self.drunkenness() + 1
        self._update(f'drunk{KEY_JOINER}{self.group_id}', value, db=False)
        for on_drink in self._drink_handlers:
            on_drink(self.bot_id, self.group_id, value)

    def sober_up(self) -> bool:
        '''
        醒酒，降低醉酒程度，返回是否完全醒酒
        '''
        value = self.drunkenness() - 1
        self._update(f'drunk{KEY_JOINER}{self.group_id}', value, db=False)
        if value > 0:
            return False
        for on_sober_up in self._sober_up_handlers:
            on_sober_up(self.bot_id, self.group_id, value)
        return True

    def drunkenness(self) -> int:
        '''
        获取醉酒程度
        '''
        value = self._find(f'drunk{KEY_JOINER}{self.group_id}')
        return value if value else 0

    @classmethod
    def fully_sober_up(cls) -> None:
        '''
        完全醒酒
        '''
        cls._update_all('drunk', {})

    def is_sleep(self) -> bool:
        '''
        牛牛睡了么？
        '''
        value = self._find(f'sleep{KEY_JOINER}{self.group_id}')
        return value > time.time() if value else False

    def sleep(self, seconds: int) -> None:
        '''
        牛牛睡觉
        '''
        self._update(f'sleep{KEY_JOINER}{self.group_id}',
                     time.time() + seconds)

    def taken_name(self) -> int:
        '''
        返回在该群夺舍的账号
        '''
        user_id = self._find(f'taken_name{KEY_JOINER}{self.group_id}')
        return user_id if user_id else 0

    def update_taken_name(self, user_id: int) -> None:
        '''
        更新夺舍的账号
        '''
        self._update(f'taken_name{KEY_JOINER}{self.group_id}', user_id)


class GroupConfig(Config):
    def __init__(self, group_id: int, cooldown: int = 5) -> None:
        super().__init__(
            table='group_config',
            key='group_id',
            key_id=group_id)

        self.group_id = group_id
        self.cooldown = cooldown

    def roulette_mode(self) -> int:
        '''
        获取轮盘模式

        :return: 0 踢人 1 禁言
        '''
        mode = self._find('roulette_mode')
        return mode if mode != None else plugin_config.default_roulette_mode

    def set_roulette_mode(self, mode: int) -> None:
        '''
        设置轮盘模式

        :param mode: 0 踢人 1 禁言
        '''
        self._update('roulette_mode', mode)

    def ban(self) -> None:
        '''
        拉黑该群
        '''
        self._update('banned', True)

    def is_banned(self) -> bool:
        '''
        群是否被拉黑
        '''
        banned = self._find('banned')
        return True if banned else False

    def is_cooldown(self, action_type: str) -> bool:
        '''
        是否冷却完成
        '''
        cd = self._find(
            f'cooldown{KEY_JOINER}{action_type}')
        return cd + self.cooldown < time.time() if cd else True

    def refresh_cooldown(self, action_type: str) -> None:
        '''
        刷新冷却时间
        '''
        self._update(
            f'cooldown{KEY_JOINER}{action_type}', time.time(), db=False)

    def reset_cooldown(self, action_type: str) -> None:
        '''
        重置冷却时间
        '''
        self._update(
            f'cooldown{KEY_JOINER}{action_type}', 0, db=False)

    def sing_progress(self) -> Optional[dict]:
        '''
        获取歌曲进度
        '''
        return self._find('sing_progress')

    def update_sing_progress(self, progress: dict) -> None:
        '''
        更新歌曲进度
        '''
        self._update('sing_progress', progress)


class UserConfig(Config):
    def __init__(self, user_id: int) -> None:
        super().__init__(
            table='user_config',
            key='user_id',
            key_id=user_id)

        self.user_id = user_id

    def ban(self) -> None:
        '''
        拉黑这个人
        '''
        self._update('banned', True)

    def is_banned(self) -> bool:
        '''
        是否被拉黑
        '''
        banned = self._find('banned')
        return True if banned else False


def test():
    BotConfig(1234567).drink()
    BotConfig.fully_sober_up()


@BotConfig.handle_drink
def my_callback(bot_id, group_id, value):
    print(bot_id, group_id, value)


if __name__ == "__main__":
    test()
