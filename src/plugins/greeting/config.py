from pydantic import BaseSettings

class Config(BaseSettings):
  greeting_groups = []

  class Config:
    extra = "ignore"