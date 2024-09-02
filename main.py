import asyncio
import os

from aiogram import Bot, Dispatcher, types, F
from aiogram.enums import ChatType
from aiogram.filters import Command, ChatMemberUpdatedFilter, JOIN_TRANSITION, LEAVE_TRANSITION
from aiogram.types import BotCommand, ChatMemberUpdated
from dotenv import load_dotenv

from utils import fetch_news, send_news_to_groups, save_json_file, logger, groups, config

# Загрузка переменных окружения
load_dotenv()
TOKEN = os.getenv('BOT_TOKEN')

dp = Dispatcher()

# Идентификатор бота
bot_id = None


# Обработчик команды /code
@dp.message(Command(BotCommand(command='code', description='Получить ссылку на GitHub репозиторий бота')))
async def handle_code_command(message: types.Message) -> None:
    """
    Обрабатывает команду /code и отправляет ссылку на GitHub репозиторий.

    Args:
        message (types.Message): Сообщение, содержащее команду /code.
    """
    github_link = "https://github.com/overklassniy/stankin_dean_news_bot"
    try:
        await message.answer(f"Исходный код бота доступен на GitHub: {github_link}")
        logger.info(f"Sent GitHub link to {message.chat.id}")
    except Exception as e:
        logger.error(f"Error sending GitHub link to {message.chat.id}: {e}")


# Обработчик личных сообщений
@dp.message(F.chat.func(lambda chat: chat.type == ChatType.PRIVATE))
async def handle_private_message(message: types.Message) -> None:
    """
    Обрабатывает личные сообщения пользователей.

    Args:
        message (types.Message): Сообщение, полученное ботом.
    """
    response_text = "Привет, пока у меня нет функционала в личных сообщениях. Добавьте меня в любую группу, чтобы получать актуальные новости!"
    try:
        await message.answer(response_text)
        logger.info(f"Sent private message to {message.chat.id}")
    except Exception as e:
        logger.error(f"Error sending private message to {message.chat.id}: {e}")


# Обработчик добавления бота в группу
@dp.my_chat_member(ChatMemberUpdatedFilter(member_status_changed=JOIN_TRANSITION))
async def bot_added(event: ChatMemberUpdated):
    """
    Добавляет чат в список рассылки, если бот был добавлен в группу.

    Args:
        event (types.ChatMemberUpdated): Информация о статусе бота.
    """
    global bot_id

    member_id = event.new_chat_member.user.id
    chat_id = event.chat.id

    if member_id == bot_id:
        if chat_id not in groups:
            groups.append(chat_id)
            save_json_file(config['GROUPS_FILE'], groups)
            logger.info(f"Bot added to group {chat_id}")


@dp.my_chat_member(ChatMemberUpdatedFilter(member_status_changed=LEAVE_TRANSITION))
async def bot_kicked(event: ChatMemberUpdated):
    """
    Удаляет чат из списка рассылки, если бот был удалён из группы.

    Args:
        event (types.ChatMemberUpdated): Информация о статусе бота.
    """
    global bot_id

    member_id = event.new_chat_member.user.id
    chat_id = event.chat.id

    if member_id == bot_id:
        if chat_id in groups:
            groups.remove(chat_id)
            save_json_file(config['GROUPS_FILE'], groups)
            logger.info(f"Bot removed from group {chat_id}")


# Асинхронная функция для периодической проверки новостей
async def check_news(bot: Bot) -> None:
    """
    Периодически проверяет наличие новых новостей и отправляет их в группы.
    """
    while True:
        news_list = await fetch_news()
        if news_list:
            await send_news_to_groups(bot, news_list)
        await asyncio.sleep(config['SLEEP_TIME'])


async def main() -> None:
    global bot_id
    bot = Bot(token=TOKEN)
    bot_id = bot.id

    asyncio.create_task(check_news(bot))

    await dp.start_polling(bot, polling_timeout=30)


# Запуск бота
if __name__ == '__main__':
    asyncio.run(main())
