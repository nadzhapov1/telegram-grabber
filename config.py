import os
from dotenv import load_dotenv

# Загружаем переменные из файла .env (будет работать только при локальном запуске)
load_dotenv()

# Секретные данные (берем из переменных окружения)
# На Render вы добавите их в Dashboard -> Environment
api_id = os.getenv('API_ID')
api_hash = os.getenv('API_HASH')
bot_token = os.getenv('BOT_TOKEN')
my_id = os.getenv('MY_ID')

# ID технического канала (тоже лучше скрыть, так как это персональные данные)
technical_channel_id = os.getenv('TECHNICAL_CHANNEL_ID')

# Публичные настройки (можно оставить как есть, если они не секретны)
new_link = "http://t.me/"
new_username = "@"

# Настройки прокси и OpenAI
proxy_url = 'http://ip:port'  #заполнять только если планируете рерайтить текст в режиме модерации с помощью Chat GPT
openai_api_key = "sk-..."  #заполнять только если планируете рерайтить текст в режиме модерации с помощью Chat GPT

# Приведение типов (если библиотека требует int для ID)
if api_id:
    api_id = int(api_id)
if my_id:
    my_id = int(my_id)
if technical_channel_id:
    technical_channel_id = int(technical_channel_id)
