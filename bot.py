from aiogram import Bot
import os

bot = Bot(token=os.getenv("BOT_TOKEN"))
ADMIN_ID = os.getenv("ADMIN_ID")

async def send_owner_notif(pesan: str):
    try:
        await bot.send_message(chat_id=ADMIN_ID, text=pesan, parse_mode="HTML")
    except Exception as e:
        print(f"Gagal kirim notif: {e}")