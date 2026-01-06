"""
Вспомогательные утилиты для бота новостей СТАНКИН.

Модуль содержит:
- Настройку логирования
- Загрузку конфигурации
- Получение новостей через API
- Отправку новостей в группы
"""

import json
import logging
import os
from datetime import datetime
from pathlib import Path

import aiohttp
from aiogram import Bot
from aiogram.types import FSInputFile, InlineKeyboardButton, InlineKeyboardMarkup

import database as db


def load_config(config_path: str = 'config.json') -> dict:
    """
    Загружает конфигурационные данные из файла config.json.

    Args:
        config_path: Путь к конфигурационному файлу.

    Returns:
        dict: Словарь с конфигурационными данными.
    
    Raises:
        FileNotFoundError: Если файл конфигурации не найден.
        json.JSONDecodeError: Если файл содержит невалидный JSON.
    """
    with open(config_path, 'r', encoding='utf-8') as config_file:
        return json.load(config_file)


config = load_config()


def setup_logger(logs_dir: str = None) -> logging.Logger:
    """
    Настраивает логирование для вывода в файл и консоль.

    Args:
        logs_dir: Директория для логов. Если None, берётся из конфига.

    Returns:
        logging.Logger: Объект логгера для записи логов.
    """
    logs_directory = logs_dir or config.get('LOGS_DIR', 'logs')
    Path(logs_directory).mkdir(parents=True, exist_ok=True)
    
    current_time = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
    log_file_name = f"{logs_directory}/{current_time}.log"

    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    
    # Очищаем существующие обработчики чтобы избежать дублирования
    logger.handlers.clear()

    file_handler = logging.FileHandler(log_file_name, encoding='utf-8')
    console_handler = logging.StreamHandler()

    formatter = logging.Formatter(
        '%(asctime)s - %(levelname)s - %(name)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    file_handler.setFormatter(formatter)
    console_handler.setFormatter(formatter)

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    
    return logger


logger = setup_logger()


async def fetch_news() -> list[dict]:
    """
    Асинхронно получает список новостей с указанного URL.
    
    Не выполняет никакой фильтрации - возвращает все полученные новости.
    Фильтрация по отправленным новостям выполняется при отправке.

    Returns:
        list[dict]: Список новостей из API.
    """
    try:
        async with aiohttp.ClientSession() as session:
            request_params = config['REQUEST']

            async with session.post(
                request_params['URL'], 
                headers=request_params['HEADERS'], 
                json=request_params['DATA'],
                timeout=aiohttp.ClientTimeout(total=30)
            ) as response:
                response.raise_for_status()
                data = await response.json()
                news = data.get('data', {}).get('news', [])
                logger.debug(f"Получено {len(news)} новостей из API")
                return news
                
    except aiohttp.ClientError as e:
        logger.error(f"Ошибка при получении новостей: {e}")
    except asyncio.TimeoutError:
        logger.error("Таймаут при получении новостей")
    except Exception as e:
        logger.error(f"Неожиданная ошибка при получении новостей: {e}")
    
    return []


def format_news_message(news: dict) -> tuple[str, str]:
    """
    Форматирует новость для отправки в Telegram.
    
    Args:
        news: Словарь с данными новости.
    
    Returns:
        Кортеж (текст_сообщения, url_новости).
    """
    news_title = news['title']
    news_url = f'https://old.stankin.ru/news/item_{news["id"]}'
    
    # Формат даты в API: YYYY-MM-DD 00:00:00+03
    news_date = news['date'].split()[0]
    news_date = '.'.join(news_date.split('-')[::-1])  # YYYY-MM-DD → DD.MM.YYYY
    
    message = (
        f'<a href="{news_url}"><b>{news_title}</b></a>\n\n'
        f'🗓 {news_date}'
    )
    
    return message, news_url


async def send_news_to_groups(bot: Bot, news_list: list[dict], db_path: str = None) -> int:
    """
    Асинхронно отправляет список новостей в Telegram группы.
    
    Проверяет каждую новость на дубликаты через БД и отмечает отправленные.

    Args:
        bot: Объект Telegram-бота для отправки сообщений.
        news_list: Список новостей для отправки.
        db_path: Путь к файлу базы данных.
    
    Returns:
        Количество успешно отправленных новостей.
    """
    groups = await db.get_all_groups(db_path)
    
    if not groups:
        logger.warning("Нет групп для отправки новостей")
        return 0
    
    sent_count = 0
    image_path = Path(config['NEWS_IMAGE_PATH'])
    
    if not image_path.exists():
        logger.error(f"Изображение не найдено: {image_path}")
        return 0
    
    # Сортируем новости по ID (от старых к новым)
    sorted_news = sorted(news_list, key=lambda x: x['id'])
    
    for news in sorted_news:
        news_id = news['id']
        
        # Проверяем, отправлялась ли эта новость ранее
        if await db.is_news_sent(news_id, db_path):
            logger.debug(f"Новость {news_id} уже была отправлена, пропускаем")
            continue
        
        message, news_url = format_news_message(news)
        read_kb = InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text='Прочитать', url=news_url)]]
        )
        
        # Отправляем во все группы
        success_in_any_group = False
        
        for group in groups:
            chat_id = group['chat_id']
            topic_id = group.get('topic_id')
            
            try:
                # Создаём FSInputFile для каждой отправки
                photo = FSInputFile(image_path)
                
                if topic_id:
                    await bot.send_photo(
                        chat_id=chat_id,
                        message_thread_id=topic_id,
                        photo=photo,
                        caption=message,
                        parse_mode='HTML',
                        reply_markup=read_kb
                    )
                else:
                    await bot.send_photo(
                        chat_id=chat_id,
                        photo=photo,
                        caption=message,
                        parse_mode='HTML',
                        reply_markup=read_kb
                    )
                
                logger.info(f"Отправлена новость '{news['title'][:50]}...' в группу {chat_id}")
                success_in_any_group = True
                
            except Exception as e:
                logger.error(f"Ошибка отправки в группу {chat_id}: {e}")
        
        # Отмечаем новость как отправленную только если успешно отправили хотя бы в одну группу
        if success_in_any_group:
            await db.mark_news_sent(news_id, db_path)
            sent_count += 1
    
    if sent_count > 0:
        logger.info(f"Отправлено {sent_count} новых новостей")
    
    return sent_count


# Импорт asyncio для использования в fetch_news
import asyncio
