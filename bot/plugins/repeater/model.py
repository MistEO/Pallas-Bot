from typing import List, Optional, Union
from functools import cached_property
from dataclasses import dataclass

import jieba_fast.analyse
import pypinyin
import pymongo

from nonebot.adapters import Event

mongo_client = pymongo.MongoClient('127.0.0.1', 27017)

mongo_db = mongo_client['PallasBot']

mongo_message = mongo_db['message']
mongo_context = mongo_db['context']

reply_time_dict = {}


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
        if '[CQ:' not in self.raw_message:
            return True
        else:
            return False

    @cached_property
    def keywords(self) -> List[str]:
        if not self.is_plain_text:
            return []

        return jieba_fast.analyse.extract_tags(
            self.plain_text, topK=ChatData._keywords_size)

    @cached_property
    def keywords_pinyin(self) -> List[str]:
        pinyin_list = []
        for text in self.keywords:
            text_pinyin = ''.join([item[0] for item in pypinyin.pinyin(
                text, style=pypinyin.NORMAL, errors='default')]).lower()

            pinyin_list.append(text_pinyin)

        return pinyin_list


class Chat:
    _count_threshold = 3

    def __init__(self, data: Union[ChatData, Event]):

        if (isinstance(data, ChatData)):
            self.chat_data = data
        elif (isinstance(data, Event)):
            event_dict = data.dict()
            self.chat_data = ChatData(
                group_id=event_dict['group_id'],
                user_id=event_dict['user_id'],
                raw_message=event_dict['raw_message'],
                plain_text=data.get_plaintext(),
                time=event_dict['time']
            )

    def learn(self):
        '''
        学习这句话
        '''

        # 群里的上一条发言
        group_pre_msg = mongo_message.find_one({
            'group_id': self.chat_data.group_id
        }, sort=[('time', pymongo.DESCENDING)])

        self._context_insert(group_pre_msg)

        if group_pre_msg and group_pre_msg['user_id'] != self.chat_data.user_id:
            # 该用户在群里的上一条发言
            user_pre_msg = mongo_message.find_one({
                'group_id': self.chat_data.group_id,
                'user_id': self.chat_data.user_id
            }, sort=[('time', pymongo.DESCENDING)])

            self._context_insert(user_pre_msg)

        self._message_insert()

    def answer(self) -> Optional[List[str]]:
        '''
        回复这句话，可能会分多次回复（所以是List），也可能不回复
        '''
        pass

    def _message_insert(self):
        mongo_message.insert_one({
            'group_id': self.chat_data.group_id,
            'user_id': self.chat_data.user_id,
            'raw_message': self.chat_data.raw_message,
            'is_plain_text': self.chat_data.is_plain_text,
            'plain_text': self.chat_data.plain_text,
            'keywords': self.chat_data.keywords,
            'time': self.chat_data.time,
        })

    def _context_insert(self, pre_msg):
        if not pre_msg:
            return

        # 在复读，不学
        if pre_msg['raw_message'] == self.chat_data.raw_message:
            return

        # # 如果有反过来的，直接退出，说明可能是两句话在轮流复读。只取正向的（先达到阈值的）
        # reverse = mongo_context.find_one({
        #     'group_id': self.chat_data.group_id,
        #     'pre_raw_msg': self.chat_data.raw_message,
        #     'cur_raw_msg': pre_msg.raw_message,
        #     'count': {'$gt': ChatData._count_threshold}
        # })
        # if reverse:
        #     return

        update_key = {
            'group_id': self.chat_data.group_id,
            'pre_is_plain_text': pre_msg['is_plain_text'],
            'cur_is_plain_text': self.chat_data.is_plain_text
        }

        if self.chat_data.is_plain_text:
            update_key['cur_keywords'] = self.chat_data.keywords
        else:
            update_key['cur_raw_msg'] = self.chat_data.raw_message

        if pre_msg['is_plain_text']:
            update_key['pre_keywords'] = pre_msg['keywords']
        else:
            update_key['pre_raw_msg'] = pre_msg['raw_message']

        update_value = update_key.copy()
        update_value['time'] = self.chat_data.time
        # update_value['count'] = 1

        set_value = {}
        set_value['$set'] = update_value
        set_value['$inc'] = {
            'count': 1
        }
        if self.chat_data.is_plain_text:
            nested = 'cur_raw_msg_options.' + self.chat_data.raw_message
            set_value['$inc'][nested] = 1

        print(set_value)
        mongo_context.update_one(update_key, set_value, upsert=True)


if __name__ == '__main__':

    import time

    test_data: ChatData = ChatData(
        group_id=1234567,
        user_id=1111111,
        raw_message='牛牛出来玩',
        plain_text='牛牛出来玩',
        time=time.time() - 1
    )

    test_chat: Chat = Chat(test_data)
    test_chat.learn()

    test_data: ChatData = ChatData(
        group_id=1234567,
        user_id=1111111,
        raw_message='别烦，我学MySql啊',
        plain_text='别烦，我学MySql啊',
        time=time.time()
    )

    test_chat: Chat = Chat(test_data)
    test_chat.learn()
