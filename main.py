import sys
import os
from PyQt5 import QtWidgets, uic, QtCore, QtGui
from PyQt5.QtWidgets import QFileDialog, QMessageBox, QInputDialog
from database import DatabaseManager
from gtts import gTTS
import pygame
import tempfile


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        uic.loadUi("ui/main_window.ui", self)

        # Инициализация pygame mixer
        pygame.mixer.init()

        # Создание объекта для работы с базой данных
        try:
            self.db = DatabaseManager()
        except Exception as e:
            QMessageBox.critical(self, "Ошибка базы данных",
                                 f"Не удалось подключиться к базе данных: {str(e)}")
            self.db = None

        #  Дополнительная инициализация аудио системы
        try:
            pygame.mixer.init(frequency=22050, size=-16, channels=2, buffer=4096)
        except pygame.error as e:
            QMessageBox.warning(self, "Ошибка аудио", f"Не удалось инициализировать аудиосистему: {e}")

        # Инициализация переменных состояния
        self.current_word = None # Текущее слово
        self.words = [] # Список всех слов
        self.current_index = 0 # Текущий индекс в списке слов
        self.is_flipped = False # Состояние карточки (перевернута/нет)
        self.temp_files = []  # Временные файлы для произношения

        self.setup_ui() # Настройка интерфейса
        self.load_words() # Загрузка слов из БД
        self.setup_shortcuts() # Настройка горячих клавиш

    def setup_ui(self):
        """Настройка пользовательского интерфейса"""
        self.setWindowTitle("Языковые карточки")

        # # Настройка выравнивания текста в виджетах
        self.word_label.setAlignment(QtCore.Qt.AlignCenter)
        self.translation_label.setAlignment(QtCore.Qt.AlignCenter)
        self.translation_label.hide() # Скрытие перевода по умолчанию

        # Настройка прогресса
        self.progress_bar.setValue(0)

        # Подключение кнопок
        self.add_btn.clicked.connect(self.show_add_word_dialog)
        self.flip_btn.clicked.connect(self.flip_card)
        self.next_btn.clicked.connect(self.next_card)
        self.prev_btn.clicked.connect(self.prev_card)
        self.know_btn.clicked.connect(lambda: self.mark_card(True))
        self.dont_know_btn.clicked.connect(lambda: self.mark_card(False))
        self.pronounce_btn.clicked.connect(self.pronounce_word)

        # Настройка выпадающего списка языков
        self.language_combo.addItem("Английский", "english")
        self.language_combo.addItem("Тайский", "thai")
        self.language_combo.currentIndexChanged.connect(self.language_changed)

    def load_words(self, language=None):
        """Загрузка слов из базы данных"""
        if not self.db:
            self.word_label.setText("Ошибка базы данных")
            self.translation_label.clear()
            return

        # Получение слов из БД (всех или для конкретного языка)
        self.words = self.db.get_words(language)
        self.current_index = 0
        self.update_progress()

        if self.words:
            self.show_word()
        else:
            self.word_label.setText("Нет слов для изучения")
            self.translation_label.clear()

    def show_word(self):
        """Отображение текущего слова"""
        if not self.words:
            return

        # Установка текущего слова
        self.current_word = self.words[self.current_index]
        self.word_label.setText(self.current_word[1])  # Оригинальное слово
        self.translation_label.setText(self.current_word[2])  # Перевод

        # Отображение примера использования, если он есть
        if self.current_word[4]:  # example
            self.example_label.setText(f"Пример: {self.current_word[4]}")
        else:
            self.example_label.clear()

        # Скрытие перевода и сброс состояния карточки
        self.translation_label.hide()
        self.is_flipped = False

    def flip_card(self):
        """Переворот карточки (показ/скрытие перевода)"""
        if not self.words:
            return

        if self.is_flipped:
            self.translation_label.hide()
            self.word_label.show()
        else:
            self.word_label.hide()
            self.translation_label.show()

        self.is_flipped = not self.is_flipped # Изменение состояния

    def next_card(self):
        """Переход к следующей карточке"""
        if not self.words:
            return

        # Циклический переход по списку слов
        self.current_index = (self.current_index + 1) % len(self.words)
        self.show_word()

    def prev_card(self):
        """Переход к предыдущей карточке"""
        if not self.words:
            return

        self.current_index = (self.current_index - 1) % len(self.words)
        self.show_word()

    def mark_card(self, known):
        """Пометка карточки как известной/неизвестной"""
        if not self.current_word or not self.db:
            return

        try:
            # Обновление статистики в БД
            self.db.update_statistic(self.current_word[0], known)
            self.next_card() # Переход к следующей карточке
            self.update_progress() # Обновление прогресса
        except Exception as e:
            QMessageBox.warning(self, "Ошибка", f"Не удалось обновить статистику: {str(e)}")

    def pronounce_word(self):
        """Произносит слово с использованием прикрепленного MP3 или gTTS"""
        if not self.current_word or len(self.current_word) < 2:
            QMessageBox.warning(self, "Ошибка", "Нет текущего слова или некорректные данные")
            return

        try:
            # Останавливаем предыдущее воспроизведение
            pygame.mixer.music.stop()

            # 1. Проверяем наличие MP3 (индекс 5, если есть)
            pronunciation_path = None
            if len(self.current_word) > 5:  # Проверяем, есть ли поле pronunciation
                pronunciation_path = self.current_word[5]

                if pronunciation_path and os.path.exists(pronunciation_path):
                    try:
                        pygame.mixer.music.load(pronunciation_path)
                        pygame.mixer.music.play()
                        return
                    except pygame.error as e:
                        print(f"Ошибка воспроизведения MP3: {e}")

            # 2. Используем gTTS как запасной вариант
            word_text = self.current_word[1]  # Оригинальный текст
            # Определение языка для произношения
            language = self.current_word[3] if len(self.current_word) > 3 else 'english'  # language с fallback

            lang_map = {
                'english': 'en',
                'thai': 'th',
            }
            lang_code = lang_map.get(language.lower(), 'en')  # По умолчанию английский

            try:
                # Создание временного файла для аудио
                with tempfile.NamedTemporaryFile(suffix='.mp3', delete=False) as temp_file:
                    temp_path = temp_file.name

                # Генерация аудио с помощью gTTS
                tts = gTTS(text=word_text, lang=lang_code)
                tts.save(temp_path)

                # Воспроизведение аудио
                pygame.mixer.music.load(temp_path)
                pygame.mixer.music.play()

                # Сохранение пути для последующего удаления
                self.temp_files.append(temp_path)

            except Exception as e:
                QMessageBox.warning(self, "Ошибка TTS", f"Не удалось сгенерировать произношение: {str(e)}")

        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Ошибка воспроизведения: {str(e)}")

    def update_progress(self):
        """Обновление прогресс-бара на основе статистики"""
        if not self.db:
            self.progress_bar.setValue(0)
            return

        # Получение статистики из БД
        stats = self.db.get_statistics()
        if not stats:
            self.progress_bar.setValue(0)
            return

        # Расчет прогресса (процент известных слов)
        known_count = sum(1 for stat in stats if stat[0])
        total = len(stats)
        progress = int((known_count / total) * 100) if total > 0 else 0
        self.progress_bar.setValue(progress)

    def language_changed(self):
        """Обработчик изменения выбранного языка"""
        language = self.language_combo.currentData()
        self.load_words(language)

    def show_add_word_dialog(self):
        """Показ диалога добавления нового слова"""
        if not self.db:
            QMessageBox.warning(self, "Ошибка", "База данных недоступна")
            return

        try:
            dialog = AddWordDialog(self)
            if dialog.exec_() == QtWidgets.QDialog.Accepted:
                word_data = dialog.get_word_data()

                # Проверка обязательных полей
                if not word_data['original'] or not word_data['translation']:
                    QMessageBox.warning(self, "Ошибка", "Поля 'Слово' и 'Перевод' обязательны для заполнения")
                    return

                # Добавление слова в БД
                word_id = self.db.add_word(**word_data)
                if word_id:
                    self.load_words()
                    QMessageBox.information(self, "Успех", "Слово успешно добавлено!")
                else:
                    QMessageBox.critical(self, "Ошибка", "Не удалось добавить слово")
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Произошла ошибка: {str(e)}")

    def setup_shortcuts(self):
        """Настройка горячих клавиш"""
        QtWidgets.QShortcut(QtCore.Qt.Key_Space, self, self.flip_card)
        QtWidgets.QShortcut(QtCore.Qt.Key_Right, self, self.next_card)
        QtWidgets.QShortcut(QtCore.Qt.Key_Left, self, self.prev_card)
        QtWidgets.QShortcut(QtCore.Qt.Key_1, self, lambda: self.mark_card(True))
        QtWidgets.QShortcut(QtCore.Qt.Key_2, self, lambda: self.mark_card(False))
        QtWidgets.QShortcut(QtCore.Qt.Key_R, self, self.pronounce_word)
        QtWidgets.QShortcut(QtCore.Qt.Key_Escape, self, self.close)
        QtWidgets.QShortcut(QtGui.QKeySequence("Ctrl+N"), self, self.show_add_word_dialog)

    def closeEvent(self, event):
        # Остановка и очистка аудио системы
        try:
            if pygame.mixer.get_init():
                pygame.mixer.music.stop()
                pygame.mixer.quit()
        except:
            pass

        # Удаление временных аудио файлов
        for temp_file in self.temp_files:
            try:
                if os.path.exists(temp_file):
                    os.unlink(temp_file)
            except:
                pass

        event.accept() # Подтверждение закрытия окна


class AddWordDialog(QtWidgets.QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        uic.loadUi("ui/add_word.ui", self) # Загрузка интерфейса диалога
        self.setup_ui()
        self.pronunciation_path = None # Путь к файлу произношения

    def setup_ui(self):
        """Настройка интерфейса диалога добавления слова"""
        self.setWindowTitle("Добавить новое слово")
        self.language_combo.addItem("Английский", "english")
        self.language_combo.addItem("Тайский", "thai")

        # Подключение кнопки выбора файла произношения
        self.browse_btn.clicked.connect(self.browse_pronunciation)

        # Подключение кнопок OK и Cancel
        self.button_box.accepted.connect(self.validate_input)
        self.button_box.rejected.connect(self.reject)

    def browse_pronunciation(self):
        """Открытие диалога выбора MP3 файла с произношением"""
        file_dialog = QFileDialog(self)
        file_dialog.setNameFilter("MP3 Files (*.mp3)")
        file_dialog.setFileMode(QFileDialog.ExistingFile)

        if file_dialog.exec_():
            selected = file_dialog.selectedFiles()
            if selected:
                # Отображение имени файла в интерфейсе
                self.pronunciation_path = selected[0]
                self.pronunciation_edit.setText(os.path.basename(self.pronunciation_path))

    def validate_input(self):
        """Проверка введенных данных"""
        if not self.original_edit.text().strip():
            QMessageBox.warning(self, "Ошибка", "Введите слово")
            return

        if not self.translation_edit.text().strip():
            QMessageBox.warning(self, "Ошибка", "Введите перевод")
            return

        self.accept() # Закрытие диалога с результатом OK

    def get_word_data(self):
        """Получение данных о слове из формы"""
        data = {
            "original": self.original_edit.text(),
            "translation": self.translation_edit.text(),
            "language": self.language_combo.currentData(),
            "example": self.example_edit.toPlainText(),
            "pronunciation": None
        }

        # Обработка файла произношения, если он выбран
        if self.pronunciation_path:
            try:
                media_dir = "media/pronunciation"
                os.makedirs(media_dir, exist_ok=True) # Создание директории, если не существует

                # Генерация уникального имени файла
                base_name = f"{data['language']}_{data['original']}.mp3"
                dest_path = os.path.join(media_dir, base_name)

                # Копирование файла в медиа-папку
                import shutil
                shutil.copy2(self.pronunciation_path, dest_path)
                data["pronunciation"] = dest_path # Сохранение пути в данных
            except Exception as e:
                print(f"Ошибка копирования MP3 файла: {e}")

        return data

    def load_words(self, language=None):
        self.words = self.db.get_words(language)
        if self.words:
            print(f"Загружено слов: {len(self.words)}, полей: {len(self.words[0])}")  # Отладочный вывод

if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)
    app.setStyle("Fusion")  # Установка стиля интерфейса

    try:
        window = MainWindow()
        window.show()
        sys.exit(app.exec_())  # Запуск главного цикла приложения
    except Exception as e:
        QMessageBox.critical(None, "Ошибка", f"Не удалось запустить приложение: {str(e)}")
        sys.exit(1)