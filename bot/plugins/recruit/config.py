from pydantic import BaseSettings


class Config(BaseSettings):
    baiduApiSwitch = False
    APP_ID = ''
    API_KEY = ''
    SECRET_KEY = ''

    class Config:
        extra = "ignore"
