import asyncio
import logging
import base64
import os
from typing import List, Dict, Any
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart
from aiogram.dispatcher.middlewares.base import BaseMiddleware
import aiohttp
from aiohttp import web

# Берём ключи из переменных окружения или ставим свои значения по умолчанию
BOT_TOKEN = os.getenv("BOT_TOKEN", "ТВОЙ_ТОКЕН_БОТА")
IMGBB_API_KEY = os.getenv("IMGBB_API_KEY", "ТВОЙ_API_КЛЮЧ_IMGBB")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# Middleware для сборки нескольких фото из альбома
class AlbumMiddleware(BaseMiddleware):
    def __init__(self, latency: float = 0.6):
        self.latency = latency
        self.album_data: Dict[str, List[types.Message]] = {}

    async def __call__(self, handler, event: types.Message, data: Dict[str, Any]):
        if not event.media_group_id:
            return await handler(event, data)

        try:
            self.album_data[event.media_group_id].append(event)
            return
        except KeyError:
            self.album_data[event.media_group_id] = [event]
            await asyncio.sleep(self.latency)
            data["album"] = self.album_data.pop(event.media_group_id)
            return await handler(event, data)

dp.message.middleware(AlbumMiddleware())

# Загрузка фото на ImgBB
async def upload_image_to_imgbb(session: aiohttp.ClientSession, photo: types.PhotoSize) -> str:
    file_info = await bot.get_file(photo.file_id)
    downloaded_file = await bot.download_file(file_info.file_path)
    base64_image = base64.b64encode(downloaded_file.read()).decode('utf-8')

    upload_url = "https://api.imgbb.com/1/upload"
    payload = {
        "key": IMGBB_API_KEY,
        "image": base64_image
    }

    async with session.post(upload_url, data=payload) as response:
        result = await response.json()
        if response.status == 200 and result.get("success"):
            return result["data"]["url"]
        else:
            raise Exception(result.get("error", {}).get("message", "Ошибка загрузки"))

@dp.message(CommandStart())
async def start_cmd(message: types.Message):
    await message.answer("Здарова! Отправь мне одно или несколько фото, и я пришлю чистые ссылки.")

@dp.message(F.photo)
async def handle_photos(message: types.Message, album: List[types.Message] = None):
    photos_to_process = [msg.photo[-1] for msg in album] if album else [message.photo[-1]]
    status_msg = await message.answer(f"⏳ Загружаю ({len(photos_to_process)} шт.)...")

    uploaded_links = []
    async with aiohttp.ClientSession() as session:
        for photo in photos_to_process:
            try:
                url = await upload_image_to_imgbb(session, photo)
                uploaded_links.append(url)
            except Exception as e:
                uploaded_links.append(f"Ошибка: {e}")

    result_text = "\n".join(uploaded_links)
    await status_msg.edit_text(result_text)

# Заглушка веб-сервера для проверки здоровья сервиса (Health Check) от Render
async def handle_ping(request):
    return web.Response(text="Bot is alive!")

async def main():
    logging.basicConfig(level=logging.INFO)
    
    # Запускаем фиктивный HTTP-сервер на порту, который просит Render
    app = web.Application()
    app.router.add_get("/", handle_ping)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.getenv("PORT", 8080))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()

    print(f"Сервер заглушка запущен на порту {port}. Запускаем бота...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
