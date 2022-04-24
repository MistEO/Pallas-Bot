from pydantic import BaseSettings
import os


class Config(BaseSettings):
    safe_accounts = []

    class Config:
        extra = "ignore"
