import os
from pathlib import Path
from pydantic import BaseModel, Extra
from nonebot import get_driver
from pyncm import apis as ncm
from src.common.utils.download_tools import DownloadTools


class Config(BaseModel, extra=Extra.ignore):
    NCM_PHONE: str = ""
    NCM_EMAIL: str = ""
    NCM_PASSWORD: str = ""
    NCM_CTCODE: int = 86
    NCM_REMERBER_LOGIN: bool = True


config = Config.parse_obj(get_driver().config)

if config.NCM_PHONE and config.NCM_PASSWORD:
    ncm.login.LoginViaCellphone(
        phone=config.NCM_PHONE, password=config.NCM_PASSWORD, ctcode=config.NCM_CTCODE, rememberLogin=config.NCM_REMERBER_LOGIN)
elif config.NCM_EMAIL and config.NCM_PASSWORD:
    ncm.login.LoginViaEmail(email=config.NCM_EMAIL, password=config.NCM_PASSWORD,
                            rememberLogin=config.NCM_REMERBER_LOGIN)
else:
    ncm.login.LoginViaAnonymousAccount()


def get_song_path(song_id):
    folder = Path("resource/sing/ncm")
    path = folder / f"{song_id}.mp3"
    if os.path.exists(path):
        return path

    url = get_song_url(song_id)
    if not url:
        return None

    content = request_file(url)
    if not content:
        return None

    os.makedirs(folder, exist_ok=True)
    with open(path, mode='wb+') as voice:
        voice.write(content)

    return path


def get_song_url(song_id):
    response = ncm.track.GetTrackAudio(song_id)
    return response["data"][0]["url"]


def request_file(url):
    return DownloadTools.request_file(url)
