import os
import asyncio
import logging
import re
import pickle
from dotenv import load_dotenv

# Telethon
from telethon import TelegramClient, events
from telethon.sessions import StringSession
from telethon.tl.types import MessageMediaWebPage, MessageMediaPhoto, MessageMediaDocument

# Aiogram
from aiogram import Bot, Dispatcher, types
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.contrib.middlewares.logging import LoggingMiddleware
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

import httpx

# Загрузка переменных окружения
load_dotenv()

# --- Конфигурация ---
API_ID = int(os.getenv('API_ID', 0))
API_HASH = os.getenv('API_HASH', '')
BOT_TOKEN = os.getenv('BOT_TOKEN', '')
MY_ID = int(os.getenv('MY_ID', 0))
TECHNICAL_CHANNEL_ID = int(os.getenv('TECHNICAL_CHANNEL_ID', 0))
STRING_SESSION = os.getenv('TELEGRAM_SESSION', '') # Сюда вставляется строка

NEW_LINK = "http://t.me/your_link"
NEW_USERNAME = "@your_username"

# --- Инициализация ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Используем StringSession для авторизации без файлов
client = TelegramClient(StringSession(STRING_SESSION), API_ID, API_HASH, system_version="4.16.30-vxMAX")
bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(bot, storage=storage)
dp.middleware.setup(LoggingMiddleware())

class ChannelAdding(StatesGroup):
    waiting_for_channel_id = State()

moderation_active = False
message_storage = {}

# --- Работа с данными ---
def load_pickle(filename):
    try:
        if os.path.exists(filename):
            with open(filename, 'rb') as f:
                return pickle.load(f)
    except Exception as e:
        logger.error(f"Ошибка загрузки {filename}: {e}")
    return {}

channels = load_pickle('channels.pickle')
destination_channels = load_pickle('destination_channels.pickle')
channel_mapping = load_pickle('channel_mapping.pickle')

def save_channels():
    with open('channels.pickle', 'wb') as f: pickle.dump(channels, f)
    with open('destination_channels.pickle', 'wb') as f: pickle.dump(destination_channels, f)
    with open('channel_mapping.pickle', 'wb') as f: pickle.dump(channel_mapping, f)

def replace_link(text, new_link):
    if not text: return text
    markdown_url_pattern = re.compile(r'\[([^\]]+)\]\(http[s]?://[^\)]+\)')
    return markdown_url_pattern.sub(r'[\1](' + new_link + ')', text)

def replace_at_word(text, new_word):
    if not text: return text
    return re.sub(r'@(\w+)', new_word, text)

# --- Логика пересылки Telethon ---

@client.on(events.NewMessage(chats=list(channels.keys())))
async def my_event_handler(event):
    if event.message.grouped_id: return
    
    original_text = event.message.text or ""
    updated_text = replace_link(replace_at_word(original_text, NEW_USERNAME), NEW_LINK)

    source_channel_id = event.chat_id
    dest_channel_id = channel_mapping.get(source_channel_id)

    if not dest_channel_id: return

    if moderation_active:
        msg = await bot.send_message(TECHNICAL_CHANNEL_ID, f"Модерация:\n{updated_text}")
        message_storage[msg.message_id] = {'text': updated_text, 'dest': dest_channel_id, 'event': event}
    else:
        # Прямая пересылка
        if event.message.media:
            await client.send_file(dest_channel_id, event.message.media, caption=updated_text)
        else:
            await client.send_message(dest_channel_id, updated_text)

# --- Интерфейс Aiogram ---

@dp.message_handler(commands=['start'])
async def send_welcome(message: types.Message):
    if message.from_user.id != MY_ID: return
    keyboard = InlineKeyboardMarkup()
    keyboard.add(InlineKeyboardButton("Добавить канал", callback_data='add_channel'))
    keyboard.add(InlineKeyboardButton("Включить модерацию" if not moderation_active else "Выключить модерацию", callback_data='toggle_mod'))
    await message.reply("Управление граббером:", reply_markup=keyboard)

@dp.callback_query_handler(lambda c: c.data == 'add_channel')
async def process_add_channel(callback_query: types.CallbackQuery):
    await bot.answer_callback_query(callback_query.id)
    await bot.send_message(callback_query.from_user.id, "Отправьте ID канала (число):")
    await ChannelAdding.waiting_for_channel_id.set()

@dp.message_handler(state=ChannelAdding.waiting_for_channel_id)
async def add_channel_id(message: types.Message, state: FSMContext):
    try:
        cid = int(message.text)
        channels[cid] = True
        save_channels()
        await message.reply(f"Канал {cid} добавлен. Перезапустите бота для обновления списка прослушки.")
    except:
        await message.reply("Нужно ввести число.")
    await state.finish()

@dp.callback_query_handler(lambda c: c.data == 'toggle_mod')
async def toggle_moderation(callback_query: types.CallbackQuery):
    global moderation_active
    moderation_active = not moderation_active
    await bot.answer_callback_query(callback_query.id, f"Модерация: {'ВКЛ' if moderation_active else 'ВЫКЛ'}")
    await send_welcome(callback_query.message)

# --- Основной цикл запуска ---

async def main():
    # 1. Авторизация в Telethon
    print("Запуск Telethon...")
    await client.start()
    
    # Если вы запускаете код первый раз локально, он попросит код в консоли
    # После входа он выведет строку, которую нужно вставить в Render
    if not STRING_SESSION:
        print("\n" + "="*60)
        print("ВАША СТРОКА СЕССИИ (СКОПИРУЙТЕ ЕЁ В TELEGRAM_SESSION):")
        print(client.session.save())
        print("="*60 + "\n")

    print("Бот залогинился в аккаунт!")

    # 2. Запуск Aiogram
    print("Запуск Aiogram...")
    try:
        # Используем диспетчер для получения обновлений
        await dp.start_polling()
    finally:
        await client.disconnect()

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Бот выключен")
