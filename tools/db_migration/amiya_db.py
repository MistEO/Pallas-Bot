from peewee import *

sqlite_db = SqliteDatabase('amiya.db',
                           pragmas={
                               'timeout': 30
                           },
                           check_same_thread=False)


class AmiyaDataBase:
    @staticmethod
    def create_base():
        tables = (
            MsgRecord,
            ReplyRecord)

        for item in tables:
            item.create_table()


class BaseModel(Model):
    class Meta:
        database = sqlite_db


class MsgRecord(BaseModel):
    id = IntegerField(primary_key=True, constraints=[SQL('autoincrement')])
    group_id = IntegerField()
    user_id = IntegerField()
    msg = TextField()
    msg_text = TextField(default='')
    time = BigIntegerField(default=0)

class ReplyRecord(BaseModel):
    id = IntegerField(primary_key=True, constraints=[SQL('autoincrement')])
    group_id = IntegerField()
    pre_msg = TextField()
    reply_msg = TextField()
    count = IntegerField(default=1)
    pre_msg_text = TextField(default='')
    reply_msg = TextField(default='')

class LatestAutoReply(BaseModel):
    group_id = IntegerField(primary_key=True)
    msg = TextField(default='')
    msg_text = TextField(default='')
    time = BigIntegerField(default=0)
    
