from pydantic import BaseSettings

class Config(BaseSettings):

  # catcat-about plugin config
  plugin_setting:str = "default" 
  baidu_api_ak:str="ak"
  pixiv_refresh_token:str="pk"
  recall_nsfw_pic_probability:float = 0.9
  class Config:
    extra = "ignore"  