import sys
import pymysql
import mysql.connector
import time
import cv2
import numpy as np
import torch
from ultralytics import YOLO
from basket_utils import score, detect_down, detect_up, in_hoop_region, clean_hoop_pos, clean_ball_pos, get_device
from PyQt5.QtWidgets import QFrame
from PyQt5.QtGui import QImage, QPixmap, QFont, QColor
from PyQt5.QtCore import Qt, QDateTime, QDate, QTimer, QSize
from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, 
    QPushButton, QLabel, QListWidget, 
    QLineEdit, QMessageBox, QHBoxLayout, QSizePolicy, QDateEdit, QCheckBox,
    QSlider, QDialog, QListWidgetItem, QGraphicsDropShadowEffect, QToolButton,
    QScrollArea, QSpacerItem, QStyle
)
from werkzeug.security import generate_password_hash, check_password_hash


db_user = 'root'
db_pass = 'root'


def wait_for_mysql(user, password, host='localhost', port=3307, db='basketball_db', retries=10):
    for i in range(retries):
        try:
            connection = pymysql.connect(
                host=host,
                port=port,
                user=user,
                password=password,
                db=db,
                charset='utf8mb4',
                cursorclass=pymysql.cursors.DictCursor
            )
            print("✅ MySQL готов")
            connection.close()
            return True
        except pymysql.err.OperationalError as e:
            print(f"🔄 Попытка {i+1}: MySQL ещё не готов ({e})")
            time.sleep(2)
    return False


if not wait_for_mysql(db_user, db_pass):
    print("❌ Не удалось дождаться MySQL")
    exit(1)

def hash_password(password: str) -> str:
    """Хэширование пароля."""
    return generate_password_hash(password)

def check_password(hashed_password: str, plain_password: str) -> bool:
    """Проверка пароля с хэшем."""
    return check_password_hash(hashed_password, plain_password)

def create_admin_user_if_not_exists(db_user, db_pass):
    """Создание админа, если его нет в базе данных."""
    try:
        
        connection = pymysql.connect(
            host='localhost',
            user=db_user,
            port=3307,
            password=db_pass,
            db='basketball_db',
            charset='utf8mb4',
            cursorclass=pymysql.cursors.DictCursor
        )

        with connection.cursor() as cursor:
            
            cursor.execute("SELECT * FROM users WHERE username = 'admin'")
            admin_user = cursor.fetchone()

            if not admin_user:
                
                hashed_password = hash_password("12345678") 
                cursor.execute("INSERT INTO users (username, password, role) VALUES (%s, %s, %s)", 
                               ('admin', hashed_password, 'admin'))
                connection.commit()
                print("Админ-пользователь был успешно создан.")
            else:
                print("Админ-пользователь уже существует.")

        connection.close()

    except Exception as e:
        print(f"Ошибка при добавлении админ-пользователя: {e}")


create_admin_user_if_not_exists(db_user, db_pass)


def get_matches(is_past, db_user, db_pass):
    try:
        connection = pymysql.connect(
            host='localhost',
            user=db_user,
            port=3307,
            password=db_pass,
            db='basketball_db',
            charset='utf8mb4',
            cursorclass=pymysql.cursors.DictCursor
        )

        with connection.cursor() as cursor:
            if is_past:
                cursor.execute("SELECT * FROM matches WHERE match_time < NOW() ORDER BY match_time DESC")
            else:
                cursor.execute("SELECT * FROM matches WHERE match_time >= NOW() ORDER BY match_time ASC")
            matches = cursor.fetchall()

        connection.close()
        return matches
    except Exception as e:
        print(f"Ошибка при получении матчей: {e}")
        return []

def add_match(team1, team2, match_time, db_user, db_pass):
    try:
        connection = pymysql.connect(
            host='localhost',
            user=db_user,
            port=3307,
            password=db_pass,
            db='basketball_db',
            charset='utf8mb4',
            cursorclass=pymysql.cursors.DictCursor
        )
        with connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO matches (team1, team2, match_time) VALUES (%s, %s, %s)",
                (team1, team2, match_time)
            )
            connection.commit()
        connection.close()
    except Exception as e:
        print("Ошибка при добавлении матча:", e)


class LoginWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.is_fullscreen = True

        self.setWindowTitle("Вход в систему")
        self.setStyleSheet("background-color: #121212; font-family: 'Segoe UI', Arial; color: #ffffff;")
        self.showFullScreen()

        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)

        self.setup_title_bar()
        self.setup_login_card()

    def setup_title_bar(self):
        title_bar = QHBoxLayout()
        title_bar.setContentsMargins(0, 0, 16, 6)
        title_bar.setSpacing(10)
        title_bar.addStretch()

        btn_minimize = QToolButton()
        btn_minimize.setText("—")
        btn_minimize.setStyleSheet(self.get_window_button_style())
        btn_minimize.clicked.connect(self.showMinimized)

        self.btn_toggle_fullscreen = QToolButton()
        self.btn_toggle_fullscreen.setText("🗖")
        self.btn_toggle_fullscreen.setStyleSheet(self.get_window_button_style())
        self.btn_toggle_fullscreen.clicked.connect(self.toggle_fullscreen)

        btn_close = QToolButton()
        btn_close.setText("✕")
        btn_close.setStyleSheet(self.get_window_button_style(close=True))
        btn_close.clicked.connect(self.close)

        title_bar.addWidget(btn_minimize)
        title_bar.addWidget(self.btn_toggle_fullscreen)
        title_bar.addWidget(btn_close)

        self.main_layout.addLayout(title_bar)

    def setup_login_card(self):
        outer_layout = QHBoxLayout()
        outer_layout.setContentsMargins(20, 20, 20, 20)
        outer_layout.setSpacing(0)
        outer_layout.addStretch()

        self.card = QFrame()
        self.card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.card.setStyleSheet("QFrame { background-color: #1e1e1e; border-radius: 16px; }")

        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(40)
        shadow.setOffset(0, 0)
        shadow.setColor(QColor(0, 0, 0, 180))
        self.card.setGraphicsEffect(shadow)

        card_layout = QVBoxLayout(self.card)
        card_layout.setSpacing(24)
        card_layout.setContentsMargins(60, 40, 60, 40)

        header = QLabel("Вход в систему")
        header.setFont(QFont("Segoe UI", 26, QFont.Bold))
        header.setAlignment(Qt.AlignCenter)
        card_layout.addWidget(header)

        
        username_widget, self.username_input = self.create_labeled_input("Логин:")
        card_layout.addWidget(username_widget)

        
        password_widget, self.password_input = self.create_labeled_input("Пароль:", password=True)
        card_layout.addWidget(password_widget)

        self.login_button = QPushButton("Войти")
        self.login_button.setStyleSheet(self.get_button_style())
        self.login_button.setFont(QFont("Segoe UI", 14, QFont.Bold))
        self.login_button.clicked.connect(self.try_login)
        card_layout.addWidget(self.login_button)

        self.register_button = QPushButton("Зарегистрироваться")
        self.register_button.setStyleSheet(self.get_button_style(secondary=True))
        self.register_button.setFont(QFont("Segoe UI", 14))
        self.register_button.clicked.connect(self.open_registration_window)
        card_layout.addWidget(self.register_button)

        outer_layout.addWidget(self.card)
        outer_layout.addStretch()

        self.main_layout.addLayout(outer_layout)

    def toggle_fullscreen(self):
        if self.is_fullscreen:
            self.showNormal()
            self.is_fullscreen = False
            self.btn_toggle_fullscreen.setText("🗖")
        else:
            self.showFullScreen()
            self.is_fullscreen = True
            self.btn_toggle_fullscreen.setText("🗗")

    def create_labeled_input(self, label_text, password=False):
        wrapper = QVBoxLayout()
        wrapper.setSpacing(1)
        wrapper.setContentsMargins(0, 0, 0, 0)
        label = QLabel(label_text)
        label.setFont(QFont("Segoe UI", 15))
        label.setStyleSheet("margin: 0px; padding: 0px;")  
        wrapper.addWidget(label)

        input_field = QLineEdit()
        input_field.setStyleSheet(self.get_input_style())
        input_field.setFont(QFont("Segoe UI", 15))
        if password:
            input_field.setEchoMode(QLineEdit.Password)
        wrapper.addWidget(input_field)

        container = QFrame()
        container.setLayout(wrapper)
        
        return container, input_field

    def get_window_button_style(self, close=False):
        return f"""
            QToolButton {{
                border: none;
                background-color: {"#333" if not close else "#922"};
                color: white;
                font-size: 18px;
                padding: 6px 10px;
                border-radius: 4px;
            }}
            QToolButton:hover {{
                background-color: {"#555" if not close else "#c33"};
            }}
        """

    def get_input_style(self):
        return """
            QLineEdit {
                background-color: #2b2b2e;
                border: 2px solid #444;
                border-radius: 10px;
                padding: 12px;
                color: #ffffff;
            }
            QLineEdit:focus {
                border-color: #bb86fc;
            }
        """

    def get_button_style(self, secondary=False):
        if secondary:
            return """
                QPushButton {
                    background-color: #3a3a3a;
                    color: #ffffff;
                    border-radius: 10px;
                    padding: 12px;
                }
                QPushButton:hover {
                    background-color: #505050;
                }
            """
        return """
            QPushButton {
                background-color: #bb86fc;
                color: black;
                border-radius: 10px;
                padding: 12px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #9b68e4;
            }
        """

    def try_login(self):
        username = self.username_input.text()
        password = self.password_input.text()
        if username and password:
            user = self.authenticate_user(username, password)
            if user:
                self.open_main_window(user['role'])
            else:
                QMessageBox.warning(self, "Ошибка", "Неверный логин или пароль.")
        else:
            QMessageBox.warning(self, "Ошибка", "Пожалуйста, заполните оба поля.")

    def authenticate_user(self, username, password):
        """Метод для аутентификации пользователя"""
        try:
            
            connection = pymysql.connect(
                host='localhost',
                user=db_user,
                port=3307,
                password=db_pass,
                db='basketball_db',
                charset='utf8mb4',
                cursorclass=pymysql.cursors.DictCursor
            )

            with connection.cursor() as cursor:
                cursor.execute("SELECT * FROM users WHERE username = %s", (username,))
                user = cursor.fetchone()

            connection.close()

            if user and check_password(user['password'], password):  
                return user  
            else:
                return None

        except Exception as e:
            print(f"Ошибка при подключении к базе данных: {e}")
            return None

    def open_main_window(self, role):
        self.main_window = MainWindow(db_user, db_pass, role=role)
        self.main_window.show()
        self.close()

    def open_registration_window(self):
        self.registration_window = RegistrationWindow()
        self.registration_window.show()
        self.close()



class RegistrationWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Регистрация")
        self.setStyleSheet("background-color: #121212; font-family: 'Segoe UI', Arial; color: #ffffff;")
        self.showFullScreen()

        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)

        self.setup_title_bar()
        self.setup_registration_card()

    def setup_title_bar(self):
        title_bar = QHBoxLayout()
        title_bar.setContentsMargins(0, 0, 16, 6)
        title_bar.setSpacing(10)
        title_bar.addStretch()

        btn_close = QToolButton()
        btn_close.setText("✕")
        btn_close.setStyleSheet(self.get_window_button_style(close=True))
        btn_close.clicked.connect(self.close)

        title_bar.addWidget(btn_close)
        self.main_layout.addLayout(title_bar)

    def setup_registration_card(self):
        outer_layout = QHBoxLayout()
        outer_layout.setContentsMargins(20, 20, 20, 20)
        outer_layout.addStretch()

        self.card = QFrame()
        self.card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.card.setStyleSheet("QFrame { background-color: #1e1e1e; border-radius: 16px; }")

        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(40)
        shadow.setOffset(0, 0)
        shadow.setColor(QColor(0, 0, 0, 180))
        self.card.setGraphicsEffect(shadow)

        card_layout = QVBoxLayout(self.card)
        card_layout.setSpacing(20)
        card_layout.setContentsMargins(60, 40, 60, 40)

        header = QLabel("Регистрация")
        header.setFont(QFont("Segoe UI", 26, QFont.Bold))
        header.setAlignment(Qt.AlignCenter)
        card_layout.addWidget(header)

        
        username_widget, self.username_input = self.create_labeled_input("Логин:")
        card_layout.addWidget(username_widget)

        
        password_widget, self.password_input = self.create_labeled_input("Пароль:", password=True)
        card_layout.addWidget(password_widget)

       
        self.register_button = QPushButton("Зарегистрироваться")
        self.register_button.setStyleSheet(self.get_button_style())
        self.register_button.setFont(QFont("Segoe UI", 14, QFont.Bold))
        self.register_button.clicked.connect(self.register_user)
        card_layout.addWidget(self.register_button)

        
        self.back_button = QPushButton("Назад")
        self.back_button.setStyleSheet(self.get_button_style(secondary=True))
        self.back_button.setFont(QFont("Segoe UI", 14))
        self.back_button.clicked.connect(self.go_back)
        card_layout.addWidget(self.back_button)

        outer_layout.addWidget(self.card)
        outer_layout.addStretch()
        self.main_layout.addLayout(outer_layout)

    def create_labeled_input(self, label_text, password=False):
        wrapper = QVBoxLayout()
        wrapper.setSpacing(2)
        wrapper.setContentsMargins(0, 0, 0, 0)

        label = QLabel(label_text)
        label.setFont(QFont("Segoe UI", 15))
        label.setStyleSheet("margin: 0px; padding: 0px;")
        wrapper.addWidget(label)

        input_field = QLineEdit()
        input_field.setStyleSheet(self.get_input_style())
        input_field.setFont(QFont("Segoe UI", 15))
        if password:
            input_field.setEchoMode(QLineEdit.Password)
        wrapper.addWidget(input_field)

        container = QFrame()
        container.setLayout(wrapper)
        return container, input_field

    def get_input_style(self):
        return """
            QLineEdit {
                background-color: #2b2b2e;
                border: 2px solid #444;
                border-radius: 10px;
                padding: 12px;
                color: #ffffff;
            }
            QLineEdit:focus {
                border-color: #bb86fc;
            }
        """

    def get_button_style(self, secondary=False):
        if secondary:
            return """
                QPushButton {
                    background-color: #3a3a3a;
                    color: #ffffff;
                    border-radius: 10px;
                    padding: 12px;
                }
                QPushButton:hover {
                    background-color: #505050;
                }
            """
        return """
            QPushButton {
                background-color: #bb86fc;
                color: black;
                border-radius: 10px;
                padding: 12px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #9b68e4;
            }
        """

    def get_window_button_style(self, close=False):
        return f"""
            QToolButton {{
                border: none;
                background-color: {"#333" if not close else "#922"};
                color: white;
                font-size: 18px;
                padding: 6px 10px;
                border-radius: 4px;
            }}
            QToolButton:hover {{
                background-color: {"#555" if not close else "#c33"};
            }}
        """

    def go_back(self):
        self.login_window = LoginWindow()
        self.login_window.show()
        self.close()

    def register_user(self):
        username = self.username_input.text()
        password = self.password_input.text()

        if not username or not password:
            QMessageBox.warning(self, "Ошибка", "Пожалуйста, заполните все поля.")
            return

        hashed_password = hash_password(password)

        try:
            connection = pymysql.connect(
                host='localhost',
                user=db_user,
                port=3307,
                password=db_pass,
                db='basketball_db',
                charset='utf8mb4',
                cursorclass=pymysql.cursors.DictCursor
            )
            with connection.cursor() as cursor:
                cursor.execute("INSERT INTO users (username, password) VALUES (%s, %s)", (username, hashed_password))
                connection.commit()
            connection.close()

            QMessageBox.information(self, "Успех", "Вы успешно зарегистрировались!")
            self.login_window = LoginWindow()
            self.login_window.show()
            self.close()

        except Exception as e:
            QMessageBox.warning(self, "Ошибка", f"Не удалось зарегистрировать пользователя: {e}")

class MainWindow(QWidget):
    def __init__(self, db_user, db_pass, role):
        super().__init__()
        self.db_user = db_user
        self.db_pass = db_pass
        self.role = role

        self.setWindowTitle("Панель управления")
        self.setStyleSheet("background-color: #121212; font-family: 'Segoe UI', Arial; color: #ffffff;")
        self.showFullScreen()

        self.is_fullscreen = True

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        self.setup_title_bar(main_layout)
        self.setup_main_card(main_layout)

    def setup_title_bar(self, parent_layout):
        title_bar = QHBoxLayout()
        title_bar.setContentsMargins(0, 0, 16, 6)
        title_bar.setSpacing(10)
        title_bar.addStretch()

        btn_minimize = QToolButton()
        btn_minimize.setText("—")
        btn_minimize.setStyleSheet(self.get_window_button_style())
        btn_minimize.clicked.connect(self.showMinimized)

        self.btn_toggle_fullscreen = QToolButton()
        self.btn_toggle_fullscreen.setText("🗖")
        self.btn_toggle_fullscreen.setStyleSheet(self.get_window_button_style())
        self.btn_toggle_fullscreen.clicked.connect(self.toggle_fullscreen)

        btn_close = QToolButton()
        btn_close.setText("✕")
        btn_close.setStyleSheet(self.get_window_button_style(close=True))
        btn_close.clicked.connect(self.logout)

        title_bar.addWidget(btn_minimize)
        title_bar.addWidget(self.btn_toggle_fullscreen)
        title_bar.addWidget(btn_close)

        parent_layout.addLayout(title_bar)

    def setup_main_card(self, parent_layout):
        outer_layout = QVBoxLayout()
        outer_layout.setAlignment(Qt.AlignCenter)

        self.card = QFrame()
        self.card.setFixedWidth(420)
        self.card.setStyleSheet("QFrame { background-color: #1e1e1e; border-radius: 16px; }")

        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(40)
        shadow.setOffset(0, 0)
        shadow.setColor(QColor(0, 0, 0, 180))
        self.card.setGraphicsEffect(shadow)

        card_layout = QVBoxLayout(self.card)
        card_layout.setContentsMargins(40, 40, 40, 40)
        card_layout.setSpacing(30)

        title = QLabel("Меню")
        title.setFont(QFont("Segoe UI", 26, QFont.Bold))
        title.setAlignment(Qt.AlignCenter)
        card_layout.addWidget(title)

        
        button_container = QVBoxLayout()
        button_container.setSpacing(20)
        button_container.setAlignment(Qt.AlignCenter)

        self.matches_button = QPushButton("Список матчей")
        self.matches_button.setStyleSheet(self.get_button_style())
        self.matches_button.setFont(QFont("Segoe UI", 14))
        self.matches_button.setFixedWidth(280)
        self.matches_button.clicked.connect(self.show_matches)
        button_container.addWidget(self.matches_button, alignment=Qt.AlignCenter)

        self.stats_button = QPushButton("Статистика матчей")
        self.stats_button.setStyleSheet(self.get_button_style())
        self.stats_button.setFont(QFont("Segoe UI", 14))
        self.stats_button.setFixedWidth(280)
        self.stats_button.clicked.connect(self.show_stats)
        button_container.addWidget(self.stats_button, alignment=Qt.AlignCenter)

        self.add_match_button = QPushButton("Добавить новый матч")
        self.add_match_button.setStyleSheet(self.get_button_style())
        self.add_match_button.setFont(QFont("Segoe UI", 14))
        self.add_match_button.setFixedWidth(280)
        self.add_match_button.clicked.connect(self.show_add_match)
        button_container.addWidget(self.add_match_button, alignment=Qt.AlignCenter)

        
        if self.role == "user":
            self.add_match_button.hide()
            self.stats_button.hide()

        card_layout.addLayout(button_container)
        outer_layout.addWidget(self.card)
        parent_layout.addLayout(outer_layout)

    def toggle_fullscreen(self):
        if self.is_fullscreen:
            self.showNormal()
            self.btn_toggle_fullscreen.setText("🗖")
        else:
            self.showFullScreen()
            self.btn_toggle_fullscreen.setText("🗗")
        self.is_fullscreen = not self.is_fullscreen

    def get_button_style(self):
        return """
            QPushButton {
                background-color: #bb86fc;
                color: black;
                border-radius: 10px;
                padding: 12px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #9b68e4;
            }
        """

    def get_window_button_style(self, close=False):
        return f"""
            QToolButton {{
                border: none;
                background-color: {"#333" if not close else "#922"};
                color: white;
                font-size: 18px;
                padding: 6px 10px;
                border-radius: 4px;
            }}
            QToolButton:hover {{
                background-color: {"#555" if not close else "#c33"};
            }}
        """

    def show_matches(self):
        self.match_window = MatchesWindow(self.db_user, self.db_pass, self.role)
        self.match_window.show()

    def show_stats(self):
        self.stats_window = StatsWindow(self.db_user, self.db_pass)
        self.stats_window.show()

    def show_add_match(self):
        self.add_match_window = AddMatchWindow(self.db_user, self.db_pass)
        self.add_match_window.show()

    def logout(self):
        self.close()
        self.login_window = LoginWindow()
        self.login_window.show()


class MatchesWindow(QWidget):
    def __init__(self, db_user, db_pass, role):
        super().__init__()
        self.db_user = db_user
        self.db_pass = db_pass
        self.role = role
        self.is_fullscreen = True

        self.setWindowTitle("Список матчей")
        self.setStyleSheet("background-color: #121212; font-family: 'Segoe UI', Arial; color: #ffffff;")
        self.showFullScreen()

        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)

        self.setup_title_bar()
        self.setup_matches_card()

    def setup_title_bar(self):
        title_bar = QHBoxLayout()
        title_bar.setContentsMargins(0, 0, 16, 6)
        title_bar.setSpacing(10)
        title_bar.addStretch()

        btn_minimize = QToolButton()
        btn_minimize.setText("—")
        btn_minimize.setStyleSheet(self.get_window_button_style())
        btn_minimize.clicked.connect(self.showMinimized)

        self.btn_toggle_fullscreen = QToolButton()
        self.btn_toggle_fullscreen.setText("🗖")
        self.btn_toggle_fullscreen.setStyleSheet(self.get_window_button_style())
        self.btn_toggle_fullscreen.clicked.connect(self.toggle_fullscreen)

        btn_close = QToolButton()
        btn_close.setText("✕")
        btn_close.setStyleSheet(self.get_window_button_style(close=True))
        btn_close.clicked.connect(self.close)

        title_bar.addWidget(btn_minimize)
        title_bar.addWidget(self.btn_toggle_fullscreen)
        title_bar.addWidget(btn_close)

        self.main_layout.addLayout(title_bar)

    def setup_matches_card(self):
        outer_layout = QHBoxLayout()
        outer_layout.setContentsMargins(20, 20, 20, 20)
        outer_layout.addStretch()

        self.card = QFrame()
        self.card.setStyleSheet("QFrame { background-color: #1e1e1e; border-radius: 16px; }")
        self.card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(40)
        shadow.setOffset(0, 0)
        shadow.setColor(QColor(0, 0, 0, 180))
        self.card.setGraphicsEffect(shadow)

        card_layout = QVBoxLayout(self.card)
        card_layout.setSpacing(24)
        card_layout.setContentsMargins(60, 40, 60, 40)

        header = QLabel("📅 Список матчей")
        header.setFont(QFont("Segoe UI", 26, QFont.Bold))
        header.setAlignment(Qt.AlignCenter)
        card_layout.addWidget(header)

        self.upcoming_label = QLabel("Предстоящие матчи:")
        self.upcoming_label.setFont(QFont("Segoe UI", 18, QFont.Bold))
        self.upcoming_label.setStyleSheet("color: #9bafff;")
        card_layout.addWidget(self.upcoming_label)

        self.upcoming_matches_list = QListWidget(self)
        self.upcoming_matches_list.setStyleSheet(self.get_list_style())
        card_layout.addWidget(self.upcoming_matches_list)

        self.past_label = QLabel("Прошедшие матчи:")
        self.past_label.setFont(QFont("Segoe UI", 18, QFont.Bold))
        self.past_label.setStyleSheet("color: #ffb6c1; margin-top: 20px;")
        card_layout.addWidget(self.past_label)

        self.past_matches_list = QListWidget(self)
        self.past_matches_list.setStyleSheet(self.get_list_style())
        card_layout.addWidget(self.past_matches_list)

        self.delete_button = QPushButton("Удалить матч")
        self.delete_button.setFont(QFont("Segoe UI", 14, QFont.Bold))
        self.delete_button.setStyleSheet(self.get_button_style())
        self.delete_button.clicked.connect(self.delete_match)
        card_layout.addWidget(self.delete_button)

        if self.role.lower() != "admin":
            self.delete_button.hide()

        self.populate_matches(self.upcoming_matches_list, False)
        self.populate_matches(self.past_matches_list, True)

        self.upcoming_matches_list.itemDoubleClicked.connect(lambda item: self.match_clicked(item, False))
        self.past_matches_list.itemDoubleClicked.connect(lambda item: self.match_clicked(item, True))

        outer_layout.addWidget(self.card)
        outer_layout.addStretch()

        self.main_layout.addLayout(outer_layout)

    def toggle_fullscreen(self):
        if self.is_fullscreen:
            self.showNormal()
            self.is_fullscreen = False
            self.btn_toggle_fullscreen.setText("🗖")
        else:
            self.showFullScreen()
            self.is_fullscreen = True
            self.btn_toggle_fullscreen.setText("🗗")

    def get_window_button_style(self, close=False):
        return f"""
            QToolButton {{
                border: none;
                background-color: {"#333" if not close else "#922"};
                color: white;
                font-size: 18px;
                padding: 6px 10px;
                border-radius: 4px;
            }}
            QToolButton:hover {{
                background-color: {"#555" if not close else "#c33"};
            }}
        """

    def get_list_style(self):
        return """
            QListWidget {
                background-color: #2b2b2e;
                border: 2px solid #444;
                border-radius: 10px;
                padding: 10px;
                font-size: 16px;
                color: #ffffff;
            }
            QListWidget::item {
                padding: 10px;
                margin: 5px;
            }
            QListWidget::item:selected {
                background-color: #bb86fc;
                color: #000;
                border-radius: 5px;
            }
        """

    def get_button_style(self):
        return """
            QPushButton {
                background-color: #bb86fc;
                color: black;
                border-radius: 10px;
                padding: 12px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #9b68e4;
            }
        """

    def match_clicked(self, item, is_past):
        match_id = int(item.text().split(":")[0])
        if is_past:
            self.stats_viewer = StatsViewer(match_id, self.db_user, self.db_pass, self.role)
            self.stats_viewer.show()
        else:
            QMessageBox.information(self, "Информация", "Матч ещё не прошёл. Статистика недоступна.")

    def populate_matches(self, list_widget, is_past):
        matches = get_matches(is_past, self.db_user, self.db_pass)
        list_widget.clear()
        for match in matches:
            item = f"{match['id']}: {match['team1']} vs {match['team2']} — {match['match_time'].strftime('%d.%m.%Y %H:%M')}"
            list_widget.addItem(item)

    def delete_match(self):
        selected_item = self.upcoming_matches_list.selectedItems() or self.past_matches_list.selectedItems()
        if not selected_item:
            QMessageBox.warning(self, "Ошибка", "Пожалуйста, выберите матч для удаления.")
            return

        match_id = int(selected_item[0].text().split(":")[0])

        try:
            connection = pymysql.connect(
                host='localhost',
                user=self.db_user,
                port=3307,
                password=self.db_pass,
                db='basketball_db',
                charset='utf8mb4',
                cursorclass=pymysql.cursors.DictCursor
            )
            with connection.cursor() as cursor:
                cursor.execute("DELETE FROM matches WHERE id = %s", (match_id,))
                connection.commit()
            connection.close()

            QMessageBox.information(self, "Успех", f"Матч {match_id} был успешно удалён.")
            self.populate_matches(self.upcoming_matches_list, False)
            self.populate_matches(self.past_matches_list, True)
        except Exception as e:
            QMessageBox.warning(self, "Ошибка", f"Не удалось удалить матч: {e}")


# -------------------------------------
#               Запись в БД

def insert_shot_in_db(match_id, team_name, points):
    conn = None
    cursor = None
    try:
        conn = mysql.connector.connect(
            host="localhost",
            user="root",
            port=3307,
            password="root",
            database="basketball_db"
        )
        cursor = conn.cursor()

        points_int = int(points)

        
        cursor.execute("""
            SELECT id FROM teams WHERE LOWER(TRIM(name)) = LOWER(TRIM(%s))
        """, (team_name,))
        team = cursor.fetchone()
        if not team:
            print(f"[WARNING] Команда с названием '{team_name}' не найдена.")
            return None
        team_id = team[0]

        
        cursor.execute("""
            INSERT INTO events (team_id, match_id, event_type, points)
            VALUES (%s, %s, 'shot', %s)
        """, (team_id, match_id, points_int))

        
        cursor.execute("SELECT team1, team2 FROM matches WHERE id = %s", (match_id,))
        teams = cursor.fetchone()
        if not teams:
            print("[ERROR] Матч не найден в базе.")
            conn.rollback()
            return None
        team1, team2 = teams

        
        cursor.execute("SELECT 1 FROM stats WHERE match_id = %s", (match_id,))
        exists = cursor.fetchone()
        if not exists:
            cursor.execute("""
                INSERT INTO stats (match_id, team1_points, team2_points,
                                   team1_twos, team2_twos, team1_threes, team2_threes)
                VALUES (%s, 0, 0, 0, 0, 0, 0)
            """, (match_id,))

        
        if team_name.lower().strip() == team1.lower().strip():
            cursor.execute("""
                UPDATE stats 
                SET team1_points = team1_points + %s,
                    team1_twos = team1_twos + %s,
                    team1_threes = team1_threes + %s
                WHERE match_id = %s
            """, (points_int, 1 if points_int == 2 else 0, 1 if points_int == 3 else 0, match_id))

        elif team_name.lower().strip() == team2.lower().strip():
            cursor.execute("""
                UPDATE stats 
                SET team2_points = team2_points + %s,
                    team2_twos = team2_twos + %s,
                    team2_threes = team2_threes + %s
                WHERE match_id = %s
            """, (points_int, 1 if points_int == 2 else 0, 1 if points_int == 3 else 0, match_id))

        else:
            print("[WARNING] Команда не принадлежит ни одной из команд матча.")

        conn.commit()
        print(f"[INFO] Бросок команды '{team_name}' ({points_int} очков) записан, очки обновлены.")
        return team_id

    except mysql.connector.Error as err:
        print(f"[ERROR] Ошибка записи в БД: {err}")
        if conn:
            conn.rollback()
        return None

    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


def insert_foul_in_db(match_id, team_name, foul_time=None):
    import mysql.connector
    import datetime
    conn = None
    cursor = None
    try:
        conn = mysql.connector.connect(
            host="localhost",
            user="root",
            port = 3307,
            password="root",
            database="basketball_db"
        )
        cursor = conn.cursor()

        
        cursor.execute("""
            SELECT id FROM teams WHERE LOWER(TRIM(name)) = LOWER(TRIM(%s))
        """, (team_name,))
        team = cursor.fetchone()
        if not team:
            print(f"[WARNING] Команда с названием '{team_name}' не найдена.")
            return None
        team_id = team[0]

        
        cursor.execute("SELECT team1, team2 FROM matches WHERE id = %s", (match_id,))
        teams = cursor.fetchone()
        if not teams:
            print("[ERROR] Матч не найден в базе.")
            conn.rollback()
            return None
        team1, team2 = teams

        
        cursor.execute("SELECT 1 FROM stats WHERE match_id = %s", (match_id,))
        exists = cursor.fetchone()
        if not exists:
            cursor.execute("""
                INSERT INTO stats (match_id, team1_fouls, team2_fouls)
                VALUES (%s, 0, 0)
            """, (match_id,))

        
        if foul_time is None:
            foul_time = datetime.datetime.now()
        cursor.execute("""
            INSERT INTO events (team_id, match_id, event_type, event_time)
            VALUES (%s, %s, 'foul', %s)
        """, (team_id, match_id, foul_time))

        
        if team_name.lower().strip() == team1.lower().strip():
            cursor.execute("""
                UPDATE stats 
                SET team1_fouls = team1_fouls + 1
                WHERE match_id = %s
            """, (match_id,))
        elif team_name.lower().strip() == team2.lower().strip():
            cursor.execute("""
                UPDATE stats 
                SET team2_fouls = team2_fouls + 1
                WHERE match_id = %s
            """, (match_id,))
        else:
            print("[WARNING] Команда не принадлежит ни одной из команд матча.")
            conn.rollback()
            return None

        conn.commit()
        print(f"[INFO] Фол команды '{team_name}' записан, статистика обновлена.")
        return team_id

    except mysql.connector.Error as err:
        print(f"[ERROR] Ошибка записи в БД: {err}")
        if conn:
            conn.rollback()
        return None

    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

#------------------------------------------

class MatchViewer(QWidget):
    def __init__(self, match_id):
        super().__init__()
        self.match_id = match_id

        self.conn = pymysql.connect(
            host='localhost', user=db_user, password=db_pass, db='basketball_db',port=3307,
            charset='utf8mb4', cursorclass=pymysql.cursors.DictCursor
        )

        with self.conn.cursor() as cursor:
            cursor.execute("SELECT video_path, team1, team2 FROM matches WHERE id = %s", (self.match_id,))
            result = cursor.fetchone()
            video_path = result['video_path'] if result else 'model/video_test_8.mp4'
            self.team1 = result['team1']
            self.team2 = result['team2']

        
        self.team_colors = {}
        self.team_colors_history = {self.team1: [], self.team2: []}
        self.max_color_history = 10

        
        self.setWindowTitle("Просмотр матча")
        self.showFullScreen()
        self.is_fullscreen = True

        self.setStyleSheet("""
            background-color: #1c1c1e;
            color: #eaeaea;
            font-family: Arial, sans-serif;
            font-size: 16px;
        """)

        self.layout = QVBoxLayout()
        self.layout.setContentsMargins(15, 15, 15, 15)
        self.layout.setSpacing(15)
        self.setLayout(self.layout)

        self.video_label = QLabel()
        self.video_label.setStyleSheet("background-color: black; border-radius: 8px;")
        self.video_label.setAlignment(Qt.AlignCenter)
        self.layout.addWidget(self.video_label, stretch=1)

        
        self.device = 'cuda' if torch.cuda.is_available() else 'cpu'
        self.model_object = YOLO("model/best.pt").to(self.device)
        self.model_person = YOLO("model/yolov8n.pt").to(self.device)
        self.class_names_obj = ['Basketball', 'Basketball Hoop']
        self.cap = cv2.VideoCapture(video_path)

        
        self.frame_count = 0
        self.makes = 0
        self.attempts = 0
        self.score_team1 = 0
        self.score_team2 = 0
        self.ball_pos = []
        self.hoop_pos = []
        self.up = False
        self.down = False
        self.tracked_players_team1 = {}
        self.tracked_players_team2 = {}
        self.max_id_team1 = 0
        self.max_id_team2 = 0
        self.max_tracking_distance = 50

        
        self.fade_frames = 20
        self.fade_counter = 0
        self.overlay_color = (0, 0, 0)
        self.overlay_text = "..."

        self.timer = QTimer()
        self.timer.timeout.connect(self.update_frame)
        self.timer.start(30)

        self.foul_overlay_color = (0, 0, 255)  
        self.foul_overlay_text = ""
        self.foul_fade_counter = 0
        self.foul_fade_frames = 30  
        

        
        self.controls_layout = QHBoxLayout()
        self.controls_layout.setSpacing(20)

        btn_style = """
            QPushButton {
                background-color: #9400d3;
                color: white;
                border-radius: 10px;
                padding: 10px;
                font-weight: bold;
                font-size: 16px;
                min-width: 120px;
            }
            QPushButton:hover {
                background-color: #b759e0;
            }
            QPushButton:pressed {
                background-color: #7a00b8;
            }
        """

        self.play_button = QPushButton("▶️ Play")
        self.pause_button = QPushButton("⏸ Pause")
        self.seek_backward_button = QPushButton("⏪ Backward")
        self.seek_forward_button = QPushButton("⏩ Forward")

        for btn in [self.play_button, self.pause_button, self.seek_backward_button, self.seek_forward_button]:
            btn.setStyleSheet(btn_style)

        
        style = QApplication.style()
        self.icon_fullscreen = style.standardIcon(QStyle.SP_TitleBarMaxButton)
        self.icon_exit_fullscreen = style.standardIcon(QStyle.SP_TitleBarNormalButton)

        self.toggle_fullscreen_btn = QPushButton()
        self.toggle_fullscreen_btn.setIcon(self.icon_exit_fullscreen)
        self.toggle_fullscreen_btn.setIconSize(QSize(24, 24))
        self.toggle_fullscreen_btn.setFixedSize(40, 40)
        self.toggle_fullscreen_btn.setStyleSheet("background-color: transparent; border: none;")
        self.toggle_fullscreen_btn.setToolTip("Переключить полноэкранный режим")

        self.controls_layout.addWidget(self.seek_backward_button)
        self.controls_layout.addWidget(self.pause_button)
        self.controls_layout.addWidget(self.play_button)
        self.controls_layout.addWidget(self.seek_forward_button)
        self.controls_layout.addWidget(self.toggle_fullscreen_btn)

        self.layout.addLayout(self.controls_layout)

        self.play_button.clicked.connect(self.play_video)
        self.pause_button.clicked.connect(self.pause_video)
        self.seek_forward_button.clicked.connect(self.seek_forward)
        self.seek_backward_button.clicked.connect(self.seek_backward)
        self.toggle_fullscreen_btn.clicked.connect(self.toggle_fullscreen)

        self.is_playing = True

        
        self.slider = QSlider(Qt.Horizontal)
        self.slider.setMinimum(0)
        total_frames = int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT))
        self.slider.setMaximum(total_frames - 1)
        self.slider.sliderPressed.connect(self.slider_pressed)
        self.slider.sliderReleased.connect(self.slider_released)

        self.layout.addWidget(self.slider)
        self.slider_is_pressed = False

        
    def play_video(self):
        if not self.is_playing:
            self.timer.start(30)
            self.is_playing = True

    def pause_video(self):
        if self.is_playing:
            self.timer.stop()
            self.is_playing = False

    def seek_forward(self):
        current_frame = int(self.cap.get(cv2.CAP_PROP_POS_FRAMES))
        new_frame = current_frame + 30
        total_frames = int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT))
        if new_frame >= total_frames:
            new_frame = total_frames - 1
        self.cap.set(cv2.CAP_PROP_POS_FRAMES, new_frame)
        self.update_frame()

    def seek_backward(self):
        current_frame = int(self.cap.get(cv2.CAP_PROP_POS_FRAMES))
        new_frame = current_frame - 30
        if new_frame < 0:
            new_frame = 0
        self.cap.set(cv2.CAP_PROP_POS_FRAMES, new_frame)
        self.update_frame()

    def slider_pressed(self):
        self.slider_is_pressed = True
        self.pause_video()

    def slider_released(self):
        new_pos = self.slider.value()
        self.cap.set(cv2.CAP_PROP_POS_FRAMES, new_pos)
        self.slider_is_pressed = False
        self.play_video()

    def toggle_fullscreen(self):
        if self.is_fullscreen:
            self.showNormal()
            self.is_fullscreen = False
            self.toggle_fullscreen_btn.setIcon(self.icon_fullscreen)
            self.toggle_fullscreen_btn.setToolTip("🗖")
        else:
            self.showFullScreen()
            self.is_fullscreen = True
            self.toggle_fullscreen_btn.setIcon(self.icon_exit_fullscreen)
            self.toggle_fullscreen_btn.setToolTip("🗖")

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape and self.is_fullscreen:
            self.toggle_fullscreen()
        else:
            super().keyPressEvent(event)

    def save_team_to_db(self, name, hsv):
        with self.conn.cursor() as cursor:
            cursor.execute("SELECT * FROM teams WHERE name = %s", (name,))
            if not cursor.fetchone():
                cursor.execute("INSERT INTO teams (name, hsv_h, hsv_s, hsv_v) VALUES (%s, %s, %s, %s)",
                               (name, hsv[0], hsv[1], hsv[2]))
                self.conn.commit()
                print(f"[DB] Команда '{name}' добавлена с HSV: {hsv}")


    def hsv_distance(self, hsv1, hsv2):
        return np.linalg.norm(np.array(hsv1) - np.array(hsv2))

    def average_hsv_history(self, hsv_list):
        """Вычислить усреднённое HSV из списка кортежей."""
        if not hsv_list:
            return (0, 0, 0)
        arr = np.array(hsv_list)
        mean_hsv = tuple(np.median(arr, axis=0).astype(int))
        return mean_hsv


    def detect_foul(self, all_detected_players):
        if len(all_detected_players) < 2:
            return

        current_frame = int(self.cap.get(cv2.CAP_PROP_POS_FRAMES))

        if hasattr(self, "last_foul_frame") and (current_frame - self.last_foul_frame < 30):
            return

        for center_a, (x1_a, y1_a, x2_a, y2_a), color_a in all_detected_players:
            for center_b, (x1_b, y1_b, x2_b, y2_b), color_b in all_detected_players:
                if (x1_a, y1_a, x2_a, y2_a) == (x1_b, y1_b, x2_b, y2_b):
                    continue

                height_b = y2_b - y1_b
                mid_b = y1_b + 0.55 * height_b

                if y1_a >= mid_b:
                    height_a = y2_a - y1_a
                    shirt_area = self.frame[y1_a + height_a // 3 : y1_a + 2 * height_a // 3, x1_a : x2_a]
                    if shirt_area.size == 0:
                        continue

                    hsv = cv2.cvtColor(shirt_area, cv2.COLOR_BGR2HSV)
                    h_chan, s_chan, v_chan = cv2.split(hsv)
                    mask = (s_chan > 40) & (v_chan > 40)

                    if np.count_nonzero(mask) == 0:
                        continue

                    h = int(np.median(h_chan[mask]))
                    s = int(np.median(s_chan[mask]))
                    v = int(np.median(v_chan[mask]))
                    player_hsv = (h, s, v)

                    dist1 = self.hsv_distance(player_hsv, self.team_colors.get(self.team1, (0, 0, 0)))
                    dist2 = self.hsv_distance(player_hsv, self.team_colors.get(self.team2, (0, 0, 0)))

                    foul_team = self.team2 if dist1 < dist2 else self.team1

                    insert_foul_in_db(self.match_id, foul_team)
                    print(f"[ФОЛ] Нарушение со стороны: команда '{foul_team}' (игрок на полу)")

                    self.last_foul_frame = current_frame

                    
                    self.foul_overlay_color = (0, 0, 255)
                    self.foul_overlay_text = f"Foul by {foul_team}"
                    self.foul_fade_counter = self.foul_fade_frames

                    return

    def update_frame(self):
        if not self.slider_is_pressed:
            ret, frame = self.cap.read()
            if not ret:
                self.timer.stop()
                return

        current_frame = int(self.cap.get(cv2.CAP_PROP_POS_FRAMES))
        self.slider.setValue(current_frame)
        ret, self.frame = self.cap.read()
        if not ret:
            self.timer.stop()
            self.cap.release()
            return

        frame_height, frame_width = self.frame.shape[:2]
        results_obj = self.model_object(self.frame, device=self.device)
        for r in results_obj:
            for box in r.boxes:
                x1, y1, x2, y2 = map(int, box.xyxy[0])
                w, h = x2 - x1, y2 - y1
                conf = float(box.conf[0])
                cls = int(box.cls[0])
                label = self.class_names_obj[cls]
                center = (x1 + w // 2, y1 + h // 2)

                if label == "Basketball" and conf > 0.15:
                    self.ball_pos.append((center, self.frame_count, w, h, conf))
                    cv2.rectangle(self.frame, (x1, y1), (x2, y2), (0, 0, 255), 2)

                if label == "Basketball Hoop" and conf > 0.3:
                    self.hoop_pos.append((center, self.frame_count, w, h, conf))
                    cv2.rectangle(self.frame, (x1, y1), (x2, y2), (0, 140, 255), 2)

        results_person = self.model_person(self.frame, device=self.device)
        detected_players_team1, detected_players_team2 = [], []

        for r in results_person:
            for box in r.boxes:
                x1, y1, x2, y2 = map(int, box.xyxy[0])
                conf = float(box.conf[0])
                if conf < 0.4:
                    continue

                w, h = x2 - x1, y2 - y1
                center = ((x1 + x2) // 2, (y1 + y2) // 2)

                
                if center[1] < frame_height * 0.4:
                    continue
                if center[0] < frame_width * 0.05 or center[0] > frame_width * 0.95:
                    continue
                if w * h < 2000:
                    continue

                shirt_area = self.frame[y1 + h // 3: y1 + 2 * h // 3, x1:x2]
                if shirt_area.size == 0:
                    continue

                hsv = cv2.cvtColor(shirt_area, cv2.COLOR_BGR2HSV)
                h_chan, s_chan, v_chan = cv2.split(hsv)

                
                mask = (s_chan > 40) & (v_chan > 40)
                if np.count_nonzero(mask) == 0:
                    continue

                h_filtered = h_chan[mask]
                s_filtered = s_chan[mask]
                v_filtered = v_chan[mask]

                median_h = int(np.median(h_filtered))
                median_s = int(np.median(s_filtered))
                median_v = int(np.median(v_filtered))

                avg_hsv = (median_h, median_s, median_v)

               
                if self.team1 not in self.team_colors:
                    self.team_colors_history[self.team1].append(avg_hsv)
                    self.team_colors[self.team1] = self.average_hsv_history(self.team_colors_history[self.team1])
                    self.save_team_to_db(self.team1, self.team_colors[self.team1])
                elif self.team2 not in self.team_colors and avg_hsv != self.team_colors.get(self.team1, ()):
                    self.team_colors_history[self.team2].append(avg_hsv)
                    self.team_colors[self.team2] = self.average_hsv_history(self.team_colors_history[self.team2])
                    self.save_team_to_db(self.team2, self.team_colors[self.team2])
                else:
                    
                    dist1 = self.hsv_distance(avg_hsv, self.team_colors.get(self.team1, (0, 0, 0)))
                    dist2 = self.hsv_distance(avg_hsv, self.team_colors.get(self.team2, (0, 0, 0)))

                    if dist1 <= dist2:
                        self.team_colors_history[self.team1].append(avg_hsv)
                        if len(self.team_colors_history[self.team1]) > self.max_color_history:
                            self.team_colors_history[self.team1].pop(0)
                        self.team_colors[self.team1] = self.average_hsv_history(self.team_colors_history[self.team1])
                    else:
                        self.team_colors_history[self.team2].append(avg_hsv)
                        if len(self.team_colors_history[self.team2]) > self.max_color_history:
                            self.team_colors_history[self.team2].pop(0)
                        self.team_colors[self.team2] = self.average_hsv_history(self.team_colors_history[self.team2])

                
                dist1 = self.hsv_distance(avg_hsv, self.team_colors.get(self.team1, (0, 0, 0)))
                dist2 = self.hsv_distance(avg_hsv, self.team_colors.get(self.team2, (0, 0, 0)))

                if dist1 <= dist2:
                    color = (0, 140, 255)
                    detected_players_team1.append((center, (x1, y1, x2, y2), color))
                else:
                    color = (255, 0, 0)
                    detected_players_team2.append((center, (x1, y1, x2, y2), color))

        
        if self.foul_fade_counter > 0:
            alpha = self.foul_fade_counter / self.foul_fade_frames
            overlay = self.frame.copy()
            cv2.rectangle(overlay, (0, 0), (self.frame.shape[1], 80), self.foul_overlay_color, -1)
            cv2.addWeighted(overlay, alpha * 0.4, self.frame, 1 - alpha * 0.4, 0, self.frame)

            font = cv2.FONT_HERSHEY_SIMPLEX
            font_scale = 2
            thickness = 4

            text_size, _ = cv2.getTextSize(self.foul_overlay_text, font, font_scale, thickness)
            text_width, text_height = text_size
            center_x = self.frame.shape[1] // 2

            text_x = center_x - text_width // 2
            text_y = 50 + text_height // 2

            cv2.putText(self.frame, self.foul_overlay_text, (text_x, text_y),
                        font, font_scale, (255, 255, 255), thickness)

            self.foul_fade_counter -= 1

        def track_players(detected, tracked, max_id):
            updated = {}
            assigned = set()
            for center, bbox, color in detected:
                min_dist = float('inf')
                matched_id = None
                for pid, (prev_center, _) in tracked.items():
                    dist = np.linalg.norm(np.array(center) - np.array(prev_center))
                    if dist < min_dist and dist < self.max_tracking_distance and pid not in assigned:
                        min_dist = dist
                        matched_id = pid
                if matched_id:
                    updated[matched_id] = (center, color)
                    assigned.add(matched_id)
                else:
                    max_id += 1
                    updated[max_id] = (center, color)
                    assigned.add(max_id)
            return updated, max_id

        self.tracked_players_team1, self.max_id_team1 = track_players(
            detected_players_team1, self.tracked_players_team1, self.max_id_team1)
        self.tracked_players_team2, self.max_id_team2 = track_players(
            detected_players_team2, self.tracked_players_team2, self.max_id_team2)

        def track_players(detected, tracked, max_id):
            updated = {}
            assigned = set()
            for center, bbox, color in detected:
                min_dist = float('inf')
                matched_id = None
                for pid, (prev_center, _) in tracked.items():
                    dist = np.linalg.norm(np.array(center) - np.array(prev_center))
                    if dist < min_dist and dist < self.max_tracking_distance and pid not in assigned:
                        min_dist = dist
                        matched_id = pid
                if matched_id:
                    updated[matched_id] = (center, color)
                    assigned.add(matched_id)
                else:
                    max_id += 1
                    updated[max_id] = (center, color)
                    assigned.add(max_id)
            return updated, max_id

        self.tracked_players_team1, self.max_id_team1 = track_players(
            detected_players_team1, self.tracked_players_team1, self.max_id_team1)
        self.tracked_players_team2, self.max_id_team2 = track_players(
            detected_players_team2, self.tracked_players_team2, self.max_id_team2)
        
        all_detected_players = detected_players_team1 + detected_players_team2

        
        self.detect_foul(all_detected_players)

        def draw_players(tracked, detected, team_name):
            for pid, (center, color) in tracked.items():
                x1 = y1 = x2 = y2 = None
                for c, bbox, _ in detected:
                    if c == center:
                        x1, y1, x2, y2 = bbox
                        break
                if None not in (x1, y1, x2, y2):
                    cv2.rectangle(self.frame, (x1, y1), (x2, y2), color, 2)
                    cv2.putText(self.frame, f"{team_name}_P{pid}", (x1, y1 - 5),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)
                else:
                    cv2.circle(self.frame, center, 10, color, 2)

        draw_players(self.tracked_players_team1, detected_players_team1, self.team1)
        draw_players(self.tracked_players_team2, detected_players_team2, self.team2)
        self.detect_foul(detected_players_team1 + detected_players_team2)

        

        self.clean_motion()
        self.shot_detection()
        self.display_score()

        rgb_image = cv2.cvtColor(self.frame, cv2.COLOR_BGR2RGB)
        qt_image = QImage(rgb_image.data, rgb_image.shape[1], rgb_image.shape[0],
                          rgb_image.shape[1] * 3, QImage.Format_RGB888)
        pixmap = QPixmap.fromImage(qt_image)
        scaled_pixmap = pixmap.scaled(self.video_label.width(), self.video_label.height(),
                                      Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.video_label.setPixmap(scaled_pixmap)
        self.frame_count += 1

    
    def clean_motion(self):
        
        self.ball_pos = [b for b in self.ball_pos if self.frame_count - b[1] < 30]
        for b in self.ball_pos:
            cv2.circle(self.frame, b[0], 2, (0, 0, 255), 2)
        if self.hoop_pos:
            self.hoop_pos = [h for h in self.hoop_pos if self.frame_count - h[1] < 300]
            cv2.circle(self.frame, self.hoop_pos[-1][0], 2, (128, 128, 0), 2)


    def shot_detection(self):
        three_point_threshold = 35

        if self.hoop_pos and self.ball_pos:
            if not self.up:
                self.up = detect_up(self.ball_pos, self.hoop_pos)
                if self.up:
                    self.up_frame = self.frame_count
                    self.down = False
                    self.shot_start_hoop_pos = self.hoop_pos[-1][0]

            if self.up and not self.down:
                self.down = detect_down(self.ball_pos, self.hoop_pos)
                if self.down:
                    self.down_frame = self.frame_count

            if self.down:
                scored = self.improved_score_detection()
                last_ball_pos = self.ball_pos[-1][0]
                distance = np.linalg.norm(np.array(last_ball_pos) - np.array(self.shot_start_hoop_pos))
                points = 3 if distance >= three_point_threshold else 2

                print(f"Distance: {distance:.1f}px")
                cv2.putText(self.frame, f"Shot type: {'3PT' if points == 3 else '2PT'}", (50, 110),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 0), 2)

                if scored:
                    self.makes += 1
                    self.overlay_color = (0, 255, 0)
                    self.overlay_text = f"{points} Points"

                    team_name = self.determine_scoring_team(last_ball_pos)
                    if team_name == self.team1:
                        self.score_team1 += points
                    elif team_name == self.team2:
                        self.score_team2 += points

                    if team_name:
                        inserted_team_id = insert_shot_in_db(self.match_id, team_name, points)
                        if inserted_team_id:
                            print(f"[DB] {points}-очковый бросок от '{team_name}', ID={inserted_team_id}")
                else:
                    self.overlay_color = (0, 0, 255)
                    self.overlay_text = "Miss"

                self.attempts += 1
                self.fade_counter = self.fade_frames
                self.up = self.down = False

        if self.fade_counter > 0:
            alpha = self.fade_counter / self.fade_frames
            overlay = self.frame.copy()
            cv2.rectangle(overlay, (0, 0), (self.frame.shape[1], self.frame.shape[0]), self.overlay_color, -1)
            cv2.addWeighted(overlay, alpha * 0.4, self.frame, 1 - alpha * 0.4, 0, self.frame)

            font = cv2.FONT_HERSHEY_SIMPLEX
            font_scale = 2
            thickness = 4

            text_size, _ = cv2.getTextSize(self.overlay_text, font, font_scale, thickness)
            text_width, text_height = text_size

            center_x = self.frame.shape[1] // 2

            
            text_x = center_x - text_width // 2
            text_y = 50 + text_height

            cv2.putText(self.frame, self.overlay_text, (text_x, text_y),
                        font, font_scale, (255, 255, 255), thickness)
            self.fade_counter -= 1


    def improved_score_detection(self):
        if not self.hoop_pos or not self.ball_pos:
            return False

        hoop_center, _, hoop_w, hoop_h, _ = self.hoop_pos[-1]

        radius = hoop_w * 0.6 

        def point_in_circle(point, center, radius):
            return (point[0] - center[0]) ** 2 + (point[1] - center[1]) ** 2 < radius ** 2

        ball_positions = [b[0] for b in self.ball_pos[-15:]]

     
        smoothed_positions = []
        window_size = 3
        for i in range(len(ball_positions)):
            start = max(0, i - window_size + 1)
            window_points = ball_positions[start:i + 1]
            avg_x = int(np.mean([p[0] for p in window_points]))
            avg_y = int(np.mean([p[1] for p in window_points]))
            smoothed_positions.append((avg_x, avg_y))

        
        inside_points = [p for p in smoothed_positions if point_in_circle(p, hoop_center, radius)]
        ball_in_rim = bool(inside_points)

        
        above = any(p[1] < hoop_center[1] - radius for p in smoothed_positions)
        below = any(p[1] > hoop_center[1] + radius for p in smoothed_positions)

        
        if ball_in_rim and above and below:
            y_positions = [p[1] for p in smoothed_positions]
            vertical_velocities = np.diff(y_positions)
            if any(v > 0 for v in vertical_velocities):  
                return True

        
        trajectory_score = self.analyze_trajectory()
        if trajectory_score > 0.75:
            return True

        return False


    def analyze_trajectory(self):
        if len(self.ball_pos) < 5:
            return 0.0

        hoop_center, _, hoop_w, hoop_h, _ = self.hoop_pos[-1]
        rim_top = hoop_center[1] - hoop_h // 2
        rim_bottom = hoop_center[1] + hoop_h // 4
        rim_left = hoop_center[0] - hoop_w * 0.4
        rim_right = hoop_center[0] + hoop_w * 0.4

        points = [ball[0] for ball in self.ball_pos[-10:]]
        x = [p[0] for p in points]
        y = [p[1] for p in points]

        try:
            coeffs = np.polyfit(x, y, 2)
            a, b, c = coeffs

            for test_x in np.linspace(rim_left, rim_right, 5):
                pred_y = a * test_x ** 2 + b * test_x + c
                if rim_top < pred_y < rim_bottom:
                    return 0.8 

            if y[-1] - y[0] < 0:
                return 0.0

        except:
            pass

        above = any(ball[0][1] < rim_top for ball in self.ball_pos[-5:])
        below = any(ball[0][1] > rim_bottom for ball in self.ball_pos[-5:])

        if above and below:
            return 0.6

        return 0.0


    def determine_scoring_team(self, ball_pos):
        def find_closest_player(tracked_players):
            min_dist = float('inf')
            closest_player = None
            for pid, (center, _) in tracked_players.items():
                dist = np.linalg.norm(np.array(center) - np.array(ball_pos))
                if dist < min_dist:
                    min_dist = dist
                    closest_player = (pid, center)
            return closest_player

        closest1 = find_closest_player(self.tracked_players_team1)
        closest2 = find_closest_player(self.tracked_players_team2)

        dist1 = np.linalg.norm(np.array(closest1[1]) - np.array(ball_pos)) if closest1 else float('inf')
        dist2 = np.linalg.norm(np.array(closest2[1]) - np.array(ball_pos)) if closest2 else float('inf')

        if dist1 <= dist2 and closest1:
            return self.team1
        elif closest2:
            return self.team2
        return None

    def display_score(self):
        text1 = f"{self.team1}: {self.score_team1}"
        text2 = f"{self.team2}: {self.score_team2}"
        text3 = f"Attempts: {self.attempts}"

        x = 30
        y_start = 40
        spacing = 40

        cv2.putText(self.frame, text1, (x, y_start), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 255), 2)
        cv2.putText(self.frame, text2, (x, y_start + spacing), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 255), 2)
        cv2.putText(self.frame, text3, (x, y_start + spacing * 2), cv2.FONT_HERSHEY_SIMPLEX, 1, (200, 200, 200), 2)

    def closeEvent(self, event):
        self.cap.release()
        self.timer.stop()
        event.accept()


class StatsViewer(QWidget):
    def __init__(self, match_id, db_user, db_pass, role):
        super().__init__()
        self.match_id = match_id
        self.db_user = db_user
        self.db_pass = db_pass
        self.role = role

        self.setWindowTitle("Просмотр статистики")
        self.setStyleSheet("background-color: #121212; color: #fff; font-family: 'Segoe UI', Arial;")
        self.resize(700, 500)

        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(20, 20, 20, 20)
        self.main_layout.setSpacing(20)

        self.setup_top_bar()
        self.setup_stats_area()
        self.setup_buttons()

        self.load_stats()

    def setup_top_bar(self):
        top_bar = QHBoxLayout()
        top_bar.addStretch()

        self.refresh_button = QPushButton("⟳")
        self.refresh_button.setFixedSize(32, 32)
        self.refresh_button.setStyleSheet(self.get_icon_button_style())
        self.refresh_button.setToolTip("Обновить статистику")
        self.refresh_button.clicked.connect(self.load_stats)

        top_bar.addWidget(self.refresh_button)
        self.main_layout.addLayout(top_bar)

    def setup_stats_area(self):
        self.stats_card = QFrame()
        self.stats_card.setStyleSheet("""
            QFrame {
                background-color: #1e1e1e;
                border-radius: 16px;
            }
        """)
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(35)
        shadow.setOffset(0, 0)
        shadow.setColor(QColor(0, 0, 0, 160))
        self.stats_card.setGraphicsEffect(shadow)

        card_layout = QHBoxLayout(self.stats_card)
        card_layout.setContentsMargins(40, 30, 40, 30)
        card_layout.setSpacing(60)

        self.team1_layout = QVBoxLayout()
        self.team2_layout = QVBoxLayout()

        card_layout.addLayout(self.team1_layout)
        card_layout.addLayout(self.team2_layout)

        self.team1_labels = []
        self.team2_labels = []

        self.main_layout.addWidget(self.stats_card)

    def setup_buttons(self):
        self.buttons_layout = QHBoxLayout()
        self.buttons_layout.addStretch()

        btn_style = """
            QPushButton {
                background-color: #bb86fc;
                color: #121212;
                border-radius: 10px;
                padding: 12px 24px;
                font-weight: 600;
                font-size: 14px;
            }
            QPushButton:hover {
                background-color: #9b68e4;
            }
        """

        self.view_match_button = QPushButton("Посмотреть матч")
        self.view_match_button.setStyleSheet(btn_style)
        self.view_match_button.clicked.connect(self.open_match_viewer)
        self.buttons_layout.addWidget(self.view_match_button)

        self.edit_button = QPushButton("Редактировать статистику")
        self.edit_button.setStyleSheet(btn_style)
        if self.role == 'admin':
            self.edit_button.clicked.connect(self.open_editor)
            self.buttons_layout.addWidget(self.edit_button)
        else:
            self.edit_button.setVisible(False)

        if self.role == 'admin':
            self.timecodes_button = QPushButton("Тайм-коды")
            self.timecodes_button.setStyleSheet(btn_style)
            self.timecodes_button.clicked.connect(self.open_timecodes_window)
            self.buttons_layout.addWidget(self.timecodes_button)

        self.buttons_layout.addStretch()
        self.main_layout.addLayout(self.buttons_layout)

    def load_stats(self):
        # Очистка старых меток
        for lbl in self.team1_labels:
            self.team1_layout.removeWidget(lbl)
            lbl.deleteLater()
        for lbl in self.team2_labels:
            self.team2_layout.removeWidget(lbl)
            lbl.deleteLater()
        self.team1_labels.clear()
        self.team2_labels.clear()

        try:
            connection = pymysql.connect(
                host='localhost',
                user=self.db_user,
                port=3307,
                password=self.db_pass,
                db='basketball_db',
                charset='utf8mb4',
                cursorclass=pymysql.cursors.DictCursor
            )
            with connection.cursor() as cursor:
                cursor.execute("SELECT team1, team2 FROM matches WHERE id = %s", (self.match_id,))
                match = cursor.fetchone()
                if match:
                    self.team1_name = match['team1']
                    self.team2_name = match['team2']
                else:
                    self.team1_name = "Команда 1"
                    self.team2_name = "Команда 2"

                cursor.execute("SELECT * FROM stats WHERE match_id = %s", (self.match_id,))
                stats = cursor.fetchone()
            connection.close()

            def make_label(text, layout, store):
                label = QLabel(text)
                label.setStyleSheet("font-size: 16px; padding: 4px 0;")
                layout.addWidget(label)
                store.append(label)

            if stats:
                make_label(f"Очки {self.team1_name}: {stats.get('team1_points', 0)}", self.team1_layout, self.team1_labels)
                make_label(f"Фолы {self.team1_name}: {stats.get('team1_fouls', 0)}", self.team1_layout, self.team1_labels)
                make_label(f"2-очковые {self.team1_name}: {stats.get('team1_twos', 0)}", self.team1_layout, self.team1_labels)
                make_label(f"3-очковые {self.team1_name}: {stats.get('team1_threes', 0)}", self.team1_layout, self.team1_labels)
                make_label(f"Штрафные {self.team1_name}: {stats.get('team1_freethrows', 0)}", self.team1_layout, self.team1_labels)

                make_label(f"Очки {self.team2_name}: {stats.get('team2_points', 0)}", self.team2_layout, self.team2_labels)
                make_label(f"Фолы {self.team2_name}: {stats.get('team2_fouls', 0)}", self.team2_layout, self.team2_labels)
                make_label(f"2-очковые {self.team2_name}: {stats.get('team2_twos', 0)}", self.team2_layout, self.team2_labels)
                make_label(f"3-очковые {self.team2_name}: {stats.get('team2_threes', 0)}", self.team2_layout, self.team2_labels)
                make_label(f"Штрафные {self.team2_name}: {stats.get('team2_freethrows', 0)}", self.team2_layout, self.team2_labels)
            else:
                lbl_empty = QLabel("Статистика отсутствует.")
                lbl_empty.setStyleSheet("font-size: 16px; color: #888;")
                self.team1_layout.addWidget(lbl_empty)
                self.team2_layout.addWidget(QLabel(""))

        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Ошибка при загрузке статистики: {e}")

    def open_match_viewer(self):
        self.match_viewer = MatchViewer(self.match_id)
        self.match_viewer.show()

    def open_editor(self):
        self.stats_editor = StatsEditor(self.match_id, self.db_user, self.db_pass)
        self.stats_editor.show()

    def open_timecodes_window(self):
        self.timecodes_window = TimecodesWindow(self.match_id, self.db_user, self.db_pass, parent_viewer=self)
        self.timecodes_window.show()

    def get_icon_button_style(self):
        return """
            QPushButton {
                background-color: #333;
                color: #eee;
                border-radius: 8px;
                font-size: 20px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #555;
            }
        """


class TimecodesWindow(QDialog):
    def __init__(self, match_id, db_user, db_pass, parent_viewer=None):
        super().__init__()
        self.match_id = match_id
        self.db_user = db_user
        self.db_pass = db_pass
        self.parent_viewer = parent_viewer 

        self.setWindowTitle("⏱️ Тайм-коды событий")
        self.setGeometry(300, 300, 550, 450)
        self.setStyleSheet("""
            background-color: #1f1f1f;
            color: #fff;
            font-size: 14px;
        """)

        self.layout = QVBoxLayout()
        self.setLayout(self.layout)

        # Заголовок
        title_label = QLabel("Список событий по времени")
        title_label.setFont(QFont("Arial", 16, QFont.Bold))
        title_label.setStyleSheet("margin-bottom: 10px; color: #00bfff;")
        self.layout.addWidget(title_label)

        # Список событий
        self.list_widget = QListWidget()
        self.list_widget.setStyleSheet("""
            QListWidget {
                background-color: #2b2b2b;
                border: 1px solid #444;
                padding: 5px;
            }
            QListWidget::item {
                padding: 10px;
            }
            QListWidget::item:selected {
                background-color: #444;
                color: #00ffcc;
            }
            QListWidget::item:hover {
                background-color: #333;
            }
        """)
        self.layout.addWidget(self.list_widget)

        self.load_events()

    def load_events(self):
        import pymysql
        try:
            connection = pymysql.connect(
                host='localhost',
                user=self.db_user,
                port=3307,
                password=self.db_pass,
                db='basketball_db',
                charset='utf8mb4',
                cursorclass=pymysql.cursors.DictCursor
            )
            with connection.cursor() as cursor:
                cursor.execute("""
                    SELECT e.id, e.points, e.event_time, t.name AS team_name, e.event_type
                    FROM events e
                    LEFT JOIN teams t ON e.team_id = t.id
                    WHERE e.match_id = %s
                    ORDER BY e.event_time
                """, (self.match_id,))
                events = cursor.fetchall()
            connection.close()

            self.list_widget.clear()
            for event in events:
                team_label = f"[{event['team_name']}]" if event['team_name'] else "[Неизв. команда]"
                if event['event_type'] == 'shot':
                    points = event['points'] or 0
                    status = "Промах" if points == 0 else f"{points} очк{'о' if points == 1 else 'а'}"
                else:
                    status = "Фол"
                item_text = f"{event['event_time']} — {status} {team_label}"
                item = QListWidgetItem(item_text)
                item.setData(1000, (event['id'], event['event_type']))
                self.list_widget.addItem(item)

            self.list_widget.itemDoubleClicked.connect(self.confirm_action)

        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Не удалось загрузить события: {e}")

    def confirm_action(self, item):
        event_id, event_type = item.data(1000)
        text = item.text()

        confirm = QMessageBox.question(
            self,
            "Удалить событие?",
            f"Удалить это событие из базы данных?\n\n{text}",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        if confirm == QMessageBox.Yes:
            if event_type == 'shot':
                self.delete_shot(event_id)
            elif event_type == 'foul':
                self.delete_foul(event_id)
            self.list_widget.takeItem(self.list_widget.row(item))

    def delete_shot(self, shot_id):
        import pymysql
        try:
            connection = pymysql.connect(
                host='localhost',
                user=self.db_user,
                port=3307,
                password=self.db_pass,
                db='basketball_db',
                charset='utf8mb4',
                cursorclass=pymysql.cursors.DictCursor
            )
            with connection.cursor() as cursor:
                cursor.execute("SELECT team_id, match_id, points FROM events WHERE id = %s AND event_type = 'shot'", (shot_id,))
                shot = cursor.fetchone()
                if not shot:
                    QMessageBox.warning(self, "Не найдено", "Бросок не найден в базе данных.")
                    return

                team_id = shot['team_id']
                match_id = shot['match_id']
                points = shot['points'] or 0

                cursor.execute("SELECT team1, team2 FROM matches WHERE id = %s", (match_id,))
                match = cursor.fetchone()

                cursor.execute("SELECT name FROM teams WHERE id = %s", (team_id,))
                team = cursor.fetchone()

                team_name = team['name'] if team else None

                if team_name == match['team1']:
                    if points == 1:
                        cursor.execute("UPDATE stats SET team1_points = team1_points - 1, team1_freethrows = team1_freethrows - 1 WHERE match_id = %s", (match_id,))
                    elif points == 2:
                        cursor.execute("UPDATE stats SET team1_points = team1_points - 2, team1_twos = team1_twos - 1 WHERE match_id = %s", (match_id,))
                    elif points == 3:
                        cursor.execute("UPDATE stats SET team1_points = team1_points - 3, team1_threes = team1_threes - 1 WHERE match_id = %s", (match_id,))
                elif team_name == match['team2']:
                    if points == 1:
                        cursor.execute("UPDATE stats SET team2_points = team2_points - 1, team2_freethrows = team2_freethrows - 1 WHERE match_id = %s", (match_id,))
                    elif points == 2:
                        cursor.execute("UPDATE stats SET team2_points = team2_points - 2, team2_twos = team2_twos - 1 WHERE match_id = %s", (match_id,))
                    elif points == 3:
                        cursor.execute("UPDATE stats SET team2_points = team2_points - 3, team2_threes = team2_threes - 1 WHERE match_id = %s", (match_id,))

                cursor.execute("DELETE FROM events WHERE id = %s", (shot_id,))
            connection.commit()
            connection.close()

            if self.parent_viewer:
                self.parent_viewer.load_stats()

        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Не удалось удалить бросок: {e}")

    def delete_foul(self, foul_id):
        import pymysql
        try:
            connection = pymysql.connect(
                host='localhost',
                user=self.db_user,
                port=3307,
                password=self.db_pass,
                db='basketball_db',
                charset='utf8mb4',
                cursorclass=pymysql.cursors.DictCursor
            )
            with connection.cursor() as cursor:
                cursor.execute("SELECT team_id, match_id FROM events WHERE id = %s AND event_type = 'foul'", (foul_id,))
                foul = cursor.fetchone()
                if not foul:
                    QMessageBox.warning(self, "Не найдено", "Фол не найден в базе данных.")
                    return

                team_id = foul['team_id']
                match_id = foul['match_id']

                cursor.execute("SELECT team1, team2 FROM matches WHERE id = %s", (match_id,))
                match = cursor.fetchone()

                cursor.execute("SELECT name FROM teams WHERE id = %s", (team_id,))
                team = cursor.fetchone()

                team_name = team['name'] if team else None

                if team_name == match['team1']:
                    cursor.execute("UPDATE stats SET team1_fouls = team1_fouls - 1 WHERE match_id = %s", (match_id,))
                elif team_name == match['team2']:
                    cursor.execute("UPDATE stats SET team2_fouls = team2_fouls - 1 WHERE match_id = %s", (match_id,))

                cursor.execute("DELETE FROM events WHERE id = %s", (foul_id,))
            connection.commit()
            connection.close()

            if self.parent_viewer:
                self.parent_viewer.load_stats()

        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Не удалось удалить фол: {e}")


class StatsEditor(QWidget):
    def __init__(self, match_id, db_user, db_pass):
        super().__init__()
        self.match_id = match_id
        self.db_user = db_user
        self.db_pass = db_pass

        self.setWindowTitle("Редактирование статистики")
        self.setGeometry(200, 200, 600, 400)
        self.setStyleSheet("""
            background-color: #121212;
            color: #E0E0E0;
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            font-size: 15px;
        """)

        layout = QVBoxLayout()
        stats_layout = QHBoxLayout()
        team1_layout = QVBoxLayout()
        team2_layout = QVBoxLayout()

        try:
            connection = pymysql.connect(
                host='localhost',
                user=self.db_user,
                port = 3307,
                password=self.db_pass,
                db='basketball_db',
                charset='utf8mb4',
                cursorclass=pymysql.cursors.DictCursor
            )
            with connection.cursor() as cursor:
                cursor.execute("SELECT team1, team2 FROM matches WHERE id = %s", (self.match_id,))
                match = cursor.fetchone()
                if match:
                    self.team1_name = match['team1']
                    self.team2_name = match['team2']
                else:
                    self.team1_name = "Команда 1"
                    self.team2_name = "Команда 2"

                cursor.execute("SELECT * FROM stats WHERE match_id = %s", (self.match_id,))
                stats = cursor.fetchone()

                if not stats:
                    cursor.execute(
                        "INSERT INTO stats (match_id, team1_points, team2_points, team1_fouls, team2_fouls, "
                        "team1_twos, team2_twos, team1_threes, team2_threes, team1_freethrows, team2_freethrows) "
                        "VALUES (%s, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0)",
                        (self.match_id,)
                    )
                    connection.commit()
                    stats = {
                        'team1_points': 0,
                        'team1_fouls': 0,
                        'team1_twos': 0,
                        'team1_threes': 0,
                        'team1_freethrows': 0,
                        'team2_points': 0,
                        'team2_fouls': 0,
                        'team2_twos': 0,
                        'team2_threes': 0,
                        'team2_freethrows': 0
                    }
            connection.close()

            def styled_label(text):
                lbl = QLabel(text)
                lbl.setStyleSheet("margin-bottom: 6px; font-weight: 600;")
                return lbl

            self.team1_points = QLineEdit(str(stats.get('team1_points', 0)))
            self.team1_fouls = QLineEdit(str(stats.get('team1_fouls', 0)))
            self.team1_twos = QLineEdit(str(stats.get('team1_twos', 0)))
            self.team1_threes = QLineEdit(str(stats.get('team1_threes', 0)))
            self.team1_freethrows = QLineEdit(str(stats.get('team1_freethrows', 0)))

            self.team2_points = QLineEdit(str(stats.get('team2_points', 0)))
            self.team2_fouls = QLineEdit(str(stats.get('team2_fouls', 0)))
            self.team2_twos = QLineEdit(str(stats.get('team2_twos', 0)))
            self.team2_threes = QLineEdit(str(stats.get('team2_threes', 0)))
            self.team2_freethrows = QLineEdit(str(stats.get('team2_freethrows', 0)))

            inputs_style = """
                background-color: #2b2b2b;
                border: 1px solid #444;
                border-radius: 4px;
                padding: 6px 8px;
                color: #eee;
            """
            for widget in [self.team1_points, self.team1_fouls, self.team1_twos,
                           self.team1_threes, self.team1_freethrows,
                           self.team2_points, self.team2_fouls, self.team2_twos,
                           self.team2_threes, self.team2_freethrows]:
                widget.setStyleSheet(inputs_style)

            
            team1_layout.addWidget(styled_label(f"Очки {self.team1_name}:"))
            team1_layout.addWidget(self.team1_points)
            team1_layout.addWidget(styled_label(f"Фолы {self.team1_name}:"))
            team1_layout.addWidget(self.team1_fouls)
            team1_layout.addWidget(styled_label(f"2-очковые {self.team1_name}:"))
            team1_layout.addWidget(self.team1_twos)
            team1_layout.addWidget(styled_label(f"3-очковые {self.team1_name}:"))
            team1_layout.addWidget(self.team1_threes)
            team1_layout.addWidget(styled_label(f"Штрафные {self.team1_name}:"))
            team1_layout.addWidget(self.team1_freethrows)

            
            team2_layout.addWidget(styled_label(f"Очки {self.team2_name}:"))
            team2_layout.addWidget(self.team2_points)
            team2_layout.addWidget(styled_label(f"Фолы {self.team2_name}:"))
            team2_layout.addWidget(self.team2_fouls)
            team2_layout.addWidget(styled_label(f"2-очковые {self.team2_name}:"))
            team2_layout.addWidget(self.team2_twos)
            team2_layout.addWidget(styled_label(f"3-очковые {self.team2_name}:"))
            team2_layout.addWidget(self.team2_threes)
            team2_layout.addWidget(styled_label(f"Штрафные {self.team2_name}:"))
            team2_layout.addWidget(self.team2_freethrows)

        except Exception as e:
            layout.addWidget(QLabel(f"Ошибка при получении статистики: {e}"))

        stats_layout.addLayout(team1_layout)
        stats_layout.addLayout(team2_layout)
        layout.addLayout(stats_layout)

        self.save_button = QPushButton("Сохранить изменения")
        self.save_button.setStyleSheet("""
            background-color: #3cb371;
            color: white;
            padding: 10px 20px;
            border-radius: 6px;
            font-weight: 600;
            margin-top: 20px;
        """)
        self.save_button.clicked.connect(self.save_stats)
        layout.addWidget(self.save_button, alignment=Qt.AlignCenter)

        self.setLayout(layout)

    def save_stats(self):
        try:
            connection = pymysql.connect(
                host='localhost',
                user=self.db_user,
                port = 3307,
                password=self.db_pass,
                db='basketball_db',
                charset='utf8mb4',
                cursorclass=pymysql.cursors.DictCursor
            )
            with connection.cursor() as cursor:
                cursor.execute(
                    "UPDATE stats SET team1_points = %s, team1_fouls = %s, team1_twos = %s, team1_threes = %s, team1_freethrows = %s, "
                    "team2_points = %s, team2_fouls = %s, team2_twos = %s, team2_threes = %s, team2_freethrows = %s "
                    "WHERE match_id = %s",
                    (self.team1_points.text(), self.team1_fouls.text(), self.team1_twos.text(), self.team1_threes.text(),
                     self.team1_freethrows.text(), self.team2_points.text(), self.team2_fouls.text(), self.team2_twos.text(),
                     self.team2_threes.text(), self.team2_freethrows.text(), self.match_id)
                )
                connection.commit()
            connection.close()
            QMessageBox.information(self, "Успех", "Статистика успешно обновлена.")
        except Exception as e:
            QMessageBox.warning(self, "Ошибка", f"Не удалось сохранить изменения: {e}")


class StatsWindow(QWidget):
    def __init__(self, db_user, db_pass):
        super().__init__()
        self.db_user = db_user
        self.db_pass = db_pass

        self.setWindowTitle("Статистика матчей")
        self.setGeometry(100, 100, 600, 500)
        self.setStyleSheet("""
            background-color: #121212;
            color: #E0E0E0;
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            font-size: 14px;
        """)

        layout = QVBoxLayout()

        header = QLabel("Статистика матчей")
        header.setStyleSheet("""
            font-size: 26px;
            font-weight: 700;
            color: #FFD700;
            margin-bottom: 20px;
            qproperty-alignment: AlignCenter;
        """)
        layout.addWidget(header)

        filter_layout = QHBoxLayout()

        self.team_checkbox = QCheckBox("Фильтр по команде")
        self.team_checkbox.setStyleSheet("color: #ccc; font-weight: 600;")
        self.team_filter = QLineEdit()
        self.team_filter.setPlaceholderText("Название команды")
        self.team_filter.setStyleSheet("""
            padding: 6px;
            border-radius: 5px;
            border: 1px solid #444;
            background-color: #222;
            color: #eee;
        """)

        self.date_checkbox = QCheckBox("Фильтр по дате")
        self.date_checkbox.setStyleSheet("color: #ccc; font-weight: 600;")
        self.date_filter = QDateEdit()
        self.date_filter.setCalendarPopup(True)
        self.date_filter.setDisplayFormat("dd.MM.yyyy")
        self.date_filter.setDate(QDate.currentDate())
        self.date_filter.setStyleSheet("""
            padding: 6px;
            border-radius: 5px;
            border: 1px solid #444;
            background-color: #222;
            color: #eee;
        """)

        filter_btn = QPushButton("Применить фильтр")
        filter_btn.setStyleSheet("""
            background-color: #9400d3;
            color: white;
            font-weight: 700;
            padding: 8px 15px;
            border-radius: 5px;
        """)
        filter_btn.clicked.connect(self.apply_filters)

        reset_btn = QPushButton("Сбросить фильтр")
        reset_btn.setStyleSheet("""
            background-color: #555;
            color: white;
            font-weight: 700;
            padding: 8px 15px;
            border-radius: 5px;
        """)
        reset_btn.clicked.connect(self.reset_filters)

        filter_layout.addWidget(self.team_checkbox)
        filter_layout.addWidget(self.team_filter)
        filter_layout.addWidget(self.date_checkbox)
        filter_layout.addWidget(self.date_filter)
        filter_layout.addWidget(filter_btn)
        filter_layout.addWidget(reset_btn)

        layout.addLayout(filter_layout)

        self.stats_container = QWidget()
        self.stats_layout = QVBoxLayout()
        self.stats_container.setLayout(self.stats_layout)

        self.scroll_area = QScrollArea()
        self.scroll_area.setWidget(self.stats_container)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setStyleSheet("background-color: #1c1c1e; border: none;")
        layout.addWidget(self.scroll_area)

        self.setLayout(layout)

        self.load_stats(self.stats_layout)

    def apply_filters(self):
        team = self.team_filter.text().strip() if self.team_checkbox.isChecked() else None
        date = self.date_filter.date() if self.date_checkbox.isChecked() else None
        self.load_stats(self.stats_layout, team_filter=team, date_filter=date)

    def reset_filters(self):
        self.team_filter.clear()
        self.date_filter.setDate(QDate.currentDate())
        self.team_checkbox.setChecked(False)
        self.date_checkbox.setChecked(False)
        self.load_stats(self.stats_layout)

    def load_stats(self, layout, team_filter=None, date_filter=None):
        for i in reversed(range(layout.count())):
            widget = layout.itemAt(i).widget()
            if widget:
                widget.setParent(None)

        try:
            connection = pymysql.connect(
                host='localhost',
                user=self.db_user,
                port = 3307,
                password=self.db_pass,
                db='basketball_db',
                charset='utf8mb4',
                cursorclass=pymysql.cursors.DictCursor
            )

            with connection.cursor() as cursor:
                query = """
                    SELECT m.team1, m.team2, s.team1_points, s.team2_points, m.match_time
                    FROM matches m 
                    JOIN stats s ON m.id = s.match_id
                    WHERE m.match_time <= NOW()
                """
                params = []

                if team_filter:
                    query += " AND (LOWER(m.team1) LIKE %s OR LOWER(m.team2) LIKE %s)"
                    team_search = f"%{team_filter.lower()}%"
                    params.extend([team_search, team_search])

                if date_filter:
                    query += " AND DATE(m.match_time) = %s"
                    params.append(date_filter.toString("yyyy-MM-dd"))

                query += " ORDER BY m.match_time DESC"

                cursor.execute(query, params)
                past_matches = cursor.fetchall()

            connection.close()

            if past_matches:
                for match in past_matches:
                    match_time_str = match['match_time'].strftime('%Y-%m-%d %H:%M:%S')
                    match_time = QDateTime.fromString(match_time_str, 'yyyy-MM-dd HH:mm:ss')
                    formatted_time = match_time.toString('dd MMM yyyy HH:mm')

                    match_info = f"{match['team1']} - {match['team2']}  |  {match['team1_points']} / {match['team2_points']}  |  {formatted_time}"
                    match_label = QLabel(match_info)
                    match_label.setStyleSheet("""
                        font-size: 17px;
                        color: #ddd;
                        background-color: #222;
                        border: 1px solid #444;
                        padding: 12px 15px;
                        margin-bottom: 10px;
                        border-radius: 8px;
                    """)
                    layout.addWidget(match_label)

                    separator = QFrame()
                    separator.setFrameShape(QFrame.HLine)
                    separator.setFrameShadow(QFrame.Sunken)
                    separator.setStyleSheet("border-color: #444;")
                    layout.addWidget(separator)
            else:
                no_matches_label = QLabel("Нет прошедших матчей по заданному фильтру.")
                no_matches_label.setStyleSheet("""
                    font-size: 18px; 
                    color: #ff5555; 
                    margin-top: 20px; 
                    qproperty-alignment: AlignCenter;
                """)
                layout.addWidget(no_matches_label)

            spacer = QSpacerItem(20, 40, QSizePolicy.Minimum, QSizePolicy.Expanding)
            layout.addItem(spacer)

        except Exception as e:
            error_label = QLabel(f"Ошибка при получении данных: {e}")
            error_label.setStyleSheet("""
                font-size: 18px; 
                color: #ff4444; 
                margin-top: 20px; 
                qproperty-alignment: AlignCenter;
            """)
            layout.addWidget(error_label)




class AddMatchWindow(QWidget):
    def __init__(self, db_user, db_pass):
        super().__init__()
        self.db_user = db_user
        self.db_pass = db_pass

        self.setWindowTitle("Добавить новый матч")
        self.setGeometry(150, 150, 400, 320)
        self.setStyleSheet("""
            background-color: #1c1c1e;
            color: #eaeaea;
            font-family: Arial, sans-serif;
            font-size: 16px;
        """)

        layout = QVBoxLayout()
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        self.team1_label = QLabel("Команда 1:")
        self.team1_label.setStyleSheet("font-weight: bold; color: #FFD700;")
        self.team1_input = QLineEdit()
        self.team1_input.setStyleSheet(self.get_input_style())
        layout.addWidget(self.team1_label)
        layout.addWidget(self.team1_input)

        self.team2_label = QLabel("Команда 2:")
        self.team2_label.setStyleSheet("font-weight: bold; color: #FFD700;")
        self.team2_input = QLineEdit()
        self.team2_input.setStyleSheet(self.get_input_style())
        layout.addWidget(self.team2_label)
        layout.addWidget(self.team2_input)

        self.match_time_label = QLabel("Дата и время матча (YYYY-MM-DD HH:MM):")
        self.match_time_label.setStyleSheet("font-weight: bold; color: #FFD700;")
        self.match_time_input = QLineEdit()
        self.match_time_input.setPlaceholderText("2025-06-29 19:30")
        self.match_time_input.setStyleSheet(self.get_input_style())
        layout.addWidget(self.match_time_label)
        layout.addWidget(self.match_time_input)

        self.add_match_button = QPushButton("Добавить матч")
        self.add_match_button.setStyleSheet(self.get_button_style())
        self.add_match_button.clicked.connect(self.add_match)
        layout.addWidget(self.add_match_button)

        self.setLayout(layout)

    def get_input_style(self):
        return """
            background-color: #2c2c2e;
            color: #eaeaea;
            border: 1px solid #444;
            border-radius: 6px;
            padding: 10px;
            font-size: 16px;
        """

    def get_button_style(self):
        return """
            background-color: #9400d3;
            color: white;
            border-radius: 8px;
            padding: 12px;
            font-weight: bold;
            font-size: 16px;
            transition: background-color 0.3s ease;
        """

    def add_match(self):
        team1 = self.team1_input.text().strip()
        team2 = self.team2_input.text().strip()
        match_time = self.match_time_input.text().strip()

        if not team1 or not team2 or not match_time:
            QMessageBox.critical(self, "Ошибка", "Пожалуйста, заполните все поля.")
            return

        try:
            add_match(team1, team2, match_time, self.db_user, self.db_pass)
            QMessageBox.information(self, "Успех", "Матч успешно добавлен.")

            if self.parent():
                self.parent().refresh()

            self.close()
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Не удалось добавить матч:\n{e}")
            

if __name__ == "__main__":
    app = QApplication(sys.argv)
    login_window = LoginWindow()
    login_window.show()
    sys.exit(app.exec_())