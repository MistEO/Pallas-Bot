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

from nonebot.adapters import Event

mongo_client = pymongo.MongoClient('127.0.0.1', 27017)

mongo_db = mongo_client['PallasBot']

mongo_message = mongo_db['message']
mongo_context = mongo_db['context']

reply_dict = {}


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
    def keywords(self) -> List[str]:
        if not self.is_plain_text:
            return []

        keywords_list = jieba_fast.analyse.extract_tags(
            self.plain_text, topK=ChatData._keywords_size)
        keywords_list.sort()
        if len(keywords_list) == 0:
            return [self.plain_text, ]
        else:
            return keywords_list

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

        if self.chat_data.group_id in reply_dict:
            latest_reply = reply_dict[self.chat_data.group_id]
            # 限制发音频率，最多 5 秒一次
            if self.chat_data.time - latest_reply['time'] < 5:
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
            reply_dict[self.chat_data.group_id] = {
                'time': (int)(time.time()),
                'cur_msg': result[-1],
                'pre_msg': self.chat_data.raw_message
            }
        return result

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

        # 回复别人的，不学
        if '[CQ:reply,' in self.chat_data.raw_message:
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
            set_value['$push'] = {
                'cur_raw_msg_options': self.chat_data.raw_message
            }

        mongo_context.update_one(update_key, set_value, upsert=True)

    def _context_find(self) -> Optional[List[str]]:

        rand = random.randint(0, 100)
        if rand < 30:
            count_thres = Chat._count_threshold - 1
        elif rand < 60:
            count_thres = Chat._count_threshold
        else:
            count_thres = Chat._count_threshold + 1

        # hist_msg = mongo_message.find({
        #     'group_id': self.chat_data.group_id,
        # }, sort=[('time', pymongo.DESCENDING)]).limit(count_thres)

        # # 复读！
        # if hist_msg:
        #     is_repeat = True
        #     for item in hist_msg:
        #         if self.chat_data.raw_message != item.raw_message:
        #             is_repeat = False
        #             break
        #     if is_repeat:
        #         return [self.chat_data.raw_message, ]

        if self.chat_data.is_plain_text:
            all_answers = mongo_context.find({
                'pre_keywords': self.chat_data.keywords,
                'count': {'$gt': count_thres}
            })
        elif self.chat_data.is_image:
            all_answers = mongo_context.find({
                'pre_raw_msg': self.chat_data.raw_message,
                'count': {'$gt': count_thres},
                'cur_raw_msg': {'$regex': '^\[CQ:'}
            })
        else:
            all_answers = mongo_context.find({
                'pre_raw_msg': self.chat_data.raw_message,
                'count': {'$gt': count_thres}
            })
        filtered_answers = []
        answers_count = defaultdict(int)
        for answer in all_answers:
            if answer['group_id'] == self.chat_data.group_id:
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


if __name__ == '__main__':
    test_data: ChatData = ChatData(
        group_id=1234567,
        user_id=1111111,
        raw_message='牛牛出来玩',
        plain_text='牛牛出来玩',
        time=time.time() - 1
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
