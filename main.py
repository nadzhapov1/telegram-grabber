import os
import asyncio
import logging
import re
import pickle
from dotenv import load_dotenv

# Для работы порта на Render
from aiohttp import web

# Telethon
from telethon import TelegramClient, events
from telethon.sessions import StringSession

# Aiogram
from aiogram import Bot, Dispatcher, types
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# Загрузка конфигов
load_dotenv()

API_ID = int(os.getenv('API_ID', 0))
API_HASH = os.getenv('API_HASH', '')
BOT_TOKEN = os.getenv('BOT_TOKEN', '')
MY_ID = int(os.getenv('MY_ID', 0))
TECHNICAL_CHANNEL_ID = int(os.getenv('TECHNICAL_CHANNEL_ID', 0))
STRING_SESSION = os.getenv('TELEGRAM_SESSION', '')

# Настройки замены
NEW_LINK = "https://t.me/your_channel"  # Замени на свою ссылку
NEW_USERNAME = "@your_admin"           # Замени на свой юзернейм

# Инициализация логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- ВЕБ-СЕРВЕР ДЛЯ RENDER (ОБМАНКА ПОРТА) ---
async def handle(request):
    return web.Response(text="Bot is alive!")

async def start_web_server():
    app = web.Application()
    app.router.add_get('/', handle)
    runner = web.AppRunner(app)
    await runner.setup()
    # Render передает порт в переменную окружения PORT
    port = int(os.getenv("PORT", 10000))
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    logger.info(f"Веб-сервер запущен на порту {port}")

# --- ИНИЦИАЛИЗАЦИЯ ТЕЛЕГРАМ ---
client = TelegramClient(StringSession(STRING_SESSION), API_ID, API_HASH, system_version="4.16.30-vxMAX")
bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(bot, storage=storage)

class ChannelAdding(StatesGroup):
    waiting_for_channel_id = State()

# --- РАБОТА С ДАННЫМИ ---
def load_data(filename):
    if os.path.exists(filename):
        try:
            with open(filename, 'rb') as f: return pickle.load(f)
        except: return {}
    return {}

channels = load_data('channels.pickle')
channel_mapping = load_data('channel_mapping.pickle')

def save_data():
    with open('channels.pickle', 'wb') as f: pickle.dump(channels, f)
    with open('channel_mapping.pickle', 'wb') as f: pickle.dump(channel_mapping, f)

def clean_text(text):
    if not text: return ""
    text = re.sub(r'http[s]?://t\.me/[^\s]+', NEW_LINK, text)
    text = re.sub(r'@\w+', NEW_USERNAME, text)
    return text

# --- ОБРАБОТЧИК СООБЩЕНИЙ (ГРАББЕР) ---
@client.on(events.NewMessage)
async def message_handler(event):
    chat_id = event.chat_id
    if chat_id in channels:
        dest_id = channel_mapping.get(chat_id)
        if not dest_id: return
        text = clean_text(event.message.text)
        try:
            if event.message.media:
                await client.send_file(dest_id, event.message.media, caption=text)
            else:
                await client.send_message(dest_id, text)
        except Exception as e:
            logger.error(f"Ошибка пересылки: {e}")

# --- АДМИН-КОМАНДЫ (AIOGRAM) ---
@dp.message_handler(commands=['start'])
async def cmd_start(message: types.Message):
    if message.from_user.id != MY_ID: return
    kb = InlineKeyboardMarkup().add(InlineKeyboardButton("Добавить канал", callback_data="add"))
    await message.answer("Бот-граббер активен. Нажмите кнопку для настройки:", reply_markup=kb)

@dp.callback_query_handler(text="add")
async def add_callback(call: types.CallbackQuery):
    await call.message.answer("Введите ID канала для прослушивания:")
    await ChannelAdding.waiting_for_channel_id.set()

@dp.message_handler(state=ChannelAdding.waiting_for_channel_id)
async def process_id(message: types.Message, state: FSMContext):
    try:
        source_id = int(message.text)
        channels[source_id] = True
        save_data()
        await message.answer(f"Канал {source_id} добавлен!")
    except:
        await message.answer("ID должен быть числом.")
    await state.finish()

# --- ЗАПУСК ВСЕГО ВМЕСТЕ ---
async def main():
    # 1. Запускаем веб-сервер, чтобы Render не убил процесс
    await start_web_server()
    
    # 2. Запускаем клиент Telethon
    logger.info("Подключение к сессии Telethon...")
    await client.start()
    
    # 3. Запускаем бота Aiogram
    logger.info("Запуск Aiogram Polling...")
    try:
        await dp.start_polling()
    finally:
        await client.disconnect()

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Бот остановлен пользователем")
