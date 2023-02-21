import os
import requests
from pathlib import Path
from pydantic import BaseModel, Extra
from nonebot import get_driver
from pyncm import apis as ncm
from src.common.utils.download_tools import DownloadTools


class Config(BaseModel, extra=Extra.ignore):
    ncm_phone: str = ""
    ncm_email: str = ""
    ncm_password: str = ""
    ncm_ctcode: int = 86


config = Config.parse_obj(get_driver().config)

if config.ncm_phone and config.ncm_password:
    ncm.login.LoginViaCellphone(
        phone=config.ncm_phone, password=config.ncm_password, ctcode=config.ncm_ctcode)
elif config.ncm_email and config.ncm_password:
    ncm.login.LoginViaEmail(email=config.ncm_email,
                            password=config.ncm_password)
else:
    ncm.login.LoginViaAnonymousAccount()


def download(song_id):
    folder = Path("resource/sing/ncm")
    path = folder / f"{song_id}.mp3"
    if path.exists():
        return path

    url = get_audio_url(song_id)
    if not url:
        return None

    content = request_file(url)
    if not content:
        return None

    os.makedirs(folder, exist_ok=True)
    with open(path, mode='wb+') as voice:
        voice.write(content)

    return path


def get_audio_url(song_id):
    response = ncm.track.GetTrackAudio(song_id)
    if response["data"][0]["size"] > 20000000:  # 20MB
        return None
    return response["data"][0]["url"]


def request_file(url):
    return DownloadTools.request_file(url)


def get_song_title(song_id):
    response = ncm.track.GetTrackDetail(song_id)
    return response["songs"][0]["name"]


def get_song_id(song_name: str):
    if not song_name:
        return None

    url = 'http://music.163.com/api/search/get/'
    params = {'s': song_name, 'type': 1, 'limit': 1}
    r = requests.get(url, params=params)
    r_json = r.json()
    if r_json['code'] != 200:
        return None
    if not r_json['result']['songs']:
        return None
    song_id = r_json['result']['songs'][0]['id']
    return song_id
