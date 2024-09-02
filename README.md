# СТАНКИН Новости деканата

Этот Telegram бот автоматически получает и отправляет новости в указанные группы из API сайта МГТУ "СТАНКИН". Бот периодически проверяет наличие новых новостей и отправляет их в Telegram группы, к которым он присоединен.

## Оглавление
- [Особенности](#особенности)
- [Установка](#установка)
- [Настройка](#настройка)
- [Запуск](#запуск)
- [Использование](#использование)
- [Структура проекта](#структура-проекта)
- [Технологии](#технологии)

## Особенности

- Получает новости со [страницы Единого деканата на сайте МГТУ "СТАНКИН"](https://stankin.ru/subdivisions/id_125/news_1) через API.
- Отправляет свежие новости в указанные группы Telegram.
- Автоматически добавляет новую группу в список рассылки, когда его добавляют в неё.
- Логирование всех операций в консоль и файл.

## Установка

1. Клонируйте репозиторий:
    ```bash
    git clone https://github.com/overklassniy/stankin_dean_news_bot.git
    cd stankin_dean_news_bot
    ```

2. Установите необходимые зависимости с использованием `pip`:
    ```bash
    pip install -r requirements.txt
    ```

3. Создайте файл `.env` в корне проекта и добавьте туда токен вашего Telegram бота:
    ```dotenv
    BOT_TOKEN=your_bot_token_here
    ```

4. Создайте файл `config.json` в корне проекта, используя следующий шаблон:

    ```json
    {
        "LOGS_DIR": "logs",
        "GROUPS_FILE": "data/groups.json",
        "LAST_NEWS_ID_FILE": "data/last_news_id.json",
        "REQUEST": {
        "URL": "https://stankin.ru/api_entry.php",
        "HEADERS": {
            "Accept": "application/json, text/plain, */*",
            "Content-Type": "application/json;charset=UTF-8",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
            "Origin": "https://stankin.ru",
            "Referer": "https://stankin.ru/subdivisions/id_125/news_1"
        },
        "DATA": {
            "action": "getNews",
            "data": {
                "count": 9,
                "is_main": false,
                "page": 1,
                "pull_site": false,
                "query_search": "",
                "subdivision_id": 125,
                "tag": ""
            }
        }
    },
        "NEWS_IMAGE_URL": "https://stankin.ru/uploads/files/file_66d589eacfa20.jpg",
        "SLEEP_TIME": 360
    }
    ```

## Настройка

В файле `config.json` вы можете настроить следующие параметры:

- `LOGS_DIR`: Директория, в которой будут сохраняться файлы логов.
- `GROUPS_FILE`: Файл, в котором будет храниться список групп, в которые отправляются новости.
- `LAST_NEWS_ID_FILE`: Файл, в котором будет храниться ID последней отправленной новости.
- `REQUEST`: Параметры запроса.
  - `URL`: URL API, с которого бот будет получать новости.
  - `HEADERS`: HTTP заголовки, которые будут отправлены при запросе к API.
  - `DATA`: Тело запроса к API для получения новостей.
- `NEWS_IMAGE_URL`: Ссылка на изображение, которое будет прикрепляться к отправляемым новостям.
- `SLEEP_TIME`: Время в секундах, задающее интервал между отправкой запросов.

## Запуск

Для запуска бота выполните следующую команду:

```bash
python main.py
```

Бот автоматически начнет проверку новостей и отправку их в группы.

## Использование

- **Добавление в группу:** Чтобы бот начал отправлять новости в группу, достаточно добавить его в эту группу. Бот автоматически сохранит ID группы и начнет отправку новостей.
- **Получение новостей:** Бот периодически (каждые n секунд, заданных в config.json) проверяет наличие новых новостей и отправляет их в группы, если такие есть.
- **Получение ссылки на GitHub репозиторий:** Используйте `/code` в личных сообщениях бота, чтобы получить ссылку на этот репозиторий.

## Структура проекта

```bash
.
├── data/
│   └── groups.json          # Файл с ID групп (создается автоматически)
│   └── last_news_id.json    # Файл с последним ID новости (создается автоматически)
├── logs/                    # Логи работы бота
├── main.py                  # Основной файл для запуска бота
├── utils.py                 # Утилиты и вспомогательные функции
├── config.json              # Конфигурационный файл
├── .env                     # Файл для переменных окружения
├── requirements.txt         # Список зависимостей
└── README.md                # Документация
```

## Технологии

- [Python](https://www.python.org/downloads/) - Используемый язык программирования
- [aiogram](https://github.com/aiogram/aiogram) - Фреймворк для асинхронной работы с Telegram Bot API
- [aiohttp](https://github.com/aio-libs/aiohttp) - Библиотека для асинхронных HTTP-запросов
- [python-dotenv](https://pypi.org/project/python-dotenv/) - Библиотека для работы с переменными окружения
