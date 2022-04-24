from pydantic import BaseSettings
import os

class Config(BaseSettings):
    accounts = os.listdir('accounts')
    safe_accounts = []

    class Config:
        extra = "ignore"
