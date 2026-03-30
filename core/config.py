import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    BOT_TOKEN = os.getenv("BOT_TOKEN")
    ADMIN_ID = os.getenv("ADMIN_ID")
    SECRET_TOKEN = os.getenv("SECRET_TOKEN")
    ADMIN_USER = os.getenv("ADMIN_USER")
    ADMIN_PASS = os.getenv("ADMIN_PASS")
    # Setting lainnya...