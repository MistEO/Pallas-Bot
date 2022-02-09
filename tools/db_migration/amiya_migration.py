import tools.db_migration.pallas_db as pallas_db
import tools.db_migration.amiya_db as amiya_db

import json
import pypinyin


def text_to_pinyin(text: str):
    return ''.join([item[0] for item in pypinyin.pinyin(
        text, style=pypinyin.NORMAL, errors='default')]).lower()

# return [cq_result: str, is_plain_text: bool, msg_text: str, msg_pinyin: str]


def mirai2cq(msg: str):
    seg = json.loads(msg)
    is_plain_text = True
    res = ''
    msg_text = ''
    for item in seg:
        if item['type'] == 'Plain':
            res += item['text']
            msg_text += item['text']
        elif item['type'] == 'At':
            is_plain_text = False
            target = item['target']
            res += '[CQ:at,qq={}]'.format(target)
        elif item['type'] == 'Image':
            is_plain_text = False
            imageId = item['imageId'].replace(
                '{', '').replace('}', '').replace('-', '')
            imageId = imageId.split('.')[0]
            imageId = imageId.lower()
            res += '[CQ:image,file={}.image]'.format(imageId)
        elif item['type'] == 'File':
            is_plain_text = False
        elif item['type'] == 'Quote':
            is_plain_text = False
        elif item['type'] == 'Face':
            is_plain_text = False
        else:
            is_plain_text = False
            print('type error', item['type'])

    return res, is_plain_text, msg_text, text_to_pinyin(msg_text)


def migrate_message():
    all_msg = amiya_db.MsgRecord.select()

    data = []
    for item in all_msg:
        if item.group_id == 716692626:  # 测试群
            continue
        raw_msg, is_pt, pt, pinyin = mirai2cq(item.msg)
        # print(raw_msg, is_pt, pt, pinyin)
        if raw_msg:
            data.append(
                {'group': item.group_id,
                 'user': item.user_id,
                 'raw_msg': raw_msg,
                 'is_plain_text': is_pt,
                 'text_msg': pt,
                 'pinyin_msg': pinyin,
                 'time': item.time}
            )
    num = 30000
    for i in range(0, len(data), num):
        pallas_db.Message.insert_many(data[i:i+num]).execute()


def migrate_context():
    all_msg = amiya_db.ReplyRecord.select()

    data = []
    for item in all_msg:
        if item.group_id == 716692626:  # 测试群
            continue
        raw_msg, is_pt, pt, pinyin = mirai2cq(item.pre_msg)
        rep_raw_msg, rep_is_pt, _2, _3 = mirai2cq(item.reply_msg)

        if raw_msg and rep_raw_msg:
            # 有一部分回复图的链接挂了，直接所有的都不迁移了
            if 'CQ:image' in rep_raw_msg:
                continue
            data.append({
                'group': item.group_id,
                'above_raw_msg': raw_msg,
                'above_is_plain_text': is_pt,
                'above_text_msg': pt,
                'above_pinyin_msg': pinyin,
                'below_raw_msg': rep_raw_msg,
                'count': item.count,
                'latest_time': 0})
    num = 30000
    for i in range(0, len(data), num):
        pallas_db.Context.insert_many(
            data[i:i+num]).on_conflict('replace').execute()


def strip_message():
    all_msg = pallas_db.Message.select()

    for item in all_msg:
        if item.raw_msg.endswith(' ') or item.raw_msg.startswith(' '):
            pallas_db.Message.update(
                raw_msg=item.raw_msg.strip(),
                text_msg=item.text_msg.strip(),
            ).where(
                pallas_db.Message.id == item.id
            ).execute()


def strip_context():
    all_msg = pallas_db.Context.select()
    for item in all_msg:
        if item.above_raw_msg.endswith(' ') or item.above_raw_msg.startswith(' ') or item.below_raw_msg.endswith(' ') or item.below_raw_msg.startswith(' '):
            pallas_db.Context.delete().where(
                pallas_db.Context.group == item.group,
                pallas_db.Context.above_raw_msg == item.above_raw_msg,
                pallas_db.Context.above_is_plain_text == item.above_is_plain_text,
                pallas_db.Context.above_text_msg == item.above_text_msg,
                pallas_db.Context.above_pinyin_msg == item.above_pinyin_msg,
                pallas_db.Context.below_raw_msg == item.below_raw_msg,
                pallas_db.Context.count == item.count,
                pallas_db.Context.latest_time == item.latest_time,).execute()

            item.above_raw_msg = item.above_raw_msg.strip()
            item.above_text_msg = item.above_text_msg.strip()
            item.below_raw_msg = item.below_raw_msg.strip()

            pallas_db.Context.insert(
                group=item.group,
                above_raw_msg=item.above_raw_msg,
                above_is_plain_text=item.above_is_plain_text,
                above_text_msg=item.above_text_msg,
                above_pinyin_msg=item.above_pinyin_msg,
                below_raw_msg=item.below_raw_msg,
                count=item.count,
                latest_time=item.latest_time,
            ).on_conflict('replace').execute()


def tutu2niuniu_context():
    all_msg = pallas_db.Context.select().where(
        (pallas_db.Context.above_raw_msg.contains('兔兔')) |
        (pallas_db.Context.below_raw_msg.contains('兔兔'))
    )
    for item in all_msg:
        pallas_db.Context.delete().where(
            pallas_db.Context.group == item.group,
            pallas_db.Context.above_raw_msg == item.above_raw_msg,
            pallas_db.Context.above_is_plain_text == item.above_is_plain_text,
            pallas_db.Context.above_text_msg == item.above_text_msg,
            pallas_db.Context.above_pinyin_msg == item.above_pinyin_msg,
            pallas_db.Context.below_raw_msg == item.below_raw_msg,
            pallas_db.Context.count == item.count,
            pallas_db.Context.latest_time == item.latest_time,).execute()

        item.above_raw_msg = item.above_raw_msg.replace('兔兔', '牛牛')
        item.above_text_msg = item.above_text_msg.replace('兔兔', '牛牛')
        item.above_pinyin_msg = item.above_pinyin_msg.replace('tutu', 'niuniu')
        item.below_raw_msg = item.below_raw_msg.replace('兔兔', '牛牛')

        pallas_db.Context.insert(
            group=item.group,
            above_raw_msg=item.above_raw_msg,
            above_is_plain_text=item.above_is_plain_text,
            above_text_msg=item.above_text_msg,
            above_pinyin_msg=item.above_pinyin_msg,
            below_raw_msg=item.below_raw_msg,
            count=item.count,
            latest_time=item.latest_time,
        ).on_conflict('ignore').execute()


def text2pinyin_context():
    all_plain = pallas_db.Context.select().where(
        pallas_db.Context.above_is_plain_text == True)

    len = all_plain.count()
    count = 0
    for item in all_plain:
        pinyin = text_to_pinyin(item.above_text_msg)
        # for ch in ' ，。？！（）…—【】、“”：；《》‘’￥『』': # with space
        #     pinyin = pinyin.replace(ch, '')
        # print(pinyin)
        pallas_db.Context.update(
            above_pinyin_msg=pinyin,
        ).where(
            pallas_db.Context.group == item.group,
            pallas_db.Context.above_raw_msg == item.above_raw_msg,
            pallas_db.Context.below_raw_msg == item.below_raw_msg,
        ).execute()

        count = count + 1
        if count % 100 == 0:
            print('text2pinyin_context: ', count / len * 100, "%")


def text2pinyin_message():

    all_plain = pallas_db.Message.select().where(
        pallas_db.Message.is_plain_text == True)

    len = all_plain.count()
    count = 0
    for item in all_plain:
        pinyin = text_to_pinyin(item.text_msg)
        pallas_db.Message.update(
            pinyin_msg=pinyin,
        ).where(
            pallas_db.Message.id == item.id,
        ).execute()

        count = count + 1
        if count % 100 == 0:
            print('text2pinyin_message: ', count / len * 100, "%")


if __name__ == '__main__':
    amiya_db.AmiyaDataBase.create_base()
    pallas_db.DataBase.create_base()

    text2pinyin_context()
    text2pinyin_message()
