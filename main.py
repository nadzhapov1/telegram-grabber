import os
import asyncio
import logging
import re
import pickle
from dotenv import load_dotenv

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

# Настройки замены (можешь поменять на свои)
NEW_LINK = "https://t.me/your_channel"
NEW_USERNAME = "@your_admin"

# Инициализация
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Используем StringSession для облачного запуска
client = TelegramClient(StringSession(STRING_SESSION), API_ID, API_HASH, system_version="4.16.30-vxMAX")
bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(bot, storage=storage)

class ChannelAdding(StatesGroup):
    waiting_for_channel_id = State()

# --- Работа с базой данных (файлы) ---
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

# --- Функции очистки текста ---
def clean_text(text):
    if not text: return ""
    # Замена ссылок в формате Markdown [текст](ссылка)
    text = re.sub(r'\[([^\]]+)\]\(http[s]?://[^\)]+\)', f'[\\1]({NEW_LINK})', text)
    # Замена обычных ссылок http/https
    text = re.sub(r'http[s]?://t\.me/[^\s]+', NEW_LINK, text)
    # Замена упоминаний @username
    text = re.sub(r'@\w+', NEW_USERNAME, text)
    return text

# --- Логика Граббера (Telethon) ---
@client.on(events.NewMessage)
async def message_handler(event):
    chat_id = event.chat_id
    
    # Проверяем, есть ли этот канал в нашем списке прослушки
    if chat_id in channels:
        dest_id = channel_mapping.get(chat_id)
        if not dest_id: return

        text = clean_text(event.message.text)
        
        try:
            if event.message.media:
                await client.send_file(dest_id, event.message.media, caption=text)
            else:
                await client.send_message(dest_id, text)
            logger.info(f"Сообщение из {chat_id} переслано в {dest_id}")
        except Exception as e:
            logger.error(f"Ошибка пересылки: {e}")

# --- Логика Управления (Aiogram) ---
@dp.message_handler(commands=['start'])
async def cmd_start(message: types.Message):
    if message.from_user.id != MY_ID: return
    kb = InlineKeyboardMarkup().add(InlineKeyboardButton("Добавить канал", callback_data="add"))
    await message.answer("Бот-граббер работает на Render.\nИспользуйте кнопку для настройки:", reply_markup=kb)

@dp.callback_query_handler(text="add")
async def add_callback(call: types.CallbackQuery):
    await call.message.answer("Пришлите ID канала, который нужно слушать:")
    await ChannelAdding.waiting_for_channel_id.set()

@dp.message_handler(state=ChannelAdding.waiting_for_channel_id)
async def process_id(message: types.Message, state: FSMContext):
    try:
        source_id = int(message.text)
        # Здесь можно добавить логику привязки к целевому каналу
        channels[source_id] = True
        save_data()
        await message.answer(f"Канал {source_id} добавлен в список прослушки!")
    except:
        await message.answer("Ошибка! Введите числовой ID.")
    await state.finish()

# --- Главный цикл ---
async def main():
    logger.info("Запуск сессии Telethon...")
    await client.start()
    
    logger.info("Запуск бота Aiogram...")
    try:
        # Запускаем и Telethon и Aiogram вместе
        await dp.start_polling()
    finally:
        await client.disconnect()

if __name__ == '__main__':
    asyncio.run(main())
