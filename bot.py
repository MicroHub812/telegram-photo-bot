import asyncio
import logging
import base64
from typing import List, Dict, Any
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart
from aiogram.dispatcher.middlewares.base import BaseMiddleware
import aiohttp

BOT_TOKEN = "токен бота"
IMGBB_API_KEY = "токен с сайта хостинга"

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# Middleware для сборки нескольких фото из одной группы (альбома)
class AlbumMiddleware(BaseMiddleware):
    def __init__(self, latency: float = 0.6):
        self.latency = latency
        self.album_data: Dict[str, List[types.Message]] = {}

    async def __call__(self, handler, event: types.Message, data: Dict[str, Any]):
        if not event.media_group_id:
            return await handler(event, data)

        try:
            self.album_data[event.media_group_id].append(event)
            return  # Пропускаем обработку отдельных сообщений альбома
        except KeyError:
            self.album_data[event.media_group_id] = [event]
            await asyncio.sleep(self.latency)
            data["album"] = self.album_data.pop(event.media_group_id)
            return await handler(event, data)

# Регистрируем Middleware для сообщений
dp.message.middleware(AlbumMiddleware())

# Вспомогательная функция для загрузки 1 фото на ImgBB
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
    await message.answer("Здарова! Отправь мне одно или несколько фото (альбомом), и я пришлю ссылки одним сообщением!")

# Обработчик одиночных фото и альбомов
@dp.message(F.photo)
async def handle_photos(message: types.Message, album: List[types.Message] = None):
    # Если пришел альбом — берем список сообщений, если одно фото — оборачиваем в список
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

    # Собираем и отправляем только чистые ссылки с новой строки
    result_text = "\n".join(uploaded_links)
    await status_msg.edit_text(result_text)

    # Формируем одно итоговое сообщение
    result_text = "✅ **Готово! Ваши ссылки:**\n\n" + "\n".join(uploaded_links)
    await status_msg.edit_text(result_text, parse_mode="Markdown")

async def main():
    logging.basicConfig(level=logging.INFO)
    print("Бот запущен!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())