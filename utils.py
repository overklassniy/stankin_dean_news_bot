import json
import logging
import os
from datetime import datetime
from typing import Union

import aiohttp
from aiogram import Bot
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


# Подгрузка конфигураций из config.json
def load_config() -> dict:
    """
    Загружает конфигурационные данные из файла config.json.

    Returns:
        dict: Словарь с конфигурационными данными.
    """
    with open('config.json', 'r') as config_file:
        return json.load(config_file)


config = load_config()


# Настройка логирования
def setup_logger() -> logging.Logger:
    """
    Настраивает логирование для вывода в файл и консоль.

    Returns:
        logging.Logger: Объект логгера для записи логов.
    """
    os.makedirs(config['LOGS_DIR'], exist_ok=True)
    current_time = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
    log_file_name = f"{config['LOGS_DIR']}/{current_time}.log"

    logger = logging.getLogger()
    logger.setLevel(logging.INFO)

    file_handler = logging.FileHandler(log_file_name)
    console_handler = logging.StreamHandler()

    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    file_handler.setFormatter(formatter)
    console_handler.setFormatter(formatter)

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    return logger


logger = setup_logger()


# Функции для работы с файлами JSON
def load_json_file(file_path: str, default_value: Union[dict, list]) -> Union[dict, list]:
    """
    Загружает данные из JSON файла. Если файл не существует, возвращает значение по умолчанию.

    Args:
        file_path (str): Путь к JSON файлу.
        default_value (dict | list): Значение по умолчанию, если файл не найден.

    Returns:
        dict | list: Данные, загруженные из JSON файла, или значение по умолчанию.
    """
    if os.path.exists(file_path):
        with open(file_path, 'r') as f:
            return json.load(f)
    return default_value


def save_json_file(file_path: str, data: Union[dict, list]) -> None:
    """
    Сохраняет данные в JSON файл.

    Args:
        file_path (str): Путь к JSON файлу.
        data (dict | list): Данные для сохранения.
    """
    # Получаем директорию из пути к файлу
    directory = os.path.dirname(file_path)

    # Проверяем, существует ли директория, и создаем её, если нет
    if not os.path.exists(directory):
        os.makedirs(directory)

    # Сохраняем данные в JSON файл
    with open(file_path, 'w') as f:
        json.dump(data, f)


# Глобальные переменные
groups = load_json_file(config['GROUPS_FILE'], default_value=[])
last_news_id = load_json_file(config['LAST_NEWS_ID_FILE'], {'last_news_id': 0})['last_news_id']


# Асинхронная функция для получения новостей
async def fetch_news() -> list:
    """
    Асинхронно получает список новостей с указанного URL, сравнивая их с последним сохранённым ID новости.

    Returns:
        list: Список новостей, которые имеют ID больше, чем последний сохранённый ID.
    """
    global last_news_id
    try:
        async with aiohttp.ClientSession() as session:
            request_params = config['REQUEST']

            async with session.post(request_params['URL'], headers=request_params['HEADERS'], json=request_params['DATA']) as response:
                response.raise_for_status()
                news = (await response.json())['data']['news']
                new_news = [item for item in news if last_news_id is None or item['id'] > last_news_id]
                if new_news:
                    last_news_id = max(item['id'] for item in new_news)
                    save_json_file(config['LAST_NEWS_ID_FILE'], {'last_news_id': last_news_id})
                    logger.info(f"Fetched {len(new_news)} new news items.")
                    return new_news
                logger.info("No new news found.")
    except aiohttp.ClientError as e:
        logger.error(f"Error fetching news: {e}")
    return []


# Асинхронная функция для отправки новостей в группы
async def send_news_to_groups(bot: Bot, news_list: list) -> None:
    """
    Асинхронно отправляет список новостей в Telegram группы.

    Args:
        bot (Bot): Объект Telegram-бота для отправки сообщений.
        news_list (list): Список новостей для отправки.
    """
    for news in news_list:
        news_title = news['title']
        news_url = f'https://old.stankin.ru/news/item_{news["id"]}'
        # в json ответе дата представлена в формате YYYY-MM-DD 00:00:00+03, так как в деканате часы, минуты и секунды не пишут, то и нам они не нужны
        news_date = news['date'].split()[0]
        news_date = '.'.join(news_date.split('-')[::-1])  # приводим формат даты из YYYY-MM-DD в DD-MM-YYYY
        message = (
            f'<a href="{news_url}"><b>{news_title}</b></a>\n\n'
            f'🗓 {news_date}'
        )
        # message = f"** [{news_title}]({news_url}) **\n\n🗓 > {news_date}"
        for chat_id in groups:
            try:
                stankin_image_url = config['NEWS_IMAGE_URL']
                read_kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='Прочитать', url=news_url)]])
                if isinstance(chat_id, list):
                    await bot.send_photo(chat_id=chat_id[0], message_thread_id=chat_id[1], photo=stankin_image_url, caption=message, parse_mode='HTML', reply_markup=read_kb)
                else:
                    await bot.send_photo(chat_id, stankin_image_url, caption=message, parse_mode='HTML', reply_markup=read_kb)
                logger.info(f"Sent news to group {chat_id}: {news_title}")
            except Exception as e:
                logger.error(f"Error sending message to group {chat_id}: {e}")
