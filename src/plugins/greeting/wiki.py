import os
import random

# 这里的值是CN不代表是中文语音，wiki的定义有点怪，所有语言都叫CN_xx
# 实际的url类似 'https://static.prts.wiki/voice_jp/char_485_pallas/CN_01.wav'
# TODO: 现在只用到了这些，懒得写了，之后可以补充全
voice_dict = {
    '任命助理': 'CN_001',
    '交谈1': 'CN_002',
    '交谈2': 'CN_003',
    '交谈3': 'CN_004',
    '晋升后交谈1': 'CN_005',
    '晋升后交谈2': 'CN_006',
    '信赖提升后交谈1': 'CN_007',
    '信赖提升后交谈2': 'CN_008',
    '信赖提升后交谈3': 'CN_009',
    '闲置': 'CN_010',
    '干员报到': 'CN_011',
    '精英化晋升1': 'CN_013',
    '精英化晋升2': 'CN_014',
    '编入队伍': 'CN_017',
    '任命队长': 'CN_018',
    '戳一下': 'CN_034',
    '信赖触摸': 'CN_036',
    '问候': 'CN_042',
}


voices_source = 'resource/voices'


class WikiVoice():
    def get_voice_filename(self, operator, key):
        if key not in voice_dict:
            return None

        f = f'{voices_source}/{operator}/{key}.wav'
        if not os.path.exists(f):
            return None
        return f

    def get_random_voice(self, operator, ranges):
        key = random.choice([r for r in ranges if r in voice_dict])
        return self.get_voice_filename(operator, key)
