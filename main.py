from aiogram import Bot, Dispatcher, types
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.contrib.middlewares.logging import LoggingMiddleware
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
import asyncio, logging, os, pickle, re, sys, httpx
from telethon import TelegramClient, events
from telethon.sessions import StringSession
from telethon.tl.types import MessageMediaWebPage, MessageMediaPhoto, MessageMediaDocument

# --- КОНФИГУРАЦИЯ ---
API_ID = int(os.getenv('API_ID', 0))
API_HASH = os.getenv('API_HASH', '')
BOT_TOKEN = os.getenv('BOT_TOKEN', '')
MY_ID = int(os.getenv('MY_ID', 0))
TECHNICAL_CHANNEL_ID = int(os.getenv('TECHNICAL_CHANNEL_ID', 0))
STRING_SESSION = os.getenv('TELEGRAM_SESSION', '')
NEW_LINK = os.getenv('NEW_LINK', '')
NEW_USERNAME = os.getenv('NEW_USERNAME', '')
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY', '')
PROXY_URL = os.getenv('PROXY_URL', '')

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- ИНИЦИАЛИЗАЦИЯ ---
client = TelegramClient(StringSession(STRING_SESSION), API_ID, API_HASH)
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(bot, storage=MemoryStorage())
dp.middleware.setup(LoggingMiddleware())

# Глобальные переменные
moderation_active = False
message_storage = {}
channels, destination_channels, channel_mapping = {}, {}, {}

# Загрузка данных
def load_data():
    global channels, destination_channels, channel_mapping
    for name, var in [('channels.pickle', channels), ('destination_channels.pickle', destination_channels), ('channel_mapping.pickle', channel_mapping)]:
        if os.path.exists(name):
            try:
                with open(name, 'rb') as f:
                    data = pickle.load(f)
                    if 'channels' in name: channels.update(data)
                    elif 'destination' in name: destination_channels.update(data)
                    elif 'mapping' in name: channel_mapping.update(data)
            except: pass

def save_data():
    with open('channels.pickle', 'wb') as f: pickle.dump(channels, f)
    with open('destination_channels.pickle', 'wb') as f: pickle.dump(destination_channels, f)
    with open('channel_mapping.pickle', 'wb') as f: pickle.dump(channel_mapping, f)

# --- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ---
def replace_link(text, new_link):
    return re.sub(r'\[([^\]]+)\]\(http[s]?://[^\)]+\)', r'[\1](' + new_link + ')', text) if text else text

def replace_at_word(text, new_word):
    return re.sub(r'@(\w+)', new_word, text) if text else text

async def rewrite_text_with_chatgpt(text, openai_api_key):
    try:
        async with httpx.AsyncClient(proxies={"http://": PROXY_URL, "https://": PROXY_URL}, timeout=15.0) as http:
            resp = await http.post("https://api.openai.com/v1/chat/completions",
                json={"model": "gpt-3.5-turbo", "messages": [{"role": "user", "content": f"Переформулируй: {text}"}]},
                headers={"Authorization": f"Bearer {openai_api_key}"})
            return resp.json()['choices'][0]['message']['content']
    except: return None

# --- ХЭНДЛЕРЫ КНОПОК И МОДЕРАЦИИ ---
@dp.callback_query_handler(lambda c: c.data.startswith('send_'))
async def process_send(callback_query: types.CallbackQuery):
    msg_id = int(callback_query.data.split('_')[1])
    if msg_id in message_storage:
        match = re.search(r'ID (-?\d+)', callback_query.message.text)
        dest_id = int(match.group(1)) if match else None
        if dest_id:
            msg = message_storage[msg_id]
            if isinstance(msg, list): await client.send_file(dest_id, [m.media for m in msg], caption=msg[0].text)
            else: await client.send_message(dest_id, msg.text, file=msg.media)
            await client.delete_messages(TECHNICAL_CHANNEL_ID, [m.id for m in msg] if isinstance(msg, list) else msg_id)
        del message_storage[msg_id]
        await bot.delete_message(callback_query.message.chat.id, callback_query.message.message_id)
        await bot.answer_callback_query(callback_query.id, "Отправлено")

@dp.callback_query_handler(lambda c: c.data.startswith('rewrite_'))
async def process_rewrite(callback_query: types.CallbackQuery):
    msg_id = int(callback_query.data.split('_')[1])
    if msg_id in message_storage:
        text = await rewrite_text_with_chatgpt(message_storage[msg_id].text, OPENAI_API_KEY)
        if text: await client.edit_message(TECHNICAL_CHANNEL_ID, msg_id, text)
        await bot.answer_callback_query(callback_query.id, "Готово")

# --- БЭКАП БД ---
@dp.message_handler(content_types=['document'])
async def handle_backup_upload(message: types.Message):
    if message.from_user.id == MY_ID and message.document.file_name.endswith('.pickle'):
        await message.document.download(destination_file=message.document.file_name)
        load_data()
        await message.reply("Данные восстановлены.")

@dp.callback_query_handler(lambda c: c.data == 'backup_db')
async def process_backup(callback_query: types.CallbackQuery):
    for f in ['channels.pickle', 'destination_channels.pickle', 'channel_mapping.pickle']:
        if os.path.exists(f): await bot.send_document(callback_query.from_user.id, open(f, 'rb'))
    await bot.answer_callback_query(callback_query.id)

# --- СОБЫТИЯ TELETHON ---
@client.on(events.NewMessage(chats=lambda c: c in channels))
async def handler(event):
    if event.message.grouped_id: return
    text = replace_link(replace_at_word(event.message.text, NEW_USERNAME), NEW_LINK)
    if moderation_active:
        sent = await client.send_message(TECHNICAL_CHANNEL_ID, text, file=event.message.media)
        message_storage[sent.id] = sent
        # ... (здесь можно добавить создание кнопок InlineKeyboardMarkup)
    else:
        dest = channel_mapping.get(event.chat_id)
        if dest: await client.send_message(dest, text, file=event.message.media)

# --- МЕНЮ И ЗАПУСК ---
def create_menu_keyboard():
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("💾 Бэкап БД", callback_data='backup_db'))
    kb.add(InlineKeyboardButton("Перезагрузка", callback_data='restart_bot'))
    return kb

@dp.callback_query_handler(lambda c: c.data == 'restart_bot')
async def restart(c):
    await bot.answer_callback_query(c.id, "Перезагружаю...")
    os.execl(sys.executable, sys.executable, *sys.argv)

@dp.message_handler(commands=['start'])
async def start(m):
    await m.reply("Бот запущен", reply_markup=create_menu_keyboard())

if __name__ == "__main__":
    async def main():
        # 1. Загружаем данные
        load_data()
        
        # 2. Подключаем Telethon
        await client.start()
        logger.info("Client запущен")
        
        # 3. ПРИНУДИТЕЛЬНО СБРАСЫВАЕМ ВСЕ СТАРЫЕ СЕССИИ TELEGRAM
        # Это самое важное: мы говорим Telegram удалить все старые Webhook-и 
        # и разрешения на получение обновлений, которые могли зависнуть.
        await bot.delete_webhook(drop_pending_updates=True)
        logger.info("Webhook сброшен, начинаю polling...")
        
        try:
            # 4. Запускаем бота
            await dp.start_polling()
        except Exception as e:
            logger.error(f"Ошибка в polling: {e}")
        finally:
            await client.disconnect()

    asyncio.run(main())
