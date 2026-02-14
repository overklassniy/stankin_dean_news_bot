"""
Вспомогательные утилиты для бота новостей СТАНКИН.

Модуль содержит:
- Настройку логирования
- Загрузку конфигурации
- Получение новостей из RSS (NEWS_RSS_URL)
- Отправку новостей в группы
"""

import hashlib
import html
import json
import logging
import os
import re
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path

import aiohttp
from aiogram import Bot
from aiogram.types import FSInputFile, InlineKeyboardButton, InlineKeyboardMarkup, URLInputFile

import database as db

# Категории новостей, которые рассылаем (без учёта регистра, с/без слэша)
ALLOWED_CATEGORIES = frozenset(('аспирантура', 'деканат'))


def load_config(config_path: str = 'config.json') -> dict:
    """
    Загружает конфигурацию бота из JSON-файла.

    Открывает файл в UTF-8, парсит JSON и возвращает словарь (LOGS_DIR, DB_PATH,
    REQUEST, NEWS_IMAGE_PATH, SLEEP_TIME и др.). Используется при старте модуля.

    Args:
        config_path: Путь к файлу (по умолчанию config.json).

    Returns:
        dict: Словарь с конфигурационными данными.

    Raises:
        FileNotFoundError: Если файл не найден.
        json.JSONDecodeError: Если содержимое не валидный JSON.
    """
    with open(config_path, 'r', encoding='utf-8') as config_file:
        return json.load(config_file)


config = load_config()


def setup_logger(logs_dir: str = None) -> logging.Logger:
    """
    Настраивает логирование для вывода в файл и консоль.

    Создаёт директорию для логов (если нужно), файл с именем по текущей дате/времени,
    очищает существующие обработчики корневого логгера и добавляет FileHandler и StreamHandler
    с единым форматом. Уровень – INFO.

    Args:
        logs_dir: Директория для файлов логов. Если None, берётся из config['LOGS_DIR'] или 'logs'.

    Returns:
        logging.Logger: Настроенный корневой логгер.
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


def _normalize_category(cat: str) -> str:
    """
    Нормализует строку категории для сравнения с ALLOWED_CATEGORIES.

    Убирает пробелы по краям и завершающий слэш, приводит к нижнему регистру,
    чтобы «Аспирантура/» и «деканат» совпадали с множеством разрешённых категорий.

    Args:
        cat: Сырая строка категории из RSS (например "Аспирантура/").

    Returns:
        Нормализованная строка или пустая, если cat пустой.
    """
    if not cat:
        return ""
    return cat.strip().rstrip("/").lower()


def _normalize_link(link: str) -> str:
    """
    Нормализует URL новости для стабильного id и дедупликации.

    Обрезает пробелы и завершающий слэш, чтобы один и тот же материал
    не считался разным из-за «https://site.ru/a» и «https://site.ru/a/».

    Args:
        link: Ссылка на новость из RSS.

    Returns:
        Нормализованная ссылка; если после обрезки пусто – возвращается исходная link.
    """
    return link.strip().rstrip("/") or link


def _stable_news_id(link: str) -> int:
    """
    Вычисляет стабильный целочисленный id новости по ссылке.

    Используется для дедупликации в БД: один и тот же URL всегда даёт один id.
    Алгоритм: нормализация ссылки, MD5-хэш, первые 16 hex-символов как число по модулю 2^63.

    Args:
        link: URL новости (будет нормализован через _normalize_link).

    Returns:
        Неотрицательное целое число – уникальный идентификатор новости.
    """
    h = hashlib.md5(_normalize_link(link).encode("utf-8")).hexdigest()
    return int(h[:16], 16) % (2**63)


def _parse_rss_item(item: ET.Element, ns: dict) -> dict | None:
    """
    Парсит один элемент <item> из RSS-ленты в словарь новости или отбрасывает его.

    Извлекает title, link, category, pubDate, description, enclosure; проверяет категорию
    по ALLOWED_CATEGORIES (аспирантура, деканат). Если категория не подходит или нет link,
    возвращает None. Иначе возвращает словарь с полями id (хэш link), title, link, description,
    pubDate, category, enclosure_url, sort_date (datetime для сортировки).

    Args:
        item: XML-элемент <item> (ElementTree).
        ns: Словарь namespace для find (обычно пустой для RSS 2.0).

    Returns:
        Словарь с данными новости или None при неподходящей категории/отсутствии link.
    """
    def text(el: ET.Element | None, tag: str) -> str:
        if el is None:
            return ""
        child = el.find(tag, ns)
        return (child.text or "").strip()

    title = text(item, "title")
    link = text(item, "link")
    if not link:
        return None

    category_el = item.find("category", ns)
    category_raw = (category_el.text or "").strip()
    if _normalize_category(category_raw) not in ALLOWED_CATEGORIES:
        return None

    pub_date = text(item, "pubDate")
    description = text(item, "description")

    enclosure_url = ""
    enc = item.find("enclosure", ns)
    if enc is not None and enc.get("url"):
        enclosure_url = (enc.get("url") or "").strip()

    sort_date = _parse_pub_date_for_sort(pub_date)

    link_norm = _normalize_link(link)
    return {
        "id": _stable_news_id(link_norm),
        "title": title,
        "link": link_norm,
        "description": description,
        "pubDate": pub_date,
        "category": category_raw,
        "enclosure_url": enclosure_url,
        "sort_date": sort_date,
    }


async def fetch_news() -> list[dict]:
    """
    Загружает новости из RSS и возвращает отфильтрованный и дедуплицированный список.

    Берет URL из переменной окружения NEWS_RSS_URL, выполняет GET-запрос, парсит XML.
    Оставляет только элементы с категорией «Аспирантура» или «Деканат» (без учёта регистра).
    Убирает дубликаты по ссылке (одна запись на URL), сортирует по дате публикации (новые первые).
    Каждая новость имеет стабильный id (хэш ссылки) для последующей дедупликации в БД.

    Returns:
        Список словарей новостей с ключами id, title, link, description, pubDate,
        category, enclosure_url, sort_date. Пустой список при ошибке или отсутствии NEWS_RSS_URL.
    """
    rss_url = os.getenv("NEWS_RSS_URL")
    if not rss_url:
        logger.error("NEWS_RSS_URL не задан в .env")
        return []

    ns = {}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                rss_url,
                timeout=aiohttp.ClientTimeout(total=30),
            ) as response:
                response.raise_for_status()
                raw = await response.text()
    except aiohttp.ClientError as e:
        logger.error(f"Ошибка при получении RSS: {e}")
        return []
    except Exception as e:
        logger.error(f"Неожиданная ошибка при получении новостей: {e}")
        return []

    try:
        root = ET.fromstring(raw)
    except ET.ParseError as e:
        logger.error(f"Ошибка разбора RSS XML: {e}")
        return []

    # RSS 2.0: channel -> item
    channel = root.find("channel", ns)
    if channel is None:
        channel = root

    news = []
    for item in channel.findall("item", ns):
        parsed = _parse_rss_item(item, ns)
        if parsed:
            news.append(parsed)

    # Одна новость – один раз (по ссылке), чтобы не слать дубликаты
    seen_links = set()
    unique = []
    for n in news:
        link = n["link"]
        if link not in seen_links:
            seen_links.add(link)
            unique.append(n)
    news = unique

    # Сортируем по дате: сначала самые новые
    news.sort(key=lambda x: (x.get("sort_date") or datetime.min), reverse=True)
    logger.debug(f"Получено {len(news)} новостей из RSS (категории: аспирантура, деканат)")
    return news


def _parse_pub_date_for_sort(pub_date: str) -> datetime | None:
    """
    Парсит строку pubDate из RSS в datetime для сортировки.

    Ожидает формат вида "Fri, 06 Feb 2026 00:00:00 +0300". Убирает суффикс таймзоны,
    разбирает дату и время. При ошибке разбора возвращает None.

    Args:
        pub_date: Строка даты/времени из элемента <pubDate>.

    Returns:
        datetime или None при пустой строке или неверном формате.
    """
    if not pub_date:
        return None
    try:
        parts = pub_date.replace("+0300", "").replace("+0000", "").strip().rsplit(maxsplit=1)
        s = parts[0] if parts else pub_date
        return datetime.strptime(s, "%a, %d %b %Y %H:%M:%S")
    except Exception:
        return None


# День недели и месяц полностью по-русски (для даты "Среда, 28 января 2026")
_WEEKDAY_RU_FULL = ("Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье")
_MONTH_RU_FULL = (
    "января", "февраля", "марта", "апреля", "мая", "июня", "июля",
    "августа", "сентября", "октября", "ноября", "декабря",
)


def _format_pub_date(pub_date: str) -> str:
    """
    Форматирует pubDate из RSS в полный русский вид для отображения в сообщении.

    Пробует форматы с временем и без ("%a, %d %b %Y %H:%M:%S", "%a, %d %b %Y").
    Убирает таймзону в конце. Результат: «Среда, 28 января 2026» (день недели и месяц
    по-русски, число без ведущего нуля). При ошибке парсинга возвращает обрезок исходной строки.

    Args:
        pub_date: Сырая строка из <pubDate>.

    Returns:
        Строка вида "Среда, 28 января 2026" или fallback до 20 символов.
    """
    if not pub_date:
        return ""
    s = pub_date.replace("+0300", "").replace("+0000", "").strip()
    s = re.sub(r"\s+[A-Z]{2,4}$", "", s)
    s = s.strip()
    for fmt in ("%a, %d %b %Y %H:%M:%S", "%a, %d %b %Y"):
        try:
            parsed = datetime.strptime(s, fmt)
            wd = _WEEKDAY_RU_FULL[parsed.weekday()]
            mo = _MONTH_RU_FULL[parsed.month - 1]
            return f"{wd}, {parsed.day} {mo} {parsed.year}"
        except ValueError:
            continue
    return pub_date[:20] if len(pub_date) > 20 else pub_date


# Лимиты Telegram: подпись к фото – 1024, обычное сообщение – 4096
CAPTION_LIMIT = 1024
MESSAGE_LIMIT = 4096


def _strip_inner_html(html_fragment: str) -> str:
    """
    Удаляет все HTML-теги из фрагмента и возвращает чистый текст.

    Используется для содержимого элементов списков (<li>) при преобразовании
    в буллеты/нумерацию. После удаления тегов применяется html.unescape и strip.

    Args:
        html_fragment: Строка с возможными тегами (например "<b>текст</b>").

    Returns:
        Текст без тегов, с разэкранированными сущностями, без пробелов по краям.
    """
    t = re.sub(r"<[^>]+>", "", html_fragment)
    return html.unescape(t).strip()


def _html_list_to_bullets(html_fragment: str) -> str:
    """
    Заменяет HTML-списки на текстовые с буллетами и нумерацией (Telegram не поддерживает ul/ol).

    Алгоритм: сначала обрабатываются <ol> – каждый <li> превращается в "1. текст", "2. текст" и т.д.;
    затем <ul> – каждый <li> в "• текст". Внутри элементов теги снимаются через _strip_inner_html.
    Остальной HTML не меняется (будут обработаны позже при общем снятии тегов).

    Args:
        html_fragment: HTML-фрагмент из description (может содержать <ol>, <ul>, <li>).

    Returns:
        Тот же фрагмент с заменёнными блоками списков на строки с номерами/буллетами.
    """
    result = []
    # Нумерованный список: <ol>...</ol>
    def replace_ol(m: re.Match) -> str:
        inner = m.group(1)
        items = re.findall(r"<li[^>]*>(.*?)</li>", inner, re.DOTALL | re.I)
        return "\n".join(f"{i + 1}. {_strip_inner_html(it)}" for i, it in enumerate(items))

    s = re.sub(r"<ol[^>]*>(.*?)</ol>", replace_ol, html_fragment, flags=re.DOTALL | re.I)
    # Маркированный список: <ul>...</ul>
    def replace_ul(m: re.Match) -> str:
        inner = m.group(1)
        items = re.findall(r"<li[^>]*>(.*?)</li>", inner, re.DOTALL | re.I)
        return "\n".join(f"• {_strip_inner_html(it)}" for it in items)

    s = re.sub(r"<ul[^>]*>(.*?)</ul>", replace_ul, s, flags=re.DOTALL | re.I)
    return s


def _normalize_whitespace(s: str) -> str:
    """
    Нормализует пробелы и переводы строк в тексте.

    В каждой строке множественные пробелы схлопываются в один, обрезаются пробелы по краям.
    Подряд идущие пустые строки сокращаются до одной (между абзацами остаётся одна пустая).
    Итоговая строка обрезается по краям.

    Args:
        s: Исходный текст (например из HTML description после снятия тегов).

    Returns:
        Текст с нормализованными пробелами и не более одной пустой строки подряд.
    """
    if not s:
        return ""
    lines = [re.sub(r" +", " ", line.strip()) for line in s.splitlines()]
    # Убираем подряд идущие пустые строки – оставляем максимум одну пустую между блоками
    out = []
    for line in lines:
        if line:
            out.append(line)
        elif out and out[-1] != "":
            out.append("")
    return "\n".join(out).strip()


def _html_description_to_text(html_fragment: str) -> str:
    """
    Преобразует HTML из поля description RSS в плоский текст для поста.

    Алгоритм: сначала списки (<ol>, <ul>) заменяются на строки с нумерацией и буллетами;
    затем <br> и </p><p> превращаются в переводы строк; все оставшиеся теги удаляются;
    применяется html.unescape и _normalize_whitespace.

    Args:
        html_fragment: Сырой HTML из <description> элемента RSS.

    Returns:
        Один текст без тегов, с переносами и нормализованными пробелами.
    """
    if not html_fragment:
        return ""
    s = html_fragment.strip()
    s = _html_list_to_bullets(s)
    s = re.sub(r"<br\s*/?>", "\n", s, flags=re.I)
    s = re.sub(r"</p>\s*<p[^>]*>", "\n\n", s, flags=re.I)
    s = re.sub(r"<[^>]+>", "", s)
    s = html.unescape(s)
    s = _normalize_whitespace(s)
    return s


def _escape_for_telegram_html(s: str) -> str:
    """
    Экранирует символы, опасные в HTML-режиме Telegram (parse_mode='HTML').

    Заменяет & на &amp;, < на &lt;, > на &gt;, чтобы произвольный текст не ломал разметку
    и не внедрял теги при вставке в подпись/сообщение.

    Args:
        s: Произвольная строка (например текст описания новости).

    Returns:
        Строка с экранированными &, <, >.
    """
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def format_news_message(news: dict, caption_limit: int = MESSAGE_LIMIT) -> tuple[str, str]:
    """
    Собирает текст поста для Telegram из данных одной новости.

    Структура: заголовок (ссылка + жирный title), дата в русском формате, затем описание
    в <blockquote>. Если полное описание умещается в caption_limit – блок «Читать далее» не добавляется.
    Если не умещается – описание обрезается с «...» в конце внутри blockquote и после блока
    добавляется ссылка «Читать далее...». Длина итоговой строки не превышает caption_limit.

    Args:
        news: Словарь новости с ключами title, link, pubDate, description (и др.).
        caption_limit: Максимальная длина сообщения (1024 для подписи к фото, 4096 для текста).

    Returns:
        Кортеж (текст сообщения в HTML для parse_mode='HTML', url новости).
    """
    title = news.get("title", "")
    link = news.get("link", "")
    pub_date = _format_pub_date(news.get("pubDate", ""))
    header = f'<a href="{link}"><b>{title}</b></a>\n\n🗓 {pub_date}'
    if not pub_date:
        header = f'<a href="{link}"><b>{title}</b></a>'

    description = _html_description_to_text(news.get("description", ""))
    if not description:
        return header, link

    desc_safe = _escape_for_telegram_html(description)
    read_more_block = '\n\n<a href="' + link + '">Читать далее...</a>'
    header_with_sep = header + "\n\n"
    blockquote_open, blockquote_close = "<blockquote>", "</blockquote>"
    # Место под текст внутри blockquote без «Читать далее»
    max_quote_full = caption_limit - len(header_with_sep) - len(blockquote_open) - len(blockquote_close)
    # Место с учётом «Читать далее» (если придётся обрезать)
    max_quote_truncated = max_quote_full - len(read_more_block)

    if len(desc_safe) <= max_quote_full:
        # Всё уместилось – без «Читать далее»
        quote_content = desc_safe
        message = header_with_sep + blockquote_open + quote_content + blockquote_close
        return message, link

    if max_quote_truncated <= 0:
        message = header + read_more_block
        return message, link
    quote_content = desc_safe[: max_quote_truncated - 3].rstrip() + "..."
    message = header_with_sep + blockquote_open + quote_content + blockquote_close + read_more_block
    return message, link


async def send_news_to_groups(bot: Bot, news_list: list[dict], db_path: str = None) -> int:
    """
    Рассылает не отправленные ранее новости во все зарегистрированные группы.

    Для каждой новости проверяется БД: если news_id уже в sent_news – пропуск (continue).
    Иначе формируется сообщение с учётом лимита (1024 при отправке с фото, 4096 без фото),
    выбирается фото (enclosure из RSS или fallback из конфига). Сообщение отправляется
    во все группы (с учётом topic_id для супергрупп); при успехе хотя бы в одну группу
    новость помечается как отправленная. Возвращается количество новостей, отправленных в этот вызов.

    Args:
        bot: Экземпляр aiogram Bot для отправки сообщений.
        news_list: Список словарей новостей (рекомендуется отсортированный по дате).
        db_path: Путь к SQLite БД; None – использовать значение по умолчанию.

    Returns:
        Число новостей, успешно разосланных (каждая хотя бы в одну группу).
    """
    groups = await db.get_all_groups(db_path)
    if not groups:
        logger.warning("Нет групп для отправки новостей")
        return 0

    image_path = Path(config.get("NEWS_IMAGE_PATH", "images/stankin.jpg"))
    fallback_photo = None
    if image_path.exists():
        fallback_photo = FSInputFile(image_path)
    else:
        logger.warning(f"Изображение по умолчанию не найдено: {image_path}")

    # news_list уже отсортирован по sort_date (новые первые)
    sent_count = 0

    for news in news_list:
        news_id = news["id"]
        if await db.is_news_sent(news_id, db_path):
            logger.debug(f"Новость уже отправлялась, пропускаем")
            continue

        # Подпись к фото в Telegram – не более 1024 символов
        has_photo = bool(
            news.get("enclosure_url") and news["enclosure_url"].startswith("http")
        ) or fallback_photo is not None
        caption_limit = CAPTION_LIMIT if has_photo else MESSAGE_LIMIT
        message, news_url = format_news_message(news, caption_limit=caption_limit)

        read_kb = InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="Прочитать", url=news_url)]]
        )

        if news.get("enclosure_url") and news["enclosure_url"].startswith("http"):
            photo = URLInputFile(news["enclosure_url"])
        elif fallback_photo:
            photo = fallback_photo
        else:
            logger.warning("Нет изображения для новости, отправляем без фото")
            photo = None

        success_in_any_group = False
        for group in groups:
            chat_id = group["chat_id"]
            topic_id = group.get("topic_id")
            try:
                if photo:
                    if topic_id:
                        await bot.send_photo(
                            chat_id=chat_id,
                            message_thread_id=topic_id,
                            photo=photo,
                            caption=message,
                            parse_mode="HTML",
                            reply_markup=read_kb,
                        )
                    else:
                        await bot.send_photo(
                            chat_id=chat_id,
                            photo=photo,
                            caption=message,
                            parse_mode="HTML",
                            reply_markup=read_kb,
                        )
                else:
                    text = message + "\n\n" + news_url
                    if topic_id:
                        await bot.send_message(
                            chat_id=chat_id,
                            message_thread_id=topic_id,
                            text=text,
                            parse_mode="HTML",
                            reply_markup=read_kb,
                        )
                    else:
                        await bot.send_message(
                            chat_id=chat_id,
                            text=text,
                            parse_mode="HTML",
                            reply_markup=read_kb,
                        )
                logger.info(f"Отправлена новость «{news['title'][:50]}...» в группу {chat_id}")
                success_in_any_group = True
            except Exception as e:
                logger.error(f"Ошибка отправки в группу {chat_id}: {e}")

        if success_in_any_group:
            await db.mark_news_sent(news_id, db_path)
            sent_count += 1

    if sent_count > 0:
        logger.info(f"Отправлено {sent_count} новых новостей")
    return sent_count
