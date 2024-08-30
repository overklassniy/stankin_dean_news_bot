import json
import logging
import os
import requests
from datetime import datetime
from typing import Union

import telebot


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
    with open(file_path, 'w') as f:
        json.dump(data, f)


# Глобальные переменные
groups = set(load_json_file(config['GROUPS_FILE'], default_value=[]))
last_news_id = load_json_file(config['LAST_NEWS_ID_FILE'], {'last_news_id': config['DEFAULT_LAST_NEWS_ID']})['last_news_id']


# Функция для получения новостей
def fetch_news() -> list:
    """
    Получает список новостей с указанного URL, сравнивая их с последним сохранённым ID новости.

    Returns:
        list: Список новостей, которые имеют ID больше, чем последний сохранённый ID.
    """
    global last_news_id
    try:
        with requests.Session() as session:
            response = session.post(config['URL'], headers=config['HEADERS'], json=config['DATA'])
            response.raise_for_status()
            news = response.json()['data']['news']
            new_news = [item for item in news if last_news_id is None or item['id'] > last_news_id]
            if new_news:
                last_news_id = max(item['id'] for item in new_news)
                save_json_file(config['LAST_NEWS_ID_FILE'], {'last_news_id': last_news_id})
                logger.info(f"Fetched {len(new_news)} new news items.")
                return new_news
            logger.info("No new news found.")
    except requests.RequestException as e:
        logger.error(f"Error fetching news: {e}")
    return []


# Функция для отправки новостей в группы
def send_news_to_groups(bot: telebot.TeleBot, news_list: list) -> None:
    """
    Отправляет список новостей в Telegram группы.

    Args:
        bot (telebot.TeleBot): Объект Telegram-бота для отправки сообщений.
        news_list (list): Список новостей для отправки.
    """
    for news in news_list:
        news_url = f'https://stankin.ru/news/item_{news["id"]}'
        # в json ответе дата представлена в формате YYYY-MM-DD 00:00:00+03, так как в деканате часы, минуты и секунды не пишут, то и нам они не нужны
        news_date = news['date'].split()[0]
        news_date = '.'.join(news_date.split('-')[::-1])  # приводим формат даты из YYYY-MM-DD в DD-MM-YYYY
        message = f"[{news['title']}]({news_url})\n\n🗓 {news_date}"
        for chat_id in groups:
            try:
                with open(config['NEWS_IMAGE_PATH'], 'rb') as stankin_photo:
                    read_kb = telebot.types.InlineKeyboardMarkup()
                    read_kb.add(telebot.types.InlineKeyboardButton('Прочитать', url=news_url))
                    bot.send_photo(chat_id, stankin_photo, caption=message, parse_mode='Markdown', reply_markup=read_kb)
                    logger.info(f"Sent news to group {chat_id}: {news['title']}")
            except Exception as e:
                logger.error(f"Error sending message to group {chat_id}: {e}")
