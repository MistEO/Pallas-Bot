from pydantic import BaseSettings

class Config(BaseSettings):

  # catcat-about plugin config
  plugin_setting:str = "default" 
  baidu_api_ak:str="ak"
  pixiv_refresh_token="pk"

  class Config:
    extra = "ignore"  