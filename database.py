"""
Модуль для работы с базой данных SQLite через aiosqlite.

Предоставляет асинхронные функции для управления:
- Группами/чатами, в которые отправляются новости
- ID отправленных новостей для предотвращения дублей
- Настройками топиков для супергрупп
"""

import aiosqlite
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Путь к БД по умолчанию (может быть переопределён через конфиг)
DB_PATH = "data/bot.db"


async def init_db(db_path: Optional[str] = None) -> None:
    """
    Инициализирует базу данных и создаёт необходимые таблицы, если их ещё нет.

    Создаёт директорию для файла БД при необходимости. Таблицы: groups (chat_id, topic_id,
    is_supergroup, added_at), sent_news (news_id, sent_at). Используется CREATE TABLE IF NOT EXISTS.

    Args:
        db_path: Путь к файлу SQLite. Если None, используется DB_PATH.

    Returns:
        None.
    """
    path = db_path or DB_PATH
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    
    async with aiosqlite.connect(path) as db:
        # Таблица групп с поддержкой топиков
        await db.execute("""
            CREATE TABLE IF NOT EXISTS groups (
                chat_id INTEGER PRIMARY KEY,
                topic_id INTEGER DEFAULT NULL,
                is_supergroup BOOLEAN DEFAULT FALSE,
                added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Таблица отправленных новостей (для предотвращения дублей)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS sent_news (
                news_id INTEGER PRIMARY KEY,
                sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        await db.commit()
        logger.info(f"База данных инициализирована: {path}")


async def get_db_connection(db_path: Optional[str] = None) -> aiosqlite.Connection:
    """
    Создаёт и возвращает асинхронное соединение с SQLite.

    Вызывающий код должен сам закрывать соединение после использования.

    Args:
        db_path: Путь к файлу БД. Если None – DB_PATH.

    Returns:
        Открытое соединение aiosqlite.Connection.
    """
    path = db_path or DB_PATH
    return await aiosqlite.connect(path)


# === Функции для работы с группами ===

async def add_group(chat_id: int, is_supergroup: bool = False, db_path: Optional[str] = None) -> bool:
    """
    Регистрирует группу (чат) для рассылки новостей.

    Вставляет запись в таблицу groups. При дубликате chat_id (IntegrityError)
    вставка игнорируется.

    Args:
        chat_id: ID чата/группы Telegram.
        is_supergroup: True, если чат – супергруппа (для топиков).
        db_path: Путь к БД; None – DB_PATH.

    Returns:
        True, если группа добавлена; False, если уже существовала.
    """
    path = db_path or DB_PATH
    async with aiosqlite.connect(path) as db:
        try:
            await db.execute(
                "INSERT INTO groups (chat_id, is_supergroup) VALUES (?, ?)",
                (chat_id, is_supergroup)
            )
            await db.commit()
            logger.info(f"Группа {chat_id} добавлена в БД (supergroup={is_supergroup})")
            return True
        except aiosqlite.IntegrityError:
            logger.debug(f"Группа {chat_id} уже существует в БД")
            return False


async def remove_group(chat_id: int, db_path: Optional[str] = None) -> bool:
    """
    Удаляет группу из списка рассылки.

    Выполняет DELETE FROM groups WHERE chat_id = ?.

    Args:
        chat_id: ID чата/группы.
        db_path: Путь к БД; None – DB_PATH.

    Returns:
        True, если была удалена хотя бы одна запись; иначе False.
    """
    path = db_path or DB_PATH
    async with aiosqlite.connect(path) as db:
        cursor = await db.execute("DELETE FROM groups WHERE chat_id = ?", (chat_id,))
        await db.commit()
        deleted = cursor.rowcount > 0
        if deleted:
            logger.info(f"Группа {chat_id} удалена из БД")
        return deleted


async def get_all_groups(db_path: Optional[str] = None) -> list[dict]:
    """
    Возвращает все зарегистрированные группы для рассылки.

    Выбирает chat_id, topic_id, is_supergroup из таблицы groups. Результат – список
    словарей, пригодный для итерации при отправке новостей.

    Args:
        db_path: Путь к БД; None – DB_PATH.

    Returns:
        Список dict с ключами chat_id, topic_id, is_supergroup.
    """
    path = db_path or DB_PATH
    async with aiosqlite.connect(path) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT chat_id, topic_id, is_supergroup FROM groups"
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]


async def set_topic(chat_id: int, topic_id: Optional[int], db_path: Optional[str] = None) -> bool:
    """
    Устанавливает или сбрасывает топик для супергруппы.

    Обновляет поле topic_id в таблице groups для данного chat_id. topic_id=None
    отключает топик (новости идут в основной чат).

    Args:
        chat_id: ID чата/супергруппы.
        topic_id: ID топика или None.
        db_path: Путь к БД; None – DB_PATH.

    Returns:
        True, если обновлена хотя бы одна строка; False, если группа не найдена.
    """
    path = db_path or DB_PATH
    async with aiosqlite.connect(path) as db:
        cursor = await db.execute(
            "UPDATE groups SET topic_id = ? WHERE chat_id = ?",
            (topic_id, chat_id)
        )
        await db.commit()
        updated = cursor.rowcount > 0
        if updated:
            logger.info(f"Топик {topic_id} установлен для группы {chat_id}")
        return updated


async def get_group(chat_id: int, db_path: Optional[str] = None) -> Optional[dict]:
    """
    Возвращает данные одной группы по chat_id.

    Args:
        chat_id: ID чата/группы.
        db_path: Путь к БД; None – DB_PATH.

    Returns:
        Словарь с ключами chat_id, topic_id, is_supergroup или None, если группа не найдена.
    """
    path = db_path or DB_PATH
    async with aiosqlite.connect(path) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT chat_id, topic_id, is_supergroup FROM groups WHERE chat_id = ?",
            (chat_id,)
        )
        row = await cursor.fetchone()
        return dict(row) if row else None


async def update_group_supergroup_status(chat_id: int, is_supergroup: bool, db_path: Optional[str] = None) -> bool:
    """
    Обновляет поле is_supergroup для группы.

    Args:
        chat_id: ID чата.
        is_supergroup: Новое значение флага супергруппы.
        db_path: Путь к БД; None – DB_PATH.

    Returns:
        True, если обновлена хотя бы одна строка.
    """
    path = db_path or DB_PATH
    async with aiosqlite.connect(path) as db:
        cursor = await db.execute(
            "UPDATE groups SET is_supergroup = ? WHERE chat_id = ?",
            (is_supergroup, chat_id)
        )
        await db.commit()
        return cursor.rowcount > 0


# === Функции для работы с отправленными новостями ===

async def is_news_sent(news_id: int, db_path: Optional[str] = None) -> bool:
    """
    Проверяет, есть ли новость в таблице отправленных (дедупликация).

    Выполняет SELECT по news_id в sent_news. Используется перед рассылкой, чтобы
    не отправлять одну и ту же новость повторно.

    Args:
        news_id: Идентификатор новости (например хэш ссылки).
        db_path: Путь к БД; None – DB_PATH.

    Returns:
        True, если запись с таким news_id есть в sent_news; иначе False.
    """
    path = db_path or DB_PATH
    async with aiosqlite.connect(path) as db:
        cursor = await db.execute(
            "SELECT 1 FROM sent_news WHERE news_id = ?",
            (news_id,),
        )
        return await cursor.fetchone() is not None


async def mark_news_sent(news_id: int, db_path: Optional[str] = None) -> None:
    """
    Добавляет новость в таблицу отправленных (после успешной рассылки).

    Используется INSERT OR IGNORE, чтобы повторный вызов для того же news_id не вызывал ошибку.

    Args:
        news_id: Идентификатор новости.
        db_path: Путь к БД; None – DB_PATH.

    Returns:
        None.
    """
    path = db_path or DB_PATH
    async with aiosqlite.connect(path) as db:
        await db.execute(
            "INSERT OR IGNORE INTO sent_news (news_id) VALUES (?)",
            (news_id,)
        )
        await db.commit()
        logger.debug(f"Новость {news_id} отмечена как отправленная")


async def get_max_sent_news_id(db_path: Optional[str] = None) -> Optional[int]:
    """
    Возвращает максимальный news_id из таблицы sent_news.

    Может использоваться для совместимости со старыми схемами или отладки.

    Args:
        db_path: Путь к БД; None – DB_PATH.

    Returns:
        Максимальный news_id или None, если записей нет.
    """
    path = db_path or DB_PATH
    async with aiosqlite.connect(path) as db:
        cursor = await db.execute("SELECT MAX(news_id) FROM sent_news")
        row = await cursor.fetchone()
        return row[0] if row and row[0] else None


async def cleanup_old_news(keep_count: int = 1000, db_path: Optional[str] = None) -> int:
    """
    Удаляет старые записи из sent_news, оставляя последние keep_count по news_id.

    Уменьшает размер таблицы при длительной работе бота. Удаляются записи с наименьшими
    news_id (старые по времени добавления, если id растут).

    Args:
        keep_count: Сколько последних записей оставить.
        db_path: Путь к БД; None – DB_PATH.

    Returns:
        Число удалённых строк.
    """
    path = db_path or DB_PATH
    async with aiosqlite.connect(path) as db:
        cursor = await db.execute("""
            DELETE FROM sent_news 
            WHERE news_id NOT IN (
                SELECT news_id FROM sent_news 
                ORDER BY news_id DESC 
                LIMIT ?
            )
        """, (keep_count,))
        await db.commit()
        deleted = cursor.rowcount
        if deleted > 0:
            logger.info(f"Очищено {deleted} старых записей о новостях")
        return deleted


async def migrate_from_json(groups_file: str, last_news_file: str, db_path: Optional[str] = None) -> None:
    """
    Переносит данные из старых JSON-файлов в SQLite (однократная миграция).

    Если существует groups_file – читает список групп (формат: список chat_id или [chat_id, topic_id]),
    вставляет их в таблицу groups с INSERT OR IGNORE. Если существует last_news_file – читает
    last_news_id и вставляет одну запись в sent_news. Кодировки для groups: utf-8, utf-8-sig, cp1251, latin-1.

    Args:
        groups_file: Путь к groups.json.
        last_news_file: Путь к last_news_id.json.
        db_path: Путь к SQLite; None – DB_PATH.

    Returns:
        None.
    """
    import json
    from pathlib import Path
    
    path = db_path or DB_PATH
    
    # Миграция групп
    groups_path = Path(groups_file)
    if groups_path.exists():
        try:
            # Пробуем разные кодировки
            content = None
            for encoding in ['utf-8', 'utf-8-sig', 'cp1251', 'latin-1']:
                try:
                    with open(groups_path, 'r', encoding=encoding) as f:
                        content = f.read()
                    break
                except UnicodeDecodeError:
                    continue
            
            if content is None:
                logger.error(f"Не удалось прочитать {groups_file} ни в одной кодировке")
                return
            
            groups = json.loads(content)
            
            async with aiosqlite.connect(path) as db:
                migrated_count = 0
                for group in groups:
                    try:
                        if isinstance(group, list):
                            # Формат [chat_id, topic_id]
                            chat_id, topic_id = group[0], group[1]
                            await db.execute(
                                "INSERT OR IGNORE INTO groups (chat_id, topic_id, is_supergroup) VALUES (?, ?, TRUE)",
                                (chat_id, topic_id)
                            )
                        else:
                            # Просто chat_id
                            await db.execute(
                                "INSERT OR IGNORE INTO groups (chat_id) VALUES (?)",
                                (group,)
                            )
                        migrated_count += 1
                    except Exception as e:
                        logger.warning(f"Ошибка миграции группы {group}: {e}")
                await db.commit()
            
            logger.info(f"Мигрировано {migrated_count} групп из {groups_file}")
        except json.JSONDecodeError as e:
            logger.error(f"Ошибка парсинга JSON в {groups_file}: {e}")
        except Exception as e:
            logger.error(f"Ошибка при миграции групп: {e}")
    
    # Миграция last_news_id
    last_news_path = Path(last_news_file)
    if last_news_path.exists():
        try:
            with open(last_news_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            last_id = data.get('last_news_id', 0)
            if last_id:
                # Помечаем все новости до last_id как отправленные
                async with aiosqlite.connect(path) as db:
                    await db.execute(
                        "INSERT OR IGNORE INTO sent_news (news_id) VALUES (?)",
                        (last_id,)
                    )
                    await db.commit()
                logger.info(f"Мигрирован last_news_id: {last_id}")
        except Exception as e:
            logger.error(f"Ошибка при миграции last_news_id: {e}")
