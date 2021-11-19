from pydantic import BaseSettings

class Config(BaseSettings):

  # catcat-about plugin config
  plugin_setting:str = "default" 
  recall_nsfw_pic_probability:float = 0.9
  class Config:
    extra = "ignore"  