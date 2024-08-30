import os
import threading
import time
from dotenv import load_dotenv
import telebot
from utils import fetch_news, send_news_to_groups, save_json_file, logger, groups, config

# Загрузка переменных окружения
load_dotenv()
TOKEN = os.getenv('BOT_TOKEN')
bot = telebot.TeleBot(TOKEN)

# Идентификатор бота
bot_id = bot.get_me().id


# Обработчик команды /code
@bot.message_handler(commands=['code'])
def handle_code_command(message: telebot.types.Message) -> None:
    """
    Обрабатывает команду /code и отправляет ссылку на GitHub репозиторий.

    Args:
        message (telebot.types.Message): Сообщение, содержащее команду /code.
    """
    github_link = "https://github.com/overklassniy/stankin_dean_news_bot"
    try:
        bot.send_message(message.chat.id, f"Исходный код бота доступен на GitHub: {github_link}")
        logger.info(f"Sent GitHub link to {message.chat.id}")
    except Exception as e:
        logger.error(f"Error sending GitHub link to {message.chat.id}: {e}")


# Обработчик личных сообщений
@bot.message_handler(func=lambda message: message.chat.type == 'private')
def handle_private_message(message: telebot.types.Message) -> None:
    """
    Обрабатывает личные сообщения пользователей.

    Args:
        message (telebot.types.Message): Сообщение, полученное ботом.
    """
    response_text = "Привет, пока у меня нет функционала в личных сообщениях. Добавьте меня в любую группу, чтобы получать актуальные новости!"
    try:
        bot.send_message(message.chat.id, response_text)
        logger.info(f"Sent private message to {message.chat.id}")
    except Exception as e:
        logger.error(f"Error sending private message to {message.chat.id}: {e}")


# Обработчик новых участников группы
@bot.message_handler(content_types=['new_chat_members'])
def handle_new_members(message: telebot.types.Message) -> None:
    """
    Добавляет чат в список, если бот был добавлен в группу.

    Args:
        message (telebot.types.Message): Сообщение о добавлении нового участника.
    """
    if any(member.id == bot_id for member in message.new_chat_members):
        if message.chat.id not in groups:
            groups.add(message.chat.id)
            save_json_file(config['GROUPS_FILE'], list(groups))
            try:
                logger.info(f"Bot added to group {message.chat.id}")
            except Exception as e:
                logger.error(f"Error sending message to group {message.chat.id}: {e}")


# Функция для периодической проверки новостей
def check_news() -> None:
    """
    Периодически проверяет наличие новых новостей и отправляет их в группы.
    """
    while True:
        news_list = fetch_news()
        if news_list:
            send_news_to_groups(bot, news_list)
        time.sleep(config['SLEEP_TIME'])


# Запуск бота
if __name__ == '__main__':
    threading.Thread(target=check_news).start()
    logger.info("Starting bot...")
    bot.infinity_polling(none_stop=True)
