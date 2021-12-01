from pydantic import BaseSettings

class Config(BaseSettings):
  greetings_groups = []

  class Config:
    extra = "ignore"