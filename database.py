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
    Инициализирует базу данных и создаёт необходимые таблицы.
    
    Args:
        db_path: Путь к файлу базы данных. Если None, используется DB_PATH.
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
        
        # Таблица настроек (для хранения last_news_id и других параметров)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)
        
        await db.commit()
        logger.info(f"База данных инициализирована: {path}")


async def get_db_connection(db_path: Optional[str] = None) -> aiosqlite.Connection:
    """
    Создаёт и возвращает соединение с базой данных.
    
    Args:
        db_path: Путь к файлу базы данных.
    
    Returns:
        Соединение с базой данных.
    """
    path = db_path or DB_PATH
    return await aiosqlite.connect(path)


# === Функции для работы с группами ===

async def add_group(chat_id: int, is_supergroup: bool = False, db_path: Optional[str] = None) -> bool:
    """
    Добавляет группу в базу данных.
    
    Args:
        chat_id: ID чата/группы.
        is_supergroup: Является ли чат супергруппой.
        db_path: Путь к файлу базы данных.
    
    Returns:
        True если группа добавлена, False если уже существует.
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
    Удаляет группу из базы данных.
    
    Args:
        chat_id: ID чата/группы.
        db_path: Путь к файлу базы данных.
    
    Returns:
        True если группа удалена, False если не существовала.
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
    Получает список всех групп из базы данных.
    
    Args:
        db_path: Путь к файлу базы данных.
    
    Returns:
        Список словарей с информацией о группах.
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
    Устанавливает топик для супергруппы.
    
    Args:
        chat_id: ID чата/супергруппы.
        topic_id: ID топика (None для отключения).
        db_path: Путь к файлу базы данных.
    
    Returns:
        True если топик установлен, False если группа не найдена.
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
    Получает информацию о группе.
    
    Args:
        chat_id: ID чата/группы.
        db_path: Путь к файлу базы данных.
    
    Returns:
        Словарь с информацией о группе или None.
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
    Обновляет статус супергруппы.
    
    Args:
        chat_id: ID чата.
        is_supergroup: Новый статус.
        db_path: Путь к файлу базы данных.
    
    Returns:
        True если обновлено успешно.
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
    Проверяет, была ли новость уже отправлена.
    
    Новость считается отправленной, если:
    - Её ID есть в таблице sent_news, ИЛИ
    - Её ID меньше или равен максимальному ID в таблице
      (для совместимости с миграцией из JSON)
    
    Args:
        news_id: ID новости.
        db_path: Путь к файлу базы данных.
    
    Returns:
        True если новость уже отправлена.
    """
    path = db_path or DB_PATH
    async with aiosqlite.connect(path) as db:
        # Проверяем: либо ID есть в таблице, либо ID <= max(news_id)
        cursor = await db.execute(
            """
            SELECT 1 FROM sent_news 
            WHERE news_id = ? 
               OR ? <= (SELECT MAX(news_id) FROM sent_news)
            """,
            (news_id, news_id)
        )
        return await cursor.fetchone() is not None


async def mark_news_sent(news_id: int, db_path: Optional[str] = None) -> None:
    """
    Отмечает новость как отправленную.
    
    Args:
        news_id: ID новости.
        db_path: Путь к файлу базы данных.
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
    Получает максимальный ID отправленной новости.
    
    Args:
        db_path: Путь к файлу базы данных.
    
    Returns:
        Максимальный ID или None если новостей нет.
    """
    path = db_path or DB_PATH
    async with aiosqlite.connect(path) as db:
        cursor = await db.execute("SELECT MAX(news_id) FROM sent_news")
        row = await cursor.fetchone()
        return row[0] if row and row[0] else None


async def cleanup_old_news(keep_count: int = 1000, db_path: Optional[str] = None) -> int:
    """
    Очищает старые записи об отправленных новостях, оставляя последние keep_count.
    
    Args:
        keep_count: Количество записей для сохранения.
        db_path: Путь к файлу базы данных.
    
    Returns:
        Количество удалённых записей.
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


# === Функции для работы с настройками ===

async def get_setting(key: str, default: Optional[str] = None, db_path: Optional[str] = None) -> Optional[str]:
    """
    Получает значение настройки.
    
    Args:
        key: Ключ настройки.
        default: Значение по умолчанию.
        db_path: Путь к файлу базы данных.
    
    Returns:
        Значение настройки или default.
    """
    path = db_path or DB_PATH
    async with aiosqlite.connect(path) as db:
        cursor = await db.execute(
            "SELECT value FROM settings WHERE key = ?",
            (key,)
        )
        row = await cursor.fetchone()
        return row[0] if row else default


async def set_setting(key: str, value: str, db_path: Optional[str] = None) -> None:
    """
    Устанавливает значение настройки.
    
    Args:
        key: Ключ настройки.
        value: Значение настройки.
        db_path: Путь к файлу базы данных.
    """
    path = db_path or DB_PATH
    async with aiosqlite.connect(path) as db:
        await db.execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
            (key, value)
        )
        await db.commit()


async def migrate_from_json(groups_file: str, last_news_file: str, db_path: Optional[str] = None) -> None:
    """
    Мигрирует данные из JSON файлов в SQLite.
    
    Args:
        groups_file: Путь к файлу groups.json.
        last_news_file: Путь к файлу last_news_id.json.
        db_path: Путь к файлу базы данных.
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
