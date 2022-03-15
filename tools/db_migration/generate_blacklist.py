# from .config import Config
from typing import Generator, List, Optional, Union, Tuple, Dict, Any
from functools import cached_property, cmp_to_key
from dataclasses import dataclass
from collections import defaultdict
# from aip import AipSpeech

import jieba_fast.analyse
import threading
import nonebot
import pypinyin
import pymongo
import time
import random
import re
import atexit

from nonebot.adapters.onebot.v11 import GroupMessageEvent, PrivateMessageEvent
from nonebot.adapters.onebot.v11 import Message, MessageSegment

mongo_client = pymongo.MongoClient('127.0.0.1', 27017, w=0)

mongo_db = mongo_client['PallasBot']

message_mongo = mongo_db['message']
message_mongo.create_index(name='time_index',
                           keys=[('time', pymongo.DESCENDING)])

context_mongo = mongo_db['context']
context_mongo.create_index(name='keywords_index',
                           keys=[('keywords', pymongo.HASHED)])
context_mongo.create_index(name='count_index',
                           keys=[('count', pymongo.DESCENDING)])
context_mongo.create_index(name='time_index',
                           keys=[('time', pymongo.DESCENDING)])
context_mongo.create_index(name='answers_index',
                           keys=[('answers.group_id', pymongo.TEXT),
                                 ('answers.keywords', pymongo.TEXT)],
                           default_language='none')

blacklist_mongo = mongo_db['blacklist']
blacklist_mongo.create_index(name='group_index',
                             keys=[('group_id', pymongo.HASHED)])
# global_config = nonebot.get_driver().config
# plugin_config = Config(**global_config.dict())

# if plugin_config.enable_voice:
#     tts_client = AipSpeech(plugin_config.APP_ID,
#                            plugin_config.API_KEY,
#                            plugin_config.SECRET_KEY)

# 请修改成 bot 自身的 QQ 号（
self_qq = '1234657'


@dataclass
class ChatData:
    group_id: int
    user_id: int
    raw_message: str
    plain_text: str
    time: int

    _keywords_size: int = 3

    @cached_property
    def is_plain_text(self) -> bool:
        return '[CQ:' not in self.raw_message and len(self.plain_text) != 0

    @cached_property
    def is_image(self) -> bool:
        return '[CQ:image,' in self.raw_message or '[CQ:face,' in self.raw_message

    @cached_property
    def keywords(self) -> str:
        if not self.is_plain_text:
            return self.raw_message

        keywords_list = jieba_fast.analyse.extract_tags(
            self.plain_text, topK=ChatData._keywords_size)
        if len(keywords_list) < 2:
            return self.plain_text
        else:
            # keywords_list.sort()
            return ' '.join(keywords_list)

    @cached_property
    def keywords_pinyin(self) -> str:
        return ''.join([item[0] for item in pypinyin.pinyin(
            self.keywords, style=pypinyin.NORMAL, errors='default')]).lower()

    @cached_property
    def to_me(self) -> bool:
        return '牛牛' in self.keywords or '帕拉斯' in self.keywords \
            or f'[CQ:at,qq={self_qq}]' in self.raw_message


class Chat:
    answer_threshold = 3            # answer 相关的阈值，值越小牛牛废话越多，越大话越少
    # answer_limit_threshold = 50     # 上限阈值，一般正常的上下文不可能发 50 遍，一般是其他 bot 的回复，禁了！
    cross_group_threshold = 3       # N 个群有相同的回复，就跨群作为全局回复
    repeat_threshold = 3            # 复读的阈值，群里连续多少次有相同的发言，就复读
    speak_threshold = 5             # 主动发言的阈值，越小废话越多

    lose_sanity_probability = 0.1   # 精神错乱（回复没达到阈值的话）的概率
    split_probability = 0.5         # 按逗号分割回复语的概率
    voice_probability = 0           # 回复语音的概率（仅纯文字）
    speak_continuously_probability = 0.5  # 连续主动说话的概率
    speak_continuously_max_len = 2  # 连续主动发言最多几句话

    save_time_threshold = 3600      # 每隔多久进行一次持久化 ( 秒 )
    save_count_threshold = 1000     # 单个群超过多少条聊天记录就进行一次持久化。与时间是或的关系

    blacklist_answer = defaultdict(set)

    def __init__(self, data: Union[ChatData, GroupMessageEvent, PrivateMessageEvent]):

        if (isinstance(data, ChatData)):
            self.chat_data = data
        elif (isinstance(data, GroupMessageEvent)):
            event_dict = data.dict()
            self.chat_data = ChatData(
                group_id=event_dict['group_id'],
                user_id=event_dict['user_id'],
                # 删除图片子类型字段，同一张图子类型经常不一样，影响判断
                raw_message=re.sub(
                    r',subType=\d+\]',
                    r']',
                    event_dict['raw_message']),
                plain_text=data.get_plaintext(),
                time=event_dict['time']
            )
        elif (isinstance(data, PrivateMessageEvent)):
            event_dict = data.dict()
            self.chat_data = ChatData(
                group_id=-event_dict['user_id'],    # 故意加个负号，和群号区分开来
                user_id=event_dict['user_id'],
                # 删除图片子类型字段，同一张图子类型经常不一样，影响判断
                raw_message=re.sub(
                    r',subType=\d+\]',
                    r']',
                    event_dict['raw_message']),
                plain_text=data.get_plaintext(),
                time=event_dict['time']
            )

    def learn(self) -> bool:
        '''
        学习这句话
        '''

        if len(self.chat_data.raw_message.strip()) == 0:
            return False

        group_id = self.chat_data.group_id
        if group_id in Chat._message_dict:
            group_msgs = Chat._message_dict[group_id]
            if group_msgs:
                group_pre_msg = group_msgs[-1]
            else:
                group_pre_msg = None

            # 群里的上一条发言
            self._context_insert(group_pre_msg)

            user_id = self.chat_data.user_id
            if group_pre_msg and group_pre_msg['user_id'] != user_id:
                # 该用户在群里的上一条发言（倒序三句之内）
                for msg in group_msgs[:-3:-1]:
                    if msg['user_id'] == user_id:
                        self._context_insert(msg)
                        break

        self._message_insert()
        return True

    def answer(self, with_limit: bool = True) -> Optional[Generator[Message, None, None]]:
        '''
        回复这句话，可能会分多次回复，也可能不回复
        '''

        if with_limit:
            # 不回复太短的对话，大部分是“？”、“草”
            if self.chat_data.is_plain_text and len(self.chat_data.plain_text) < 2:
                return None

            if self.chat_data.group_id in Chat._reply_dict:
                group_replies = Chat._reply_dict[self.chat_data.group_id]
                latest_reply = group_replies[-1]
                # 限制发音频率，最多 3 秒一次
                if int(time.time()) - latest_reply['time'] < 3:
                    return None
                # # 不要一直回复同一个内容
                # if self.chat_data.raw_message == latest_reply['pre_raw_message']:
                #     return None
                # 有人复读了牛牛的回复，不继续回复
                # if self.chat_data.raw_message == latest_reply['reply']:
                #    return None

                # 如果连续 5 次回复同样的内容，就不再回复。这种情况很可能是和别的 bot 死循环了
                # repeat_times = 5
                # if len(group_replies) >= repeat_times \
                #     and all(reply['pre_raw_message'] == self.chat_data.raw_message
                #             for reply in group_replies[-repeat_times:]):
                #     return None

        results = self._context_find()

        if results:
            with Chat._reply_lock:
                Chat._reply_dict[self.chat_data.group_id].append({
                    'time': int(time.time()),
                    'pre_raw_message': self.chat_data.raw_message,
                    'pre_keywords': self.chat_data.keywords,
                    'reply': "[PallasBot: Reply]",  # flag
                })

            def yield_results(str_list: List[str]) -> Generator[Message, None, None]:
                group_replies = Chat._reply_dict[self.chat_data.group_id]
                for item in str_list:
                    with Chat._reply_lock:
                        group_replies.append({
                            'time': int(time.time()),
                            'pre_raw_message': self.chat_data.raw_message,
                            'pre_keywords': self.chat_data.keywords,
                            'reply': item,
                        })
                    if '[CQ:' not in item and len(item) > 1 \
                            and random.random() < Chat.voice_probability:
                        yield Chat._text_to_speech(item)
                    else:
                        yield Message(item)

                with Chat._reply_lock:
                    group_replies = group_replies[-Chat._save_reserve_size:]

            return yield_results(results)

        return None

    @staticmethod
    def speak() -> Optional[Tuple[int, List[Message]]]:
        '''
        主动发言，返回当前最希望发言的群号、发言消息 List，也有可能不发言
        '''

        basic_msgs_len = 10
        basic_delay = 600

        def group_popularity_cmp(lhs: Tuple[int, List[Dict[str, Any]]],
                                 rhs: Tuple[int, List[Dict[str, Any]]]) -> int:

            def cmp(a: Any, b: Any):
                return (a > b) - (a < b)

            _, lhs_msgs = lhs
            _, rhs_msgs = rhs

            lhs_len = len(lhs_msgs)
            rhs_len = len(rhs_msgs)
            if lhs_len < basic_msgs_len or rhs_len < basic_msgs_len:
                return cmp(lhs_len, rhs_len)

            lhs_duration = lhs_msgs[-1]['time'] - lhs_msgs[0]['time']
            rhs_duration = rhs_msgs[-1]['time'] - rhs_msgs[0]['time']

            if not lhs_duration or not rhs_duration:
                return cmp(lhs_len, rhs_len)

            return cmp(lhs_len / lhs_duration, rhs_len / rhs_duration)

        # 按群聊热度排序
        popularity = sorted(Chat._message_dict.items(),
                            key=cmp_to_key(group_popularity_cmp))

        cur_time = time.time()
        for group_id, group_msgs in popularity:
            if group_id not in Chat._reply_dict or len(group_msgs) < basic_msgs_len:
                continue
            if Chat._reply_dict[group_id][-1]["time"] > group_msgs[-1]["time"]:
                continue

            msgs_len = len(group_msgs)
            latest_time = group_msgs[-1]['time']
            duration = latest_time - group_msgs[0]['time']
            avg_interval = duration / msgs_len

            # 已经超过平均发言间隔 N 倍的时间没有人说话了，才主动发言
            if cur_time - latest_time < avg_interval * Chat.speak_threshold + basic_delay:
                continue

            # append 一个 flag, 防止这个群热度特别高，但压根就没有可用的 context 时，每次 speak 都查这个群，浪费时间
            with Chat._reply_lock:
                Chat._reply_dict[group_id].append({
                    'time': int(cur_time),
                    'pre_raw_message': '[PallasBot: Speak]',
                    'pre_keywords': '[PallasBot: Speak]',
                    'reply': "[PallasBot: Speak]"
                })

            speak_context = context_mongo.aggregate([
                {
                    '$match': {
                        'time': {
                            '$gt': cur_time - 24 * 3600
                        },
                        'answers.count': {
                            '$gt': Chat.answer_threshold
                        },
                        'answers.group_id': group_id
                    }
                }, {
                    '$sample': {'size': 1}  # 随机一条
                }
            ])

            speak_context = list(speak_context)
            if not speak_context:
                continue

            messages = [answer['messages']
                        for answer in speak_context[0]['answers']
                        if answer['count'] >= Chat.answer_threshold
                        and answer['group_id'] == group_id]

            if not messages:
                continue

            speak = random.choice(random.choice(messages))

            with Chat._reply_lock:
                Chat._reply_dict[group_id].append({
                    'time': int(cur_time),
                    'pre_raw_message': '[PallasBot: Speak]',
                    'pre_keywords': '[PallasBot: Speak]',
                    'reply': speak
                })

            speak_list = [Message(speak), ]
            while random.random() < Chat.speak_continuously_probability \
                    and len(speak_list) < Chat.speak_continuously_max_len:
                pre_msg = str(speak_list[-1])
                answer = Chat(ChatData(group_id, 0, pre_msg,
                                       pre_msg, cur_time)).answer(False)
                if not answer:
                    break
                speak_list.extend(answer)
            return (group_id, speak_list)

        return None

    def ban(self) -> bool:
        '''
        禁止以后回复这句话，仅对该群有效果
        '''

        group_id = self.chat_data.group_id
        if group_id not in Chat._reply_dict:
            return False

        for reply in Chat._reply_dict[group_id][::-1]:
            if self.chat_data.raw_message in reply['reply']:
                pre_keywords = reply['pre_keywords']
                keywords = self.chat_data.keywords

                # 考虑这句回复是从别的群捞过来的情况，所以这里要分两次 update
                context_mongo.update_one({
                    'keywords': pre_keywords,
                    'answers.keywords': keywords,
                    'answers.group_id': group_id
                }, {
                    '$set': {
                        'answers.$.count': -99999
                    }
                })
                context_mongo.update_one({
                    'keywords': pre_keywords
                }, {
                    '$push': {
                        'ban': {
                            'keywords': keywords,
                            'group_id': group_id
                        }
                    }
                })
                return True

        return False

# private:
    _reply_dict = defaultdict(list)  # 牛牛回复的消息缓存，暂未做持久化
    _message_dict = {}              # 群消息缓存

    _save_reserve_size = 100        # 保存时，给内存中保留的大小
    _late_save_time = 0             # 上次保存（消息数据持久化）的时刻 ( time.time(), 秒 )

    _reply_lock = threading.Lock()
    _message_lock = threading.Lock()
    _blacklist_flag = 114514

    def _message_insert(self):
        group_id = self.chat_data.group_id

        with Chat._message_lock:
            if group_id not in Chat._message_dict:
                Chat._message_dict[group_id] = []

            Chat._message_dict[group_id].append({
                'group_id': group_id,
                'user_id': self.chat_data.user_id,
                'raw_message': self.chat_data.raw_message,
                'is_plain_text': self.chat_data.is_plain_text,
                'plain_text': self.chat_data.plain_text,
                'keywords': self.chat_data.keywords,
                'time': self.chat_data.time,
            })

        cur_time = self.chat_data.time
        if Chat._late_save_time == 0:
            Chat._late_save_time = cur_time - 1
            return

        if len(Chat._message_dict[group_id]) > Chat.save_count_threshold:
            Chat._sync(cur_time)

        elif cur_time - Chat._late_save_time > Chat.save_time_threshold:
            Chat._sync(cur_time)

    @staticmethod
    def _sync(cur_time: int = time.time()):
        '''
        持久化
        '''

        with Chat._message_lock:
            save_list = [msg
                         for group_msgs in Chat._message_dict.values()
                         for msg in group_msgs
                         if msg['time'] > Chat._late_save_time]
            if not save_list:
                return

            Chat._message_dict = {group_id: group_msgs[-Chat._save_reserve_size:]
                                  for group_id, group_msgs in Chat._message_dict.items()}

            Chat._late_save_time = cur_time

        message_mongo.insert_many(save_list)

    def _context_insert(self, pre_msg):
        if not pre_msg:
            return

        raw_message = self.chat_data.raw_message

        # 在复读，不学
        if pre_msg['raw_message'] == raw_message:
            return

        # 回复别人的，不学
        if '[CQ:reply,' in raw_message:
            return

        keywords = self.chat_data.keywords
        group_id = self.chat_data.group_id
        pre_keywords = pre_msg['keywords']

        # update_key = {
        #     'keywords': pre_keywords,
        #     'answers.keywords': keywords,
        #     'answers.group_id': group_id
        # }
        # update_value = {
        #     '$set': {'time': self.chat_data.time},
        #     '$inc': {'answers.$.count': 1},
        #     '$push': {'answers.$.messages': raw_message}
        # }
        # # update_value.update(update_key)

        # context_mongo.update_one(
        #     update_key, update_value, upsert=True)

        # 这个 upsert 太难写了，搞不定_(:з」∠)_
        # 先用 find + insert or update 凑合了
        find_key = {'keywords': pre_keywords}
        context = context_mongo.find_one(find_key)
        if context:
            update_value = {
                '$set': {
                    'time': self.chat_data.time
                },
                '$inc': {'count': 1}
            }
            answer_index = next((idx for idx, answer in enumerate(context['answers'])
                                 if answer['group_id'] == group_id
                                 and answer['keywords'] == keywords), -1)
            if answer_index != -1:
                update_value['$inc'].update({
                    f'answers.{answer_index}.count': 1
                })
                # 不是纯文本的时候，raw_message 是完全一样的，没必要 push
                if self.chat_data.is_plain_text:
                    update_value['$push'] = {
                        f'answers.{answer_index}.messages': raw_message
                    }
            else:
                update_value['$push'] = {
                    'answers': {
                        'keywords': keywords,
                        'group_id': group_id,
                        'count': 1,
                        'messages': [
                            raw_message
                        ]
                    }
                }

            context_mongo.update_one(find_key, update_value)
        else:
            context = {
                'keywords': pre_keywords,
                'time': self.chat_data.time,
                'count': 1,
                'answers': [
                    {
                        'keywords': keywords,
                        'group_id': group_id,
                        'count': 1,
                        'messages': [
                            raw_message
                        ]
                    }
                ]
            }
            context_mongo.insert_one(context)

    def _context_find(self) -> Optional[List[str]]:

        group_id = self.chat_data.group_id
        raw_message = self.chat_data.raw_message
        keywords = self.chat_data.keywords

        # 复读！
        if group_id in Chat._message_dict:
            group_msgs = Chat._message_dict[group_id]
            if group_msgs and len(group_msgs) >= Chat.repeat_threshold:
                if all(item['raw_message'] == raw_message
                        for item in group_msgs[:-Chat.repeat_threshold:-1]):
                    # 复读过一次就不复读了
                    if group_id not in Chat._reply_dict or Chat._reply_dict[group_id][-1]['reply'] != raw_message:
                        return [raw_message, ]

        context = context_mongo.find_one({'keywords': keywords})

        if not context:
            return None

        if random.random() < Chat.lose_sanity_probability:
            rand_threshold = 1
        else:
            rand_threshold = Chat.answer_threshold

        # 全局的黑名单
        ban_keywords = Chat.blacklist_answer[Chat._blacklist_flag] | Chat.blacklist_answer[group_id]
        # 针对单条回复的黑名单
        if 'ban' in context:
            ban_count = defaultdict(int)
            for ban in context['ban']:
                ban_key = ban['keywords']
                if ban['group_id'] == group_id or ban['group_id'] == Chat._blacklist_flag:
                    ban_keywords.add(ban_key)
                else:
                    # 超过 N 个群都把这句话 ban 了，那就全局 ban 掉
                    ban_count[ban_key] += 1
                    if ban_count[ban_key] == Chat.cross_group_threshold:
                        ban_keywords.add(ban_key)

        if not self.chat_data.is_image:
            all_answers = [answer
                           for answer in context['answers']
                           if answer['count'] >= rand_threshold
                           and len(answer['keywords']) > 1]  # 屏蔽特别短的回复内容，大部分是“？”、“草”之类的

        else:
            all_answers = [answer
                           for answer in context['answers']
                           if answer['count'] >= rand_threshold
                           and answer['keywords'].startswith('[CQ:')]   # 屏蔽图片后的纯文字回复，图片经常是表情包，后面的纯文字什么都有，很乱

        candidate_answers = []
        answers_count = defaultdict(int)
        other_group_cache = defaultdict(list)

        for answer in all_answers:
            answer_key = answer['keywords']
            if answer_key in ban_keywords:
                continue
            # if self.chat_data.to_me:
            #     if '牛牛' in answer_key or '帕拉斯' in answer_key:    # 呼叫牛牛还回复牛牛的，有点笨，ban了
            #         continue
            # # 正常一句话说不了这么多遍，一般都是其他 bot 一直发的
            # if answer['count'] > Chat.answer_limit_threshold:
            #     continue

            if answer['group_id'] == group_id:
                candidate_answers.append(answer)
            # 别的群的 at, 忽略
            elif '[CQ:at,qq=' in answer_key:
                continue
            else:   # 有这么 N 个群都有相同的回复，就作为全局回复
                answers_count[answer_key] += 1
                cur_count = answers_count[answer_key]
                if cur_count < Chat.cross_group_threshold:      # 没达到阈值前，先缓存
                    other_group_cache[answer_key].append(answer)
                elif cur_count == Chat.cross_group_threshold:   # 刚达到阈值时，将缓存加入
                    candidate_answers.append(answer)
                    candidate_answers += other_group_cache[answer_key]
                else:                                           # 超过阈值后，加入
                    candidate_answers.append(answer)

        if not candidate_answers:
            return None

        final_answer = random.choices(candidate_answers, weights=[
            # 防止某个回复权重太大，别的都 Roll 不到了
            min(answer['count'], 10) for answer in candidate_answers])[0]
        answer_str = random.choice(final_answer['messages'])

        if 0 < answer_str.count('，') <= 3 and random.random() < Chat.split_probability:
            return answer_str.split('，')
        return [answer_str, ]

    @staticmethod
    def _text_to_speech(text: str) -> Optional[Message]:
        # if plugin_config.enable_voice:
        #     result = tts_client.synthesis(text, options={'per': 111})  # 度小萌
        #     if not isinstance(result, dict):  # error message
        #         return MessageSegment.record(result)

        return Message(f'[CQ:tts,text={text}]')

    @staticmethod
    def generate_blacklist() -> None:
        group_blacklist = defaultdict(dict)

        all_ban = context_mongo.find(
            {
                'ban': {'$exists': True}
            }
        )
        for item in all_ban:
            ban_item = item['ban']
            for ban_obj in ban_item:
                group_id = ban_obj['group_id']
                keywords = ban_obj['keywords']

                cur_group_bl = group_blacklist[group_id]
                if keywords not in cur_group_bl:
                    cur_group_bl[keywords] = 0
                cur_group_bl[keywords] += 1

        # 让全局的位于第一条记录，手动管理的时候好查一些
        blacklist_mongo.update_one({"group_id": Chat._blacklist_flag},
                                   {"$set": {"answers": []}},
                                   upsert=True)

        global_ban_dict = defaultdict(int)
        for group_id, keywords_dict in group_blacklist.items():
            blacklist_answer = []
            blacklist_answer_reserve = []
            for keywords, count in keywords_dict.items():
                if count < 2:
                    blacklist_answer_reserve.append(keywords)
                    continue
                global_ban_dict[keywords] += 1
                blacklist_answer.append(keywords)
            if len(blacklist_answer_reserve):
                blacklist_mongo.update_one({"group_id": group_id},
                                           {"$set": {
                                               "answers_reserve": blacklist_answer_reserve}},
                                           upsert=True)
            if len(blacklist_answer):
                blacklist_mongo.update_one({"group_id": group_id},
                                           {"$set": {"answers": blacklist_answer}},
                                           upsert=True)

        blacklist_answer = []
        blacklist_answer_reserve = []
        for keywords, count in global_ban_dict.items():
            if count < 2:
                blacklist_answer_reserve.append(keywords)
                continue
            blacklist_answer.append(keywords)

        if len(blacklist_answer_reserve):
            blacklist_mongo.update_one(
                {'group_id': Chat._blacklist_flag},
                {'$set': {'answers_reserve': blacklist_answer_reserve}},
                upsert=True
            )

        blacklist_threshold = 50

        all_context = context_mongo.find(
            {'count': {'$gt': blacklist_threshold},
             'answers.count': {'$gt': blacklist_threshold}})
        blacklist_answer += list({answer['keywords'] for context in all_context
                                  for answer in context['answers']
                                  if answer['count'] > blacklist_threshold})

        blacklist_answer = list(set(blacklist_answer))
        if len(blacklist_answer):
            blacklist_mongo.update_one(
                {'group_id': Chat._blacklist_flag},
                {'$set': {'answers': blacklist_answer}},
                upsert=True
            )

    @staticmethod
    def update_blacklist() -> None:
        all_blacklist = blacklist_mongo.find()

        for item in all_blacklist:
            Chat.blacklist_answer[item['group_id']] |= set(
                item['answers'])


Chat.update_blacklist()


def _chat_sync():
    Chat._sync()


# Auto sync on program exit
atexit.register(_chat_sync)


if __name__ == '__main__':
    Chat.generate_blacklist()
