from pydantic import BaseSettings


class Config(BaseSettings):

    enable_voice = False

    """ 你的 APPID AK SK """
    APP_ID = '你的 App ID'
    API_KEY = '你的 Api Key'
    SECRET_KEY = '你的 Secret Key'

    class Config:
        extra = "ignore"
