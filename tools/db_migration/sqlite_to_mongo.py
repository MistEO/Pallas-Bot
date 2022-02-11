import pallas_db
import pallas_mongo


message_id = -1

all_count = pallas_db.Message.select().count()
cur_count = 0

started = False

pallas_mongo.Chat.save_count_threshold = 10000
pallas_mongo.Chat.save_time_threshold = 7 * 24 * 3600

while True:
    message = pallas_db.Message.select().where(
        pallas_db.Message.id > message_id).limit(10000)

    if not message:
        break
    message_id = message[-1].id
    message_len = message.count()

    prg: int = 0
    default_time = 1
    for index in range(message_len):
        cur_message = message[index]

        if cur_message.time == 0:
            time = default_time
            default_time += 1
        else:
            time = cur_message.time

        data = pallas_mongo.ChatData(
            cur_message.group, cur_message.user, cur_message.raw_msg, cur_message.text_msg, time
        )
        pallas_mongo.Chat(data).learn()

        if not started:
            started = True
            print('started')

    cur_count += message_len
    print('cur:', cur_count, "all:", all_count)
    print(cur_count / all_count * 100, '%')

print('sync')
pallas_mongo.Chat.sync()
pallas_mongo.Chat.sync_context()
print('finished')
