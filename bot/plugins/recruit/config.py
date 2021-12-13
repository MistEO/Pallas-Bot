from pydantic import BaseSettings


class Config(BaseSettings):
    recruitSwitch = False
    APP_ID = ''
    API_KEY = ''
    SECRET_KEY = ''

    class Config:
        extra = "ignore"
