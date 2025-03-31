import sqlite3
from datetime import datetime


class DatabaseManager:
    def __init__(self, db_path='flashcard.db'):
        # Инициализация менеджера базы данных
        # db_path - путь к файлу базы данных (по умолчанию flashcard.db)
        self.db_path = db_path
        self.conn = None
        self._initialize_db()

    def _initialize_db(self):
        """Инициализация базы данных и создание таблиц"""
        try:
            # Установка соединения с SQLite базой данных
            self.conn = sqlite3.connect(self.db_path)
            cursor = self.conn.cursor()

            # Создание таблицы words
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS words (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    original TEXT NOT NULL,
                    translation TEXT NOT NULL,
                    language TEXT NOT NULL,
                    example TEXT,
                    pronunciation TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')

            # Создание таблицы статистики
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS statistics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    word_id INTEGER NOT NULL,
                    known BOOLEAN DEFAULT 0,
                    last_review TIMESTAMP,
                    review_count INTEGER DEFAULT 0,
                    FOREIGN KEY (word_id) REFERENCES words(id)
                )
            ''')

            self.conn.commit() # Фиксация изменений
        except sqlite3.Error as e:
            print(f"Ошибка инициализации базы данных: {e}")
            raise

    def add_word(self, original, translation, language, example=None, pronunciation=None):
        """Добавление нового слова с произношением"""
        try:
            cursor = self.conn.cursor()

            # Вставка нового слова в таблицу words
            cursor.execute('''
                INSERT INTO words (original, translation, language, example, pronunciation)
                VALUES (?, ?, ?, ?, ?)
            ''', (original, translation, language, example, pronunciation))

            word_id = cursor.lastrowid # Получение ID добавленного слова

            # Добавляем запись в статистику
            cursor.execute('''
                INSERT INTO statistics (word_id)
                VALUES (?)
            ''', (word_id,))

            self.conn.commit() # Фиксация изменений
            return word_id # Возврат ID добавленного слова
        except sqlite3.Error as e:
            print(f"Ошибка добавления слова: {e}")
            raise

    def get_words(self, language=None):
        """Получение списка слов"""
        try:
            cursor = self.conn.cursor()

            # Получение слов для конкретного языка в случайном порядке
            if language:
                cursor.execute('''
                    SELECT w.id, w.original, w.translation, w.language, w.example
                    FROM words w
                    WHERE w.language = ?
                    ORDER BY RANDOM()
                ''', (language,))

            # Получение всех слов в случайном порядке
            else:
                cursor.execute('''
                    SELECT w.id, w.original, w.translation, w.language, w.example
                    FROM words w
                    ORDER BY RANDOM()
                ''')

            return cursor.fetchall()
        except sqlite3.Error as e:
            print(f"Ошибка получения слов: {e}")
            return []

    def update_statistic(self, word_id, known):
        """Обновление статистики для слова"""
        try:
            cursor = self.conn.cursor()
            cursor.execute('''
                UPDATE statistics
                SET known = ?,
                    last_review = ?,
                    review_count = review_count + 1
                WHERE word_id = ?
            ''', (known, datetime.now(), word_id))

            self.conn.commit()
        except sqlite3.Error as e:
            print(f"Ошибка обновления статистики: {e}")
            raise

    def get_statistics(self):
        """Получение статистики"""
        try:
            cursor = self.conn.cursor()
            cursor.execute('''
                SELECT known FROM statistics
            ''')
            return cursor.fetchall()
        except sqlite3.Error as e:
            print(f"Ошибка получения статистики: {e}")
            return []

    def import_from_csv(self, file_path, language):
        """Импорт слов из CSV файла"""
        try:
            import csv
            cursor = self.conn.cursor()

            with open(file_path, 'r', encoding='utf-8') as f:
                reader = csv.reader(f)
                for row in reader:
                    if len(row) >= 2:
                        cursor.execute('''
                            INSERT INTO words (original, translation, language, example)
                            VALUES (?, ?, ?, ?)
                        ''', (row[0], row[1], language, row[2] if len(row) > 2 else None))

            self.conn.commit()
        except Exception as e:
            print(f"Ошибка импорта из CSV: {e}")
            raise

    def close(self):
        """Закрытие соединения с базой данных"""
        if self.conn:
            self.conn.close()