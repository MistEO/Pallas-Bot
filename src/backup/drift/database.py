from peewee import *

sqlite_db = SqliteDatabase('drift.db',
                           pragmas={
                               'timeout': 30
                           },
                           check_same_thread=False)


class DataBase:
    @staticmethod
    def create_base():
        tables = (
            Drift,
            PickRecord,
            )

        for item in tables:
            item.create_table()


class BaseModel(Model):
    class Meta:
        database = sqlite_db


# 漂流瓶
class Drift(BaseModel):
    drift_id = IntegerField(primary_key=True, constraints=[SQL('autoincrement')])
    user_id = IntegerField()
    group_id = IntegerField()
    content = TextField()
    time = BigIntegerField()
    is_picked = BooleanField(default=False)
    picked_times = IntegerField(default=0)
    is_banned = BooleanField(default=False)
    # pick_user_id = IntegerField(default=0)
    # pick_group_id = IntegerField(default=0)
    # pick_time = BigIntegerField(default=0)

# 捡瓶子的记录
class PickRecord(BaseModel):
    drift_id = IntegerField()
    user_id = IntegerField()
    group_id = IntegerField()
    time = BigIntegerField()