from pydantic import BaseSettings

class Config(BaseSettings):

  bili_user = []
  bili_push_groups = []
  
  github_repo = []
  github_push_groups = []

  weibo_id = []
  weibo_push_groups = []

  class Config:
    extra = "ignore"