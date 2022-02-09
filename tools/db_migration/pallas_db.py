from peewee import *

sqlite_db = SqliteDatabase('repeater.db',
                           pragmas={
                               'timeout': 30
                           },
                           check_same_thread=False)


class DataBase:
    @staticmethod
    def create_base():
        tables = (
            Message,
            Context,
            Reply)

        for item in tables:
            item.create_table()


class BaseModel(Model):
    class Meta:
        database = sqlite_db


# 所有消息记录
class Message(BaseModel):
    id = IntegerField(primary_key=True, constraints=[SQL('autoincrement')])
    group = IntegerField()
    user = IntegerField()
    raw_msg = TextField()
    is_plain_text = BooleanField(default=False)
    text_msg = TextField(default='')
    pinyin_msg = TextField(default='')
    time = BigIntegerField()


# 聊天记录对话上下文
class Context(BaseModel):
    group = IntegerField()
    above_raw_msg = TextField()
    above_is_plain_text = BooleanField(default=False)
    above_text_msg = TextField(default='')
    above_pinyin_msg = TextField(default='')
    below_raw_msg = TextField()
    count = IntegerField(default=1)
    latest_time = BigIntegerField()

    class Meta:
        primary_key = CompositeKey('group', 'above_raw_msg', 'below_raw_msg')


# Bot发送的消息记录
class Reply(BaseModel):
    id = IntegerField(primary_key=True, constraints=[SQL('autoincrement')])
    group = IntegerField()
    is_proactive = BooleanField(default=False)
    above_raw_msg = TextField(default='')
    reply_raw_msg = TextField()
    time = BigIntegerField()


# # 用户画像
# class UserPortrait(BaseModel):
#     id = IntegerField(primary_key=True, constraints=[SQL('autoincrement')])
#     group = IntegerField()
#     user = IntegerField()
#     raw_msg = TextField()
#     is_plain_text = BooleanField(default=False)
#     text_msg = TextField(default='')
#     pinyin_msg = TextField(default='')
#     count = IntegerField(default=1)
#     latest_time = BigIntegerField()
