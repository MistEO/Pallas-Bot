import requests


def get_song_id(song_name: str):
    url = 'http://music.163.com/api/search/get/'
    params = {'s': song_name, 'type': 1, 'limit': 1}
    r = requests.get(url, params=params)
    r_json = r.json()
    song_id = r_json['result']['songs'][0]['id']
    return song_id
