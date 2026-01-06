"""
Telegram бот для рассылки новостей деканата МГТУ СТАНКИН.

Основные функции:
- Автоматическая рассылка новостей в группы
- Поддержка топиков в супергруппах
- Команды для управления ботом
"""

import asyncio
import os
from pathlib import Path

from aiogram import Bot, Dispatcher, types, F
from aiogram.enums import ChatType
from aiogram.filters import Command, ChatMemberUpdatedFilter, JOIN_TRANSITION, LEAVE_TRANSITION
from aiogram.types import BotCommand, ChatMemberUpdated
from dotenv import load_dotenv

import database as db
from utils import fetch_news, send_news_to_groups, logger, config

# Загрузка переменных окружения
load_dotenv()
TOKEN = os.getenv('BOT_TOKEN')

if not TOKEN:
    raise ValueError("BOT_TOKEN не найден в переменных окружения. Создайте файл .env с BOT_TOKEN=your_token")

# Путь к БД (можно задать через переменную окружения)
DB_PATH = os.getenv('DB_PATH', config.get('DB_PATH', 'data/bot.db'))

dp = Dispatcher()


# Команды бота
@dp.message(Command(BotCommand(command='start', description='Начать работу с ботом')))
async def handle_start_command(message: types.Message) -> None:
    """Обрабатывает команду /start."""
    if message.chat.type == ChatType.PRIVATE:
        await message.answer(
            "👋 Привет! Я бот для рассылки новостей деканата МГТУ СТАНКИН.\n\n"
            "📢 Добавьте меня в группу, чтобы получать актуальные новости.\n\n"
            "📌 Доступные команды:\n"
            "/code — ссылка на исходный код\n"
            "/settopic — настроить топик для новостей (только в супергруппах)"
        )
        logger.info(f"Отправлено приветствие пользователю {message.from_user.id}")


@dp.message(Command(BotCommand(command='code', description='Получить ссылку на GitHub репозиторий бота')))
async def handle_code_command(message: types.Message) -> None:
    """Обрабатывает команду /code и отправляет ссылку на GitHub репозиторий."""
    github_link = "https://github.com/overklassniy/stankin_dean_news_bot"
    try:
        if message.chat.type == ChatType.PRIVATE:
            await message.answer(f"📂 Исходный код бота доступен на GitHub:\n{github_link}")
            logger.info(f"Отправлена ссылка на GitHub пользователю {message.from_user.id}")
    except Exception as e:
        logger.error(f"Ошибка отправки ссылки на GitHub: {e}")


@dp.message(Command(BotCommand(command='settopic', description='Установить топик для новостей (в супергруппах)')))
async def handle_settopic_command(message: types.Message, bot: Bot) -> None:
    """
    Обрабатывает команду /settopic для установки топика в супергруппе.
    
    Использование:
    - /settopic - установить текущий топик (отправить команду в нужном топике)
    - /settopic 0 или /settopic off - отключить топик
    """
    chat = message.chat
    
    # Проверка типа чата
    if chat.type not in (ChatType.SUPERGROUP,):
        await message.answer(
            "⚠️ Эта команда работает только в супергруппах с включёнными топиками."
        )
        return
    
    # Проверка прав пользователя (только администраторы могут менять настройки)
    try:
        member = await bot.get_chat_member(chat.id, message.from_user.id)
        if member.status not in ('administrator', 'creator'):
            await message.answer("⚠️ Только администраторы могут изменять настройки топика.")
            return
    except Exception as e:
        logger.error(f"Ошибка проверки прав пользователя: {e}")
        await message.answer("❌ Не удалось проверить ваши права.")
        return
    
    # Проверяем, есть ли группа в БД
    group = await db.get_group(chat.id, DB_PATH)
    if not group:
        await message.answer("⚠️ Бот не зарегистрирован в этой группе. Попробуйте удалить и добавить бота заново.")
        return
    
    # Парсим аргументы команды
    args = message.text.split(maxsplit=1)
    
    if len(args) > 1:
        arg = args[1].strip().lower()
        if arg in ('0', 'off', 'выкл', 'отключить'):
            # Отключаем топик
            await db.set_topic(chat.id, None, DB_PATH)
            await message.answer("✅ Топик отключён. Новости будут отправляться в основной чат.")
            logger.info(f"Топик отключён для группы {chat.id}")
            return
        elif arg.isdigit():
            topic_id = int(arg)
            await db.set_topic(chat.id, topic_id, DB_PATH)
            await message.answer(f"✅ Установлен топик с ID: {topic_id}")
            logger.info(f"Установлен топик {topic_id} для группы {chat.id}")
            return
    
    # Используем текущий топик (message_thread_id)
    if message.message_thread_id:
        topic_id = message.message_thread_id
        await db.set_topic(chat.id, topic_id, DB_PATH)
        await message.answer(f"✅ Новости будут отправляться в этот топик (ID: {topic_id})")
        logger.info(f"Установлен топик {topic_id} для группы {chat.id}")
    else:
        await message.answer(
            "ℹ️ Использование команды:\n"
            "• Отправьте /settopic в нужном топике\n"
            "• Или используйте /settopic <id> для указания ID топика\n"
            "• /settopic off — отключить топик"
        )


# Обработчики событий чата
@dp.my_chat_member(ChatMemberUpdatedFilter(member_status_changed=JOIN_TRANSITION))
async def bot_added(event: ChatMemberUpdated, bot: Bot) -> None:
    """Добавляет чат в список рассылки, когда бот добавлен в группу."""
    if event.new_chat_member.user.id != bot.id:
        return
    
    chat = event.chat
    chat_id = chat.id
    is_supergroup = chat.type == ChatType.SUPERGROUP
    
    # Добавляем группу в БД
    added = await db.add_group(chat_id, is_supergroup, DB_PATH)
    
    if added:
        logger.info(f"Бот добавлен в {'супергруппу' if is_supergroup else 'группу'} {chat_id}")
        
        # Отправляем приветственное сообщение
        try:
            welcome_text = "👋 Привет! Я буду присылать сюда новости деканата СТАНКИН."
            if is_supergroup:
                welcome_text += "\n\n💡 Совет: используйте /settopic в нужном топике, чтобы новости приходили туда."
            await bot.send_message(chat_id, welcome_text)
        except Exception as e:
            logger.warning(f"Не удалось отправить приветствие в группу {chat_id}: {e}")


@dp.my_chat_member(ChatMemberUpdatedFilter(member_status_changed=LEAVE_TRANSITION))
async def bot_kicked(event: ChatMemberUpdated, bot: Bot) -> None:
    """Удаляет чат из списка рассылки, когда бот удалён из группы."""
    if event.new_chat_member.user.id != bot.id:
        return
    
    chat_id = event.chat.id
    removed = await db.remove_group(chat_id, DB_PATH)
    
    if removed:
        logger.info(f"Бот удалён из группы {chat_id}")


# Обработчик личных сообщений
@dp.message(F.chat.type == ChatType.PRIVATE)
async def handle_private_message(message: types.Message) -> None:
    """Обрабатывает личные сообщения пользователей (кроме команд)."""
    # Пропускаем команды
    if message.text and message.text.startswith('/'):
        return
    
    response_text = (
        "👋 Привет! Я бот для рассылки новостей деканата СТАНКИН.\n\n"
        "📢 Добавьте меня в любую группу, чтобы получать актуальные новости!\n\n"
        "💻 Исходный код: /code"
    )
    try:
        await message.answer(response_text)
        logger.debug(f"Отправлено сообщение пользователю {message.from_user.id}")
    except Exception as e:
        logger.error(f"Ошибка отправки личного сообщения: {e}")


# Фоновые задачи
async def check_news_periodically(bot: Bot) -> None:
    """
    Периодически проверяет наличие новых новостей и отправляет их в группы.
    
    Запускается как фоновая задача при старте бота.
    """
    sleep_time = config.get('SLEEP_TIME', 360)
    cleanup_interval = 100  # Очищать старые записи каждые N проверок
    check_count = 0
    
    logger.info(f"Запущена проверка новостей (интервал: {sleep_time} сек)")
    
    while True:
        try:
            news_list = await fetch_news()
            
            if news_list:
                await send_news_to_groups(bot, news_list, DB_PATH)
            else:
                logger.debug("Новых новостей не найдено")
            
            # Периодическая очистка старых записей
            check_count += 1
            if check_count >= cleanup_interval:
                await db.cleanup_old_news(keep_count=500, db_path=DB_PATH)
                check_count = 0
                
        except Exception as e:
            logger.error(f"Ошибка в цикле проверки новостей: {e}")
        
        await asyncio.sleep(sleep_time)


async def migrate_data_if_needed() -> None:
    """Мигрирует данные из JSON файлов, если они существуют."""
    groups_file = config.get('GROUPS_FILE', 'data/groups.json')
    last_news_file = config.get('LAST_NEWS_ID_FILE', 'data/last_news_id.json')
    
    if Path(groups_file).exists() or Path(last_news_file).exists():
        logger.info("Обнаружены JSON файлы, запускаем миграцию...")
        await db.migrate_from_json(groups_file, last_news_file, DB_PATH)
        
        # Переименовываем старые файлы
        for file_path in [groups_file, last_news_file]:
            path = Path(file_path)
            if path.exists() and path.suffix == '.json':
                backup_path = path.with_name(path.name + '.bak')
                try:
                    path.rename(backup_path)
                    logger.info(f"Файл {file_path} переименован в {backup_path}")
                except Exception as e:
                    logger.warning(f"Не удалось переименовать {file_path}: {e}")


async def main() -> None:
    """Главная функция запуска бота."""
    # Инициализация БД
    await db.init_db(DB_PATH)
    
    # Миграция данных из JSON (если есть)
    await migrate_data_if_needed()
    
    # Создание бота
    bot = Bot(token=TOKEN)
    
    # Получаем информацию о боте
    bot_info = await bot.get_me()
    logger.info(f"Бот запущен: @{bot_info.username} (ID: {bot_info.id})")
    
    # Запуск фоновой задачи проверки новостей
    asyncio.create_task(check_news_periodically(bot))
    
    # Запуск polling
    try:
        await dp.start_polling(bot, polling_timeout=30)
    finally:
        await bot.session.close()
        logger.info("Бот остановлен")


if __name__ == '__main__':
    asyncio.run(main())
