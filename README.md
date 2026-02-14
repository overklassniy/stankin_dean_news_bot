# СТАНКИН Новости деканата

Telegram бот для автоматической рассылки новостей деканата МГТУ "СТАНКИН" в группы и супергруппы.

## Оглавление

- [Особенности](#-особенности)
- [Требования](#-требования)
- [Установка](#-установка)
- [Настройка](#-настройка)
- [Запуск](#-запуск)
- [Docker](#-docker)
- [Команды бота](#-команды-бота)
- [Структура проекта](#-структура-проекта)
- [Технологии](#-технологии)

## Особенности

- Получает новости по **RSS** (URL задаётся в `.env` как `NEWS_RSS_URL`), рассылаются только категории **Аспирантура** и **Деканат**
- Автоматическая рассылка новостей во все подключённые группы
- **Поддержка топиков** в супергруппах – новости можно направить в конкретный топик
- Автоматическое добавление/удаление групп при присоединении/исключении бота
- **SQLite база данных** для надёжного хранения данных
- Логирование всех операций в файл и консоль
- Готов к запуску в Docker

## Требования

- Python 3.10+
- Telegram Bot Token (получить у [@BotFather](https://t.me/BotFather))

## Установка

### Локальная установка

1. **Клонируйте репозиторий:**

```bash
git clone https://github.com/overklassniy/stankin_dean_news_bot.git
cd stankin_dean_news_bot
```

2. **Создайте виртуальное окружение (рекомендуется):**

```bash
python -m venv venv
source venv/bin/activate  # Linux/macOS
# или
venv\Scripts\activate     # Windows
```

3. **Установите зависимости:**

```bash
pip install -r requirements.txt
```

4. **Создайте файл `.env`:**

```dotenv
BOT_TOKEN=your_bot_token_here
NEWS_RSS_URL=https://stankin.ru/...?limit=20
```

`NEWS_RSS_URL` – ссылка на RSS с новостями (например, с лимитом 20). Бот выбирает из ленты только записи категорий **Аспирантура** и **Деканат**.

## Настройка

### Файл `config.json`

```json
{
    "LOGS_DIR": "logs",
    "DB_PATH": "data/bot.db",
    "REQUEST": {
        "URL": "https://old.stankin.ru/api_entry.php",
        "HEADERS": {
            "Accept": "application/json, text/plain, */*",
            "Content-Type": "application/json;charset=UTF-8",
            "User-Agent": "Mozilla/5.0 ...",
            "Origin": "https://old.stankin.ru",
            "Referer": "https://old.stankin.ru/subdivisions/id_125/news_1"
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
    "NEWS_IMAGE_PATH": "images/stankin.jpg",
    "SLEEP_TIME": 360
}
```

### Параметры конфигурации

| Параметр | Описание |
|----------|----------|
| `LOGS_DIR` | Директория для файлов логов |
| `DB_PATH` | Путь к файлу базы данных SQLite |
| `REQUEST.URL` | URL API для получения новостей |
| `REQUEST.HEADERS` | HTTP-заголовки запроса |
| `REQUEST.DATA` | Тело запроса к API |
| `NEWS_IMAGE_PATH` | Путь к изображению для новостей |
| `SLEEP_TIME` | Интервал проверки новостей (секунды) |

### Переменные окружения

| Переменная | Описание                                                                                                                                                                                                                                |
|------------|-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `BOT_TOKEN` | Токен Telegram бота (обязательно)                                                                                                                                                                                                       |
| `NEWS_RSS_URL` | URL RSS-ленты новостей с лимитом 20 (обязательно). Рассылаются только категории «Аспирантура» и «Деканат».                                                                                                                              |
| `PROXY_URL` | Необязательно. Прокси для работы бота. **HTTP/SOCKS:** `http://host:port`, `socks4://...`, `socks5://user:pass@host:port`.                                                                                                              |
| `BOT_API_BASE_URL` | Необязательно. Адрес своего Bot API сервера. Для **MTProto** обязателен: запустите локальный сервер (например [TDLight Bot API](https://github.com/tdlight-team/tdlight-telegram-bot-api)) с настройкой MTProxy и укажите сюда его URL. |
| `DB_PATH` | Путь к БД (переопределяет config.json)                                                                                                                                                                                                  |

**Прокси: SOCKS и MTProto**

- **HTTP/SOCKS** – задайте только `PROXY_URL` (например `socks5://127.0.0.1:1080`). Запросы бота к Telegram API пойдут через этот прокси.
- **MTProto (MTProxy)** – Bot API работает по HTTP, поэтому MTProxy подключается на стороне сервера. Задайте `PROXY_URL=mtproto://хост:порт:секрет` и **обязательно** `BOT_API_BASE_URL=http://...` – адрес вашего локального Bot API сервера, который уже настроен на использование этого MTProxy (например TDLight с параметрами прокси).

## Запуск

### Локальный запуск

```bash
python bot.py
```

### Запуск в фоне (Linux)

```bash
nohup python bot.py > /dev/null 2>&1 &
```

## Docker

### Сборка и запуск

1. **Обновите ваш `docker-compose.yml`:**

```yaml
x-common: &common
  restart: always
  environment:
    - TZ=Europe/Moscow
  volumes:
    - /etc/localtime:/etc/localtime:ro
    - /etc/timezone:/etc/timezone:ro
  working_dir: /app

services:
  stankin-dean-news-bot:
    <<: *common
    build: ./stankin-dean-news-bot
    container_name: stankin-dean-news-bot
    env_file: ./stankin-dean-news-bot/.env
    volumes:
      # Логи и БД хранятся вне контейнера
      - ./stankin-dean-news-bot/logs:/app/logs
      - ./stankin-dean-news-bot/data:/app/data
      - /etc/localtime:/etc/localtime:ro
      - /etc/timezone:/etc/timezone:ro
    command: python bot.py
```

2. **Запустите:**

```bash
docker-compose up -d --build
```

### Просмотр логов

```bash
docker-compose logs -f stankin-dean-news-bot
```

## Команды бота

| Команда | Описание | Где работает |
|---------|----------|--------------|
| `/start` | Приветственное сообщение | Личные сообщения |
| `/code` | Ссылка на GitHub репозиторий | Личные сообщения |
| `/settopic` | Установить топик для новостей | Супергруппы |

### Настройка топика в супергруппе

1. Добавьте бота в супергруппу с включёнными топиками
2. Откройте нужный топик
3. Отправьте команду `/settopic`
4. Бот будет отправлять новости в этот топик

**Дополнительные опции:**
- `/settopic off` – отключить топик (новости пойдут в основной чат)
- `/settopic <id>` – указать ID топика вручную

## Структура проекта

```
stankin_dean_news_bot/
├── bot.py              # Основной файл бота
├── database.py         # Модуль работы с SQLite (aiosqlite)
├── utils.py            # Утилиты (логирование, API, отправка)
├── config.json         # Конфигурация бота
├── requirements.txt    # Зависимости Python
├── Dockerfile          # Конфигурация Docker
├── .env                # Переменные окружения (создаётся вручную)
├── data/
│   └── bot.db          # База данных SQLite (создаётся автоматически)
├── logs/               # Логи работы бота
└── images/
    └── stankin.jpg     # Изображения
```

### Описание модулей

- **`bot.py`** – главный модуль с обработчиками команд и событий
- **`database.py`** – асинхронная работа с SQLite через aiosqlite
- **`utils.py`** – вспомогательные функции (логирование, получение и отправка новостей)

## Технологии

| Технология | Назначение |
|------------|------------|
| [Python 3.10+](https://python.org) | Язык программирования |
| [aiogram 3](https://github.com/aiogram/aiogram) | Асинхронный Telegram Bot API |
| [aiohttp](https://github.com/aio-libs/aiohttp) | Асинхронные HTTP-запросы |
| [aiosqlite](https://github.com/omnilib/aiosqlite) | Асинхронная работа с SQLite |
| [python-dotenv](https://pypi.org/project/python-dotenv/) | Загрузка переменных окружения |

## Миграция с предыдущей версии

Если вы обновляетесь с версии, использующей JSON-файлы:

1. При первом запуске бот автоматически мигрирует данные из `groups.json` и `last_news_id.json`
2. Старые файлы будут переименованы в `*.json.bak`
3. Все данные будут сохранены в `data/bot.db`