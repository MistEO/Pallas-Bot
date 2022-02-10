import threading
from typing import List, Optional, Union
from functools import cached_property
from dataclasses import dataclass
from collections import defaultdict

import jieba_fast.analyse
import pypinyin
import pymongo
import time
import random
import re
import atexit

from nonebot.adapters import Event

mongo_client = pymongo.MongoClient('127.0.0.1', 27017, w=0)

mongo_db = mongo_client['PallasBot']

message_mongo = mongo_db['message']
context_mongo = mongo_db['context']


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
            keywords_list.sort()
            return ' '.join(keywords_list)

    @cached_property
    def keywords_pinyin(self) -> str:
        return ''.join([item[0] for item in pypinyin.pinyin(
            self.keywords, style=pypinyin.NORMAL, errors='default')]).lower()


class Chat:
    save_time_threshold = 600      # 每隔多久进行一次保存 ( 秒 )
    save_count_threshold = 100     # 单个群超过多少条聊天记录就进行一次保存。与时间是或的关系

    _count_threshold = 3            # answer 相关的阈值

    _reply_dict = {}                # 牛牛回复的消息缓存，暂未做持久化
    _message_dict = {}              # 群消息缓存
    _context_dict = {}              # 学习记录的缓存

    _save_reserve_size = 10         # 保存时，给内存中保留的大小
    _late_save_time = 0             # 上次保存（消息数据持久化）的时刻 ( time.time(), 秒 )

    # _sync_lock = threading.Lock()

    def __init__(self, data: Union[ChatData, Event]):

        if (isinstance(data, ChatData)):
            self.chat_data = data
        elif (isinstance(data, Event)):
            event_dict = data.dict()
            self.chat_data = ChatData(
                group_id=event_dict['group_id'],
                user_id=event_dict['user_id'],
                # 删除图片子类型字段，同一张图子类型经常不一样，影响判断
                raw_message=re.sub(',subType=\d+', '',
                                   event_dict['raw_message']),
                plain_text=data.get_plaintext(),
                time=event_dict['time']
            )

    def learn(self):
        '''
        学习这句话
        '''

        if len(self.chat_data.raw_message.strip()) == 0:
            return

        group_id = self.chat_data.group_id
        if group_id in Chat._message_dict:
            group_msg = Chat._message_dict[group_id]
            if group_msg:
                group_pre_msg = group_msg[-1]
            else:
                group_pre_msg = None

            # 群里的上一条发言
            self._context_insert(group_pre_msg)

            user_id = self.chat_data.user_id
            if group_pre_msg and group_pre_msg['user_id'] != user_id:
                # 该用户在群里的上一条发言（倒序）
                for msg in group_msg[:-Chat._save_reserve_size:-1]:
                    if msg['user_id'] == user_id:
                        self._context_insert(msg)
                        break

        self._message_insert()

    def answer(self) -> Optional[List[str]]:
        '''
        回复这句话，可能会分多次回复（所以是List），也可能不回复
        '''

        if self.chat_data.group_id in Chat._reply_dict:
            latest_reply = Chat._reply_dict[self.chat_data.group_id]
            # 限制发音频率，最多 3 秒一次
            if self.chat_data.time - latest_reply['time'] < 3:
                return None
            # # 不要一直回复同一个内容
            # if self.chat_data.raw_message == latest_reply['pre_msg']:
            #     return None
            # 有人复读了牛牛的回复，不继续回复
            if self.chat_data.raw_message == latest_reply['cur_msg']:
                return None

        # 不回复太短的对话，大部分是“？”、“草”
        if self.chat_data.is_plain_text and len(self.chat_data.plain_text) < 2:
            return None

        result = self._context_find()

        if result:
            Chat._reply_dict[self.chat_data.group_id] = {
                'time': (int)(time.time()),
                'cur_msg': result[-1],
                'pre_msg': self.chat_data.raw_message
            }
        return result

    def _message_insert(self):
        group_id = self.chat_data.group_id

        # with Chat._sync_lock:
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
            Chat.sync(cur_time)

        elif cur_time - Chat._late_save_time > Chat.save_time_threshold:
            Chat.sync(cur_time)

    @staticmethod
    def sync(cur_time: int = time.time()):
        '''
        持久化
        '''

        # with Chat._sync_lock:
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
        is_plain_text = self.chat_data.is_plain_text

        # 在复读，不学
        if pre_msg['raw_message'] == raw_message:
            return

        # 回复别人的，不学
        if '[CQ:reply,' in raw_message:
            return

        update_key = {
            'group_id': self.chat_data.group_id,
            'pre_is_plain_text': pre_msg['is_plain_text'],
            'cur_is_plain_text': is_plain_text
        }

        if is_plain_text:
            update_key['cur_keywords'] = self.chat_data.keywords
        else:
            update_key['cur_raw_msg'] = raw_message

        if pre_msg['is_plain_text']:
            update_key['pre_keywords'] = pre_msg['keywords']
        else:
            update_key['pre_raw_msg'] = pre_msg['raw_message']

        dict_key = tuple(sorted(update_key.items()))
        if dict_key not in Chat._context_dict:
            Chat._context_dict[dict_key] = [update_key, ]

        Chat._context_dict[dict_key].append({
            'time': self.chat_data.time,
            'raw_message': raw_message
        })

        # context_mongo.update_one(update_key, update_value, upsert=True)

    @staticmethod
    def sync_context():

        save_list = []
        for value in Chat._context_dict.values():
            if len(value) - 1 < Chat._count_threshold - 1   \
                    and value[-1]['time'] < time.time() - 7 * 24 * 3600:
                continue
            insert_value = value[0].copy()
            insert_value['time'] = value[-1]['time']
            insert_value['count'] = len(value) - 1
            insert_value['cur_raw_msg_options'] = []
            for item in value[1:]:
                insert_value['cur_raw_msg_options'].append(item['raw_message'])

            save_list.append(insert_value)

        Chat._context_dict.clear()
        context_mongo.insert_many(save_list)

    def _context_find(self) -> Optional[List[str]]:

        rand = random.randint(0, 100)
        if rand < 30:
            count_thres = Chat._count_threshold - 1
        elif rand < 60:
            count_thres = Chat._count_threshold
        else:
            count_thres = Chat._count_threshold + 1

        group_id = self.chat_data.group_id
        raw_message = self.chat_data.raw_message

        # 复读！
        if group_id in Chat._message_dict:
            group_msg = Chat._message_dict[group_id]
            if group_msg:
                if all(item['raw_message'] == raw_message
                        for item in group_msg[:-count_thres:-1]):
                    return [raw_message, ]

        if self.chat_data.is_plain_text:
            all_answers = context_mongo.find({
                'pre_keywords': self.chat_data.keywords,
                'count': {'$gt': count_thres}
            })
        elif self.chat_data.is_image:
            all_answers = context_mongo.find({
                'pre_raw_msg': raw_message,
                'count': {'$gt': count_thres},
                'cur_raw_msg': {'$regex': '^\[CQ:'}
            })
        else:
            all_answers = context_mongo.find({
                'pre_raw_msg': raw_message,
                'count': {'$gt': count_thres}
            })
        filtered_answers = []
        answers_count = defaultdict(int)
        for answer in all_answers:
            if answer['group_id'] == group_id:
                filtered_answers.append(answer)
                continue
            elif answer['cur_is_plain_text']:
                answers_count[answer['cur_keywords']] += 1
                cur_count = answers_count[answer['cur_keywords']]
            elif '[CQ:at,' in answer['cur_raw_msg']:    # 别的群的 at, 过滤掉
                continue
            else:
                answers_count[answer['cur_raw_msg']] += 1
                cur_count = answers_count[answer['cur_raw_msg']]

            if cur_count == count_thres:    # 有这么多个群都有相同的回复，就作为全局回复
                filtered_answers.append(answer)

        if not len(filtered_answers):
            return None

        # count 越大的结果，回复的概率越大
        count_seg = []
        count_sum = 0
        for answer in filtered_answers:
            count_sum += answer['count'] ** 2
            count_seg.append(count_sum)
        rand_value = random.randint(0, count_sum)
        rand_index = 0
        for index in range(len(count_seg)):
            if rand_value < count_seg[index]:
                rand_index = index
                break

        final_answer = filtered_answers[rand_index]
        if final_answer['cur_is_plain_text']:
            answer_str = random.choice(
                final_answer['cur_raw_msg_options'])
        else:
            answer_str = final_answer['cur_raw_msg']

        if 0 < answer_str.count('，') <= 3 and random.randint(1, 10) < 5:
            return answer_str.split('，')
        return [answer_str, ]


def _chat_sync():
    Chat.sync()


# Auto sync on program exit
atexit.register(_chat_sync)


if __name__ == '__main__':

    while True:
        test_data: ChatData = ChatData(
            group_id=1234567,
            user_id=1111111,
            raw_message='牛牛出来玩',
            plain_text='牛牛出来玩',
            time=time.time()
        )

        test_chat: Chat = Chat(test_data)

        print(test_chat.answer())
        test_chat.learn()

        test_answer_data: ChatData = ChatData(
            group_id=1234567,
            user_id=1111111,
            raw_message='别烦，我学MySql啊',
            plain_text='别烦，我学MySql啊',
            time=time.time()
        )

        test_answer: Chat = Chat(test_answer_data)
        test_answer.learn()
