import os
import traceback
import requests
import random

# 这里的值是CN不代表是中文语音，wiki的定义有点怪，所有语言都叫CN_xx
# 实际的url类似 'https://static.prts.wiki/voice_jp/char_485_pallas/CN_01.wav'
voice_dict = {
    '问候': 'CN_042',
    '闲置': 'CN_010',
    '交谈1': 'CN_002',
    '交谈2': 'CN_003',
    '交谈3': 'CN_004',
    '晋升后交谈1': 'CN_005',
    '晋升后交谈2': 'CN_006',
    '信赖提升后交谈1': 'CN_007',
    '信赖提升后交谈2': 'CN_008',
    '信赖提升后交谈3': 'CN_009',
    '戳一下': 'CN_034',
    '信赖触摸': 'CN_036',
    '干员报到': 'CN_011',
    '精英化晋升1': 'CN_013',
    '编入队伍': 'CN_017',
    '任命队长': 'CN_001'
}


voices_source = 'resource/voices'


class DownloadTools:
    @staticmethod
    def request_file(url, stringify=True):
        headers = {
            'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 10_3_1 like Mac OS X) '
                          'AppleWebKit/603.1.30 (KHTML, like Gecko) Version/10.0 Mobile/14E304 Safari/602.1'
        }
        # noinspection PyBroadException
        try:
            stream = requests.get(url, headers=headers, stream=True)
            if stream.status_code == 200:
                if stringify:
                    return str(stream.content, encoding='utf-8')
                else:
                    return stream.content
        except Exception:
            print(traceback.format_exc())
        return None


class WikiVoice(DownloadTools):
    def download_voice_from_wiki(self, operator, url, filename):
        folder = f'{voices_source}/{operator}'
        f = f'{folder}/{filename}'
        print('Downloading', url, "as", filename, "to", folder)
        if os.path.exists(f):
            print("Already exists")
            return

        content = self.request_file(url, stringify=False)
        if content:
            os.makedirs(folder, exist_ok=True)
            with open(f, mode='wb+') as voice:
                voice.write(content)
        else:
            print("Download failed!")

    def download_voices(self, folder, oper_id):
        base_url = f'https://static.prts.wiki/voice/{oper_id}/'
        for key, web_file in voice_dict.items():
            url = f'{base_url}{web_file}.wav'
            filename = f'{key}.wav'
            self.download_voice_from_wiki(folder, url, filename)

    def get_voice_filename(self, operator, key):
        if key not in voice_dict:
            return None

        f = f'{voices_source}/{operator}/{key}.wav'
        if not os.path.exists(f):
            return None
        return f

    def get_random_voice(self, operator):
        key = random.choice(list(voice_dict.keys()))
        return self.get_voice_filename(operator, key)


if __name__ == '__main__':
    operator = 'Pallas'
    wiki = WikiVoice()
    wiki.download_voices('Pallas', 'char_485_pallas')

    print(wiki.get_random_voice(operator))
