from pydantic import BaseSettings

class Config(BaseSettings):

  # catcat-about plugin config
  plugin_setting:str = "default" 
  nicknameList =  "牛牛,帕拉斯"
  textAnalyseSwitch = True
  APP_ID = '1'
  API_KEY = '1'
  SECRET_KEY = '1'
  class Config:
    extra = "ignore"  