import sys, os, sqlite3, re, json, urllib.request
from pathlib import Path
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo, available_timezones
from PySide6.QtCore import Qt, QTimer, QDateTime, QStringListModel, QSize, QObject, Signal, QThread
from PySide6.QtGui import QAction, QActionGroup, QFont, QGuiApplication, QIcon, QPixmap, QPainter, QColor, QPen, QImage
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QGridLayout, QLabel, QPushButton, QLineEdit, QComboBox, QTabWidget, QListWidget,
    QListWidgetItem, QStackedWidget, QFrame, QDateTimeEdit, QSlider, QCheckBox, QSystemTrayIcon, QMenu,
    QMessageBox, QSplitter, QFormLayout, QGroupBox, QToolButton, QTableWidget, QTableWidgetItem, QSizePolicy, QCompleter, QInputDialog, QStatusBar, QDoubleSpinBox, QDialog, QTextEdit, QPlainTextEdit, QScrollArea)

APP_NAME = 'WorldClock'  # Keep the existing app-data and registry identity for backward compatibility.
APP_VERSION = '1.0.9.5'
APP_DIR = Path(os.getenv('APPDATA', str(Path.home()))) / APP_NAME
APP_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = APP_DIR / 'worldclock.db'
DEFAULT_CITIES = [('Cairo', 'Africa/Cairo'), ('Dubai', 'Asia/Dubai'), ('London', 'Europe/London'), ('New York', 'America/New_York'), ('Tokyo', 'Asia/Tokyo')]

def build_timezone_catalog():
    """Build searchable entries from the complete IANA tz database (not a short city list)."""
    import csv
    from zoneinfo import TZPATH
    from importlib import resources
    country_names = {}
    try:
        import pycountry
        country_names = {c.alpha_2: c.name for c in pycountry.countries}
    except Exception:
        pass
    zone_rows = {}
    candidates = [Path(base) / "zone.tab" for base in TZPATH]
    try:
        candidates.append(Path(str(resources.files("tzdata").joinpath("zoneinfo/zone.tab"))))
    except Exception:
        pass
    for tab in candidates:
        if not tab.exists():
            continue
        try:
            for row in tab.read_text(encoding="utf-8").splitlines():
                if not row or row.startswith("#"):
                    continue
                parts = row.split("\t")
                if len(parts) >= 3:
                    codes, zone = parts[0], parts[2]
                    city = (parts[3] if len(parts) > 3 else zone.split("/")[-1]).replace("_", " ")
                    for cc in codes.split(","):
                        country = country_names.get(cc, cc)
                        zone_rows[zone] = (country, city)
            if zone_rows:
                break
        except Exception:
            pass
    catalog = []
    for zone in sorted(available_timezones()):
        if zone in zone_rows:
            country, city = zone_rows[zone]
            label = f"{country} — {city} ({zone})"
        else:
            city = zone.split("/")[-1].replace("_", " ")
            region = zone.split("/")[0] if "/" in zone else "Other"
            label = f"{region} — {city} ({zone})"
        catalog.append((label, zone, city))

    # Searchable city aliases. Multiple cities may intentionally share one IANA zone.
    city_aliases = [
        ("Saudi Arabia", "Jeddah", "Asia/Riyadh"),
        ("Saudi Arabia", "Riyadh", "Asia/Riyadh"),
        ("Saudi Arabia", "Mecca", "Asia/Riyadh"),
        ("Saudi Arabia", "Medina", "Asia/Riyadh"),
        ("Saudi Arabia", "Dammam", "Asia/Riyadh"),
        ("Saudi Arabia", "Taif", "Asia/Riyadh"),
        ("Saudi Arabia", "Al Khobar", "Asia/Riyadh"),
        ("Egypt", "Alexandria", "Africa/Cairo"),
        ("Egypt", "Giza", "Africa/Cairo"),
        ("United Arab Emirates", "Dubai", "Asia/Dubai"),
        ("United Arab Emirates", "Abu Dhabi", "Asia/Dubai"),
        ("United Kingdom", "London", "Europe/London"),
        ("United States", "New York", "America/New_York"),
        ("United States", "Los Angeles", "America/Los_Angeles"),
        ("France", "Paris", "Europe/Paris"),
        ("France", "Lyon", "Europe/Paris"),
        ("Germany", "Berlin", "Europe/Berlin"),
        ("Germany", "Munich", "Europe/Berlin"),
        ("Italy", "Rome", "Europe/Rome"),
        ("Spain", "Madrid", "Europe/Madrid"),
        ("Spain", "Barcelona", "Europe/Madrid"),
        ("Brazil", "Sao Paulo", "America/Sao_Paulo"),
        ("Mexico", "Mexico City", "America/Mexico_City"),
        ("Australia", "Melbourne", "Australia/Melbourne"),
        ("Australia", "Perth", "Australia/Perth"),
        ("Russia", "Moscow", "Europe/Moscow"),
        ("Russia", "Saint Petersburg", "Europe/Moscow"),
        ("Japan", "Tokyo", "Asia/Tokyo"),
        ("China", "Shanghai", "Asia/Shanghai"),
        ("India", "Mumbai", "Asia/Kolkata"),
        ("Singapore", "Singapore", "Asia/Singapore"),
    ]
    for country, city, zone in city_aliases:
        if zone in available_timezones():
            catalog.append((f"{country} — {city} ({zone})", zone, city))
    catalog.sort(key=lambda item: item[0].casefold())
    return catalog

TIMEZONE_CATALOG = build_timezone_catalog()
CITY_NAMES = [item[0] for item in TIMEZONE_CATALOG]


DARK = '''
QWidget { background:#0b1020; color:#edf2ff; font-family:'Segoe UI'; font-size:10pt; }
QMainWindow { background:#0b1020; }
QTabWidget::pane { border:1px solid #26344a; border-radius:12px; top:-1px; }
QTabBar::tab { background:#111a2c; color:#9aa9c1; padding:8px 11px; margin-right:3px; font-size:9pt; border-top-left-radius:8px; border-top-right-radius:8px; }
QTabBar::tab:selected { color:#ffffff; background:#1a2942; border-bottom:2px solid #55d6b2; }
QLineEdit,QComboBox,QDateTimeEdit { background:#111b2e; border:1px solid #2b3b55; border-radius:8px; padding:7px 10px; selection-background-color:#287d70; min-height:20px; }\nQLineEdit:focus,QComboBox:focus,QDateTimeEdit:focus { border:1px solid #55d6b2; }
QComboBox QAbstractItemView,QCompleter QAbstractItemView { background:#111b2e; color:#edf2ff; border:1px solid #344761; selection-background-color:#24594f; selection-color:#ffffff; padding:6px; outline:0; }
QPushButton { background:#17253b; border:1px solid #30445f; border-radius:8px; padding:7px 11px; min-height:18px; }
QPushButton:hover { background:#263a58; border-color:#55d6b2; }
QPushButton#primary { background:#176b60; border-color:#258c7d; font-weight:600; }
QPushButton#danger { color:#ff9ba5; }
QListWidget,QTableWidget { background:#10192a; border:1px solid #26344a; border-radius:9px; padding:5px; gridline-color:#26344a; }
QHeaderView::section { background:#17243a; color:#9aa9c1; border:0; padding:8px; }
QSlider::groove:horizontal { height:5px; background:#26344a; border-radius:2px; }
QSlider::handle:horizontal { background:#55d6b2; width:14px; margin:-5px 0; border-radius:7px; }
QCheckBox { spacing:8px; }
QCheckBox::indicator { width:16px; height:16px; }
QFrame#card { background:#111b2e; border:1px solid #2a3b54; border-radius:14px; }\nQFrame#card:hover { border:1px solid #45627d; }
QLabel#muted { color:#91a0b8; }
QLabel#clock { font-size:23pt; font-weight:700; color:#f5f7ff; }

QListWidget#mainNavigation {
    background:#0e1728; border:1px solid #24344d; border-radius:12px;
    padding:8px 6px; color:#9fb0c9; outline:0;
}
QListWidget#mainNavigation::item {
    background:transparent; border-radius:8px; padding:8px 10px;
    margin:2px 0; min-height:24px;
}
QListWidget#mainNavigation::item:hover { background:#17263b; color:#edf2ff; }
QListWidget#mainNavigation::item:selected {
    background:#185f55; color:#ffffff; border-left:3px solid #55d6b2;
}
QStackedWidget#workspacePages {
    background:#0b1220; border:1px solid #24344d; border-radius:12px;
}
QToolButton#languageSelector {
    background:#111b2e; border:1px solid #30445f; border-radius:9px; padding:5px;
}
QToolButton#languageSelector:hover { border-color:#55d6b2; background:#17253b; }
QPushButton#quickCurrencyButton { background:#185f55; color:#ffffff; border:1px solid #267e70; }
QPushButton#quickCurrencyButton:hover { background:#207566; }

QToolButton#languageSelector::menu-indicator { image:none; }
QMenu { background:#111b2e; color:#edf2ff; border:1px solid #344761; padding:5px; }
QMenu::item { padding:8px 24px 8px 10px; border-radius:5px; }
QMenu::item:selected { background:#24594f; }
'''

TRANSLATIONS = {'ru': {'Your saved places': 'Сохранённые места', 'Search by city, country or IANA time zone. The catalog includes the full installed time-zone database.': 'Поиск по городу, стране или часовому поясу IANA.', 'Search any country or city… e.g. Japan, Paris, New York, Asia/Tokyo': 'Поиск страны или города… например: Japan, Paris, New York', '＋  Add location': '＋ Добавить место', 'Remove selected': 'Удалить выбранное', '☆ Toggle favorite': '☆ В избранное', '↑ Move up': '↑ Выше', '↓ Move down': '↓ Ниже', 'World clock': 'Мировые часы', 'Time converter': 'Конвертер времени', 'Currency converter': 'Конвертер валют', 'Quick tools': 'Быстрые инструменты', 'Meeting planner': 'Планировщик встреч', 'Time comparison': 'Сравнение времени', 'World alarms': 'Мировые будильники', 'Settings': 'Настройки', 'Convert a local date and time into every city you follow.': 'Переведите местное время для всех выбранных городов.', 'Time in:': 'Время в:', 'Date & time:': 'Дата и время:', 'Convert time': 'Конвертировать время', 'City': 'Город', 'Local date & time': 'Местные дата и время', 'UTC offset': 'Смещение UTC', 'Find a suitable meeting time across your selected cities.': 'Найдите удобное время встречи для выбранных городов.', 'Reference city:': 'Опорный город:', 'Meeting time:': 'Время встречи:', 'Compare participant times': 'Сравнить время участников', 'Find best meeting hours': 'Найти лучшее время', 'Choose a date and compare local times across your saved cities.': 'Выберите дату и сравните местное время в сохранённых городах.', 'Live world time comparison': 'Сравнение мирового времени', 'A live overview of every saved city, including date, UTC offset and typical business-hour status.': 'Текущее время, дата, смещение UTC и рабочие часы для каждого города.', 'Local time': 'Местное время', 'Local date': 'Местная дата', 'Local status': 'Статус', 'Create a one-time alarm using the selected city’s local date and time. Alarms are saved on this PC.': 'Создайте разовый будильник по местному времени выбранного города. Сигналы сохраняются на этом компьютере.', 'e.g. Call the Dubai office': 'Например: Позвонить в офис Дубая', 'Alarm title:': 'Название сигнала:', 'City / time zone:': 'Город / часовой пояс:', 'Local date & time:': 'Местные дата и время:', '＋ Add alarm': '＋ Добавить сигнал', 'Delete selected': 'Удалить выбранное', 'Title': 'Название', 'Status': 'Статус', 'Appearance & behavior': 'Внешний вид и поведение', 'My reference city:': 'Мой основной город:', '12-hour clock': '12-часовой формат', '24-hour clock': '24-часовой формат', 'Mini widget opacity:': 'Прозрачность мини-окна:', 'Show mini widget': 'Показать мини-окно', 'Keep mini widget always on top': 'Закрепить мини-окно поверх окон', 'Start WorldClock when Windows starts': 'Запускать WorldClock вместе с Windows', 'Open mini clock': 'Открыть мини-часы', 'Open dashboard': 'Открыть панель', 'Quit': 'Выход', 'Business hours': 'Рабочее время', 'Weekend': 'Выходной', 'Outside business hours': 'Вне рабочего времени'}, 'de': {'Your saved places': 'Gespeicherte Orte', 'Search by city, country or IANA time zone. The catalog includes the full installed time-zone database.': 'Suche nach Stadt, Land oder IANA-Zeitzone.', 'Search any country or city… e.g. Japan, Paris, New York, Asia/Tokyo': 'Land oder Stadt suchen… z. B. Japan, Paris, New York', '＋  Add location': '＋ Ort hinzufügen', 'Remove selected': 'Auswahl entfernen', '☆ Toggle favorite': '☆ Favorit umschalten', '↑ Move up': '↑ Nach oben', '↓ Move down': '↓ Nach unten', 'World clock': 'Weltuhr', 'Time converter': 'Zeitumrechner', 'Currency converter': 'Währungsrechner', 'Quick tools': 'Schnellwerkzeuge', 'Meeting planner': 'Meetingplaner', 'Time comparison': 'Zeitvergleich', 'World alarms': 'Weltweite Alarme', 'Settings': 'Einstellungen', 'Convert a local date and time into every city you follow.': 'Lokale Zeit in die Zeit aller gespeicherten Städte umrechnen.', 'Time in:': 'Zeit in:', 'Date & time:': 'Datum & Uhrzeit:', 'Convert time': 'Zeit umrechnen', 'City': 'Stadt', 'Local date & time': 'Lokales Datum & Uhrzeit', 'UTC offset': 'UTC-Abweichung', 'Find a suitable meeting time across your selected cities.': 'Finden Sie eine passende Besprechungszeit für Ihre Städte.', 'Reference city:': 'Referenzstadt:', 'Meeting time:': 'Besprechungszeit:', 'Compare participant times': 'Teilnehmerzeiten vergleichen', 'Find best meeting hours': 'Beste Besprechungszeit finden', 'Choose a date and compare local times across your saved cities.': 'Datum wählen und Ortszeiten vergleichen.', 'Live world time comparison': 'Weltweiter Zeitvergleich', 'A live overview of every saved city, including date, UTC offset and typical business-hour status.': 'Live-Übersicht mit Datum, UTC-Abweichung und üblichen Geschäftszeiten.', 'Local time': 'Ortszeit', 'Local date': 'Lokales Datum', 'Local status': 'Lokaler Status', 'Create a one-time alarm using the selected city’s local date and time. Alarms are saved on this PC.': 'Einmaligen Alarm anhand der Ortszeit erstellen. Alarme werden auf diesem PC gespeichert.', 'e.g. Call the Dubai office': 'z. B. Büro in Dubai anrufen', 'Alarm title:': 'Alarmname:', 'City / time zone:': 'Stadt / Zeitzone:', 'Local date & time:': 'Lokales Datum & Uhrzeit:', '＋ Add alarm': '＋ Alarm hinzufügen', 'Delete selected': 'Auswahl löschen', 'Title': 'Titel', 'Status': 'Status', 'Appearance & behavior': 'Darstellung & Verhalten', 'My reference city:': 'Meine Referenzstadt:', '12-hour clock': '12-Stunden-Format', '24-hour clock': '24-Stunden-Format', 'Mini widget opacity:': 'Deckkraft des Mini-Fensters:', 'Show mini widget': 'Mini-Fenster anzeigen', 'Keep mini widget always on top': 'Mini-Fenster immer im Vordergrund', 'Start WorldClock when Windows starts': 'WorldClock mit Windows starten', 'Open mini clock': 'Mini-Uhr öffnen', 'Open dashboard': 'Dashboard öffnen', 'Quit': 'Beenden', 'Business hours': 'Geschäftszeit', 'Weekend': 'Wochenende', 'Outside business hours': 'Außerhalb der Geschäftszeit'}, 'fr': {'Your saved places': 'Vos lieux enregistrés', 'Search by city, country or IANA time zone. The catalog includes the full installed time-zone database.': 'Rechercher une ville, un pays ou un fuseau IANA.', 'Search any country or city… e.g. Japan, Paris, New York, Asia/Tokyo': 'Rechercher un pays ou une ville… ex. Paris, Tokyo', '＋  Add location': '＋ Ajouter un lieu', 'Remove selected': 'Supprimer la sélection', '☆ Toggle favorite': '☆ Favori', '↑ Move up': '↑ Monter', '↓ Move down': '↓ Descendre', 'World clock': 'Horloge mondiale', 'Time converter': 'Convertisseur horaire', 'Currency converter': 'Convertisseur de devises', 'Quick tools': 'Outils rapides', 'Meeting planner': 'Planificateur de réunion', 'Time comparison': 'Comparaison des heures', 'World alarms': 'Alarmes mondiales', 'Settings': 'Paramètres', 'Convert a local date and time into every city you follow.': 'Convertissez une date et une heure locales pour toutes vos villes.', 'Time in:': 'Heure à :', 'Date & time:': 'Date et heure :', 'Convert time': 'Convertir l’heure', 'City': 'Ville', 'Local date & time': 'Date et heure locales', 'UTC offset': 'Décalage UTC', 'Find a suitable meeting time across your selected cities.': 'Trouvez un horaire adapté aux villes sélectionnées.', 'Reference city:': 'Ville de référence :', 'Meeting time:': 'Heure de réunion :', 'Compare participant times': 'Comparer les heures', 'Find best meeting hours': 'Trouver le meilleur créneau', 'Choose a date and compare local times across your saved cities.': 'Choisissez une date et comparez les heures locales.', 'Live world time comparison': 'Comparaison mondiale en direct', 'A live overview of every saved city, including date, UTC offset and typical business-hour status.': 'Vue en direct des dates, décalages UTC et horaires de travail.', 'Local time': 'Heure locale', 'Local date': 'Date locale', 'Local status': 'Statut local', 'Create a one-time alarm using the selected city’s local date and time. Alarms are saved on this PC.': 'Créez une alarme ponctuelle selon l’heure locale de la ville. Les alarmes sont enregistrées sur ce PC.', 'e.g. Call the Dubai office': 'ex. Appeler le bureau de Dubaï', 'Alarm title:': 'Nom de l’alarme :', 'City / time zone:': 'Ville / fuseau horaire :', 'Local date & time:': 'Date et heure locales :', '＋ Add alarm': '＋ Ajouter une alarme', 'Delete selected': 'Supprimer la sélection', 'Title': 'Titre', 'Status': 'Statut', 'Appearance & behavior': 'Apparence et comportement', 'My reference city:': 'Ma ville de référence :', '12-hour clock': 'Format 12 heures', '24-hour clock': 'Format 24 heures', 'Mini widget opacity:': 'Opacité du mini-widget :', 'Show mini widget': 'Afficher le mini-widget', 'Keep mini widget always on top': 'Garder le mini-widget au premier plan', 'Start WorldClock when Windows starts': 'Lancer WorldClock au démarrage de Windows', 'Open mini clock': 'Ouvrir la mini-horloge', 'Open dashboard': 'Ouvrir le tableau de bord', 'Quitter': 'Quitter', 'Business hours': 'Heures de travail', 'Weekend': 'Week-end', 'Outside business hours': 'Hors heures de travail'}, 'es': {'Your saved places': 'Tus lugares guardados', 'Search by city, country or IANA time zone. The catalog includes the full installed time-zone database.': 'Busca por ciudad, país o zona horaria IANA.', 'Search any country or city… e.g. Japan, Paris, New York, Asia/Tokyo': 'Buscar país o ciudad… ej. París, Tokio', '＋  Add location': '＋ Añadir ubicación', 'Remove selected': 'Eliminar selección', '☆ Toggle favorite': '☆ Favorito', '↑ Move up': '↑ Subir', '↓ Move down': '↓ Bajar', 'World clock': 'Reloj mundial', 'Time converter': 'Conversor horario', 'Currency converter': 'Conversor de divisas', 'Quick tools': 'Herramientas rápidas', 'Meeting planner': 'Planificador de reuniones', 'Time comparison': 'Comparación horaria', 'World alarms': 'Alarmas mundiales', 'Settings': 'Ajustes', 'Convert a local date and time into every city you follow.': 'Convierte una fecha y hora local para todas tus ciudades.', 'Time in:': 'Hora en:', 'Date & time:': 'Fecha y hora:', 'Convert time': 'Convertir hora', 'City': 'Ciudad', 'Local date & time': 'Fecha y hora local', 'UTC offset': 'Desfase UTC', 'Find a suitable meeting time across your selected cities.': 'Encuentra una hora adecuada para las ciudades seleccionadas.', 'Reference city:': 'Ciudad de referencia:', 'Meeting time:': 'Hora de la reunión:', 'Compare participant times': 'Comparar horas', 'Find best meeting hours': 'Buscar mejor horario', 'Choose a date and compare local times across your saved cities.': 'Elige una fecha y compara las horas locales.', 'Live world time comparison': 'Comparación mundial en directo', 'A live overview of every saved city, including date, UTC offset and typical business-hour status.': 'Vista en directo de fechas, desfases UTC y horario laboral.', 'Local time': 'Hora local', 'Local date': 'Fecha local', 'Local status': 'Estado local', 'Create a one-time alarm using the selected city’s local date and time. Alarms are saved on this PC.': 'Crea una alarma única según la hora local de la ciudad. Se guarda en este PC.', 'e.g. Call the Dubai office': 'p. ej. Llamar a la oficina de Dubái', 'Alarm title:': 'Nombre de alarma:', 'City / time zone:': 'Ciudad / zona horaria:', 'Local date & time:': 'Fecha y hora local:', '＋ Add alarm': '＋ Añadir alarma', 'Delete selected': 'Eliminar selección', 'Title': 'Título', 'Status': 'Estado', 'Appearance & behavior': 'Apariencia y comportamiento', 'My reference city:': 'Mi ciudad de referencia:', '12-hour clock': 'Formato de 12 horas', '24-hour clock': 'Formato de 24 horas', 'Mini widget opacity:': 'Opacidad del miniwidget:', 'Show mini widget': 'Mostrar miniwidget', 'Keep mini widget always on top': 'Mantener miniwidget siempre visible', 'Start WorldClock when Windows starts': 'Iniciar WorldClock con Windows', 'Open mini clock': 'Abrir mini reloj', 'Open dashboard': 'Abrir panel', 'Quit': 'Salir', 'Business hours': 'Horario laboral', 'Weekend': 'Fin de semana', 'Outside business hours': 'Fuera del horario laboral'}, 'it': {'Your saved places': 'Le tue località salvate', 'Search by city, country or IANA time zone. The catalog includes the full installed time-zone database.': 'Cerca per città, paese o fuso orario IANA.', 'Search any country or city… e.g. Japan, Paris, New York, Asia/Tokyo': 'Cerca un paese o una città… es. Parigi, Tokyo', '＋  Add location': '＋ Aggiungi località', 'Remove selected': 'Rimuovi selezione', '☆ Toggle favorite': '☆ Preferito', '↑ Move up': '↑ Sposta su', '↓ Move down': '↓ Sposta giù', 'World clock': 'Orologio mondiale', 'Time converter': 'Convertitore orario', 'Currency converter': 'Convertitore di valuta', 'Quick tools': 'Strumenti rapidi', 'Meeting planner': 'Pianificatore riunioni', 'Time comparison': 'Confronto orari', 'World alarms': 'Sveglie mondiali', 'Settings': 'Impostazioni', 'Convert a local date and time into every city you follow.': 'Converti data e ora locali per tutte le città salvate.', 'Time in:': 'Ora a:', 'Date & time:': 'Data e ora:', 'Convert time': 'Converti ora', 'City': 'Città', 'Local date & time': 'Data e ora locali', 'UTC offset': 'Offset UTC', 'Find a suitable meeting time across your selected cities.': 'Trova un orario adatto per le città selezionate.', 'Reference city:': 'Città di riferimento:', 'Meeting time:': 'Ora della riunione:', 'Compare participant times': 'Confronta orari', 'Find best meeting hours': 'Trova orario migliore', 'Choose a date and compare local times across your saved cities.': 'Scegli una data e confronta gli orari locali.', 'Live world time comparison': 'Confronto mondiale in tempo reale', 'A live overview of every saved city, including date, UTC offset and typical business-hour status.': 'Vista in tempo reale di date, offset UTC e orari lavorativi.', 'Local time': 'Ora locale', 'Local date': 'Data locale', 'Local status': 'Stato locale', 'Create a one-time alarm using the selected city’s local date and time. Alarms are saved on this PC.': 'Crea una sveglia singola in base all’ora locale della città. Le sveglie sono salvate su questo PC.', 'e.g. Call the Dubai office': 'es. Chiama l’ufficio di Dubai', 'Alarm title:': 'Nome sveglia:', 'City / time zone:': 'Città / fuso orario:', 'Local date & time:': 'Data e ora locali:', '＋ Add alarm': '＋ Aggiungi sveglia', 'Delete selected': 'Elimina selezione', 'Title': 'Titolo', 'Status': 'Stato', 'Appearance & behavior': 'Aspetto e comportamento', 'My reference city:': 'La mia città di riferimento:', '12-hour clock': 'Formato 12 ore', '24-hour clock': 'Formato 24 ore', 'Mini widget opacity:': 'Opacità mini-widget:', 'Show mini widget': 'Mostra mini-widget', 'Keep mini widget always on top': 'Mantieni mini-widget sempre in primo piano', 'Start WorldClock when Windows starts': 'Avvia WorldClock all’avvio di Windows', 'Open mini clock': 'Apri mini orologio', 'Open dashboard': 'Apri dashboard', 'Quit': 'Esci', 'Business hours': 'Orario lavorativo', 'Weekend': 'Fine settimana', 'Outside business hours': 'Fuori orario lavorativo'}}

# SmartDesk module translations. Unknown labels deliberately fall back to English.
TRANSLATIONS['ru'].update({'QR generator':'Генератор QR-кодов','Clipboard':'Буфер обмена','Unit converter':'Конвертер единиц','Quick calculator':'Быстрый калькулятор','Text tools':'Работа с текстом','Generate QR':'Создать QR','Save PNG':'Сохранить PNG',
    'Convert currencies instantly':'Мгновенная конвертация валют','Amount':'Сумма','From':'Из','To':'В','⇄ Swap':'⇄ Обменять',
    'Copy with symbol':'Копировать с символом','Copy amount':'Копировать сумму','Refresh rates':'Обновить курсы',
    'Live reference rates with an offline cache. Rates are indicative, not bank or card settlement rates.':'Актуальные справочные курсы с офлайн-кэшем. Курсы ориентировочные.',
    'Everyday tools':'Повседневные инструменты','Unit converter':'Конвертер единиц','Quick calculator':'Быстрый калькулятор',
    'QR code generator':'Генератор QR-кодов','Clipboard history':'История буфера обмена','Generate QR':'Создать QR','Save PNG':'Сохранить PNG',
    'Enable clipboard history for this session':'Включить историю буфера обмена на этот сеанс'
})
TRANSLATIONS['de'].update({'QR generator':'QR-Generator','Clipboard':'Zwischenablage','Unit converter':'Einheitenumrechner','Quick calculator':'Taschenrechner','Text tools':'Textwerkzeuge','Generate QR':'QR erstellen','Save PNG':'PNG speichern',
    'Convert currencies instantly':'Währungen sofort umrechnen','Amount':'Betrag','From':'Von','To':'Nach','⇄ Swap':'⇄ Tauschen',
    'Copy with symbol':'Mit Symbol kopieren','Copy amount':'Betrag kopieren','Refresh rates':'Kurse aktualisieren',
    'Everyday tools':'Alltagswerkzeuge','Unit converter':'Einheitenumrechner','Quick calculator':'Taschenrechner',
    'QR code generator':'QR-Code-Generator','Clipboard history':'Zwischenablage-Verlauf','Generate QR':'QR erstellen','Save PNG':'PNG speichern',
    'Enable clipboard history for this session':'Zwischenablage-Verlauf für diese Sitzung aktivieren'
})
TRANSLATIONS['fr'].update({'QR generator':'Générateur QR','Clipboard':'Presse-papiers','Unit converter':'Convertisseur d’unités','Quick calculator':'Calculatrice rapide','Text tools':'Outils de texte','Generate QR':'Générer QR','Save PNG':'Enregistrer PNG',
    'Convert currencies instantly':'Convertir des devises instantanément','Amount':'Montant','From':'De','To':'Vers','⇄ Swap':'⇄ Inverser',
    'Copy with symbol':'Copier avec symbole','Copy amount':'Copier le montant','Refresh rates':'Actualiser les taux',
    'Everyday tools':'Outils quotidiens','Unit converter':'Convertisseur d’unités','Quick calculator':'Calculatrice rapide',
    'QR code generator':'Générateur de QR code','Clipboard history':'Historique du presse-papiers','Generate QR':'Générer QR','Save PNG':'Enregistrer PNG',
    'Enable clipboard history for this session':'Activer l’historique du presse-papiers pour cette session'
})
TRANSLATIONS['es'].update({'QR generator':'Generador QR','Clipboard':'Portapapeles','Unit converter':'Conversor de unidades','Quick calculator':'Calculadora rápida','Text tools':'Herramientas de texto','Generate QR':'Generar QR','Save PNG':'Guardar PNG',
    'Convert currencies instantly':'Convierte divisas al instante','Amount':'Cantidad','From':'De','To':'A','⇄ Swap':'⇄ Intercambiar',
    'Copy with symbol':'Copiar con símbolo','Copy amount':'Copiar cantidad','Refresh rates':'Actualizar tasas',
    'Everyday tools':'Herramientas diarias','Unit converter':'Conversor de unidades','Quick calculator':'Calculadora rápida',
    'QR code generator':'Generador de códigos QR','Clipboard history':'Historial del portapapeles','Generate QR':'Generar QR','Save PNG':'Guardar PNG',
    'Enable clipboard history for this session':'Activar historial del portapapeles durante esta sesión'
})
TRANSLATIONS['it'].update({'QR generator':'Generatore QR','Clipboard':'Appunti','Unit converter':'Convertitore di unità','Quick calculator':'Calcolatrice rapida','Text tools':'Strumenti di testo','Generate QR':'Genera QR','Save PNG':'Salva PNG',
    'Convert currencies instantly':'Converti valute istantaneamente','Amount':'Importo','From':'Da','To':'A','⇄ Swap':'⇄ Scambia',
    'Copy with symbol':'Copia con simbolo','Copy amount':'Copia importo','Refresh rates':'Aggiorna tassi',
    'Everyday tools':'Strumenti quotidiani','Unit converter':'Convertitore di unità','Quick calculator':'Calcolatrice rapida',
    'QR code generator':'Generatore di codici QR','Clipboard history':'Cronologia appunti','Generate QR':'Genera QR','Save PNG':'Salva PNG',
    'Enable clipboard history for this session':'Abilita cronologia appunti per questa sessione'
})


class Store:
    def __init__(self):
        self.db = sqlite3.connect(DB_PATH)
        self.db.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)")
        self.db.execute("""CREATE TABLE IF NOT EXISTS currency_cache (
            base TEXT PRIMARY KEY, rates_json TEXT NOT NULL, updated_at TEXT NOT NULL
        )""")
        self.db.execute("""CREATE TABLE IF NOT EXISTS alarms (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            city TEXT NOT NULL,
            zone TEXT NOT NULL,
            local_at TEXT NOT NULL,
            enabled INTEGER NOT NULL DEFAULT 1,
            fired INTEGER NOT NULL DEFAULT 0
        )""")
        self._migrate_cities()
        if self.db.execute('SELECT COUNT(*) FROM cities').fetchone()[0] == 0:
            self.db.executemany('INSERT OR IGNORE INTO cities(name,zone,position,favorite) VALUES (?,?,?,0)',
                                [(n,z,i) for i,(n,z) in enumerate(DEFAULT_CITIES[:2])])
        self.db.commit()

    def _migrate_cities(self):
        info = self.db.execute("PRAGMA table_info(cities)").fetchall()
        if not info:
            self.db.execute("""CREATE TABLE cities (
                name TEXT NOT NULL, zone TEXT NOT NULL, position INTEGER NOT NULL DEFAULT 0,
                favorite INTEGER NOT NULL DEFAULT 0, UNIQUE(name, zone))""")
            return
        cols = [r[1] for r in info]
        sql_row = self.db.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='cities'").fetchone()
        sql = (sql_row[0] or "").upper() if sql_row else ""
        needs_rebuild = "FAVORITE" not in cols or "UNIQUE (ZONE)" in sql or "ZONE TEXT UNIQUE" in sql
        if needs_rebuild:
            rows = self.db.execute("SELECT name,zone,position FROM cities ORDER BY position").fetchall()
            self.db.execute("ALTER TABLE cities RENAME TO cities_legacy")
            self.db.execute("""CREATE TABLE cities (
                name TEXT NOT NULL, zone TEXT NOT NULL, position INTEGER NOT NULL DEFAULT 0,
                favorite INTEGER NOT NULL DEFAULT 0, UNIQUE(name, zone))""")
            self.db.executemany("INSERT OR IGNORE INTO cities(name,zone,position,favorite) VALUES (?,?,?,0)", rows)
            self.db.execute("DROP TABLE cities_legacy")

    def cities(self):
        return self.db.execute('SELECT name,zone FROM cities ORDER BY position').fetchall()

    def add_city(self,name,zone):
        self.db.execute('INSERT OR IGNORE INTO cities(name,zone,position,favorite) VALUES (?,?,(SELECT COALESCE(MAX(position),-1)+1 FROM cities),0)',(name,zone))
        self.db.commit()

    def remove_city(self,zone,name=None):
        if name:
            self.db.execute('DELETE FROM cities WHERE zone=? AND name=?',(zone,name))
        else:
            self.db.execute('DELETE FROM cities WHERE zone=?',(zone,))
        self.db.commit()

    def move(self,idx,delta):
        rows=self.db.execute('SELECT name,zone,favorite FROM cities ORDER BY position').fetchall(); j=idx+delta
        if 0<=idx<len(rows) and 0<=j<len(rows):
            rows[idx],rows[j]=rows[j],rows[idx]
            self.db.execute('UPDATE cities SET position=position+10000')
            for i,(n,z,fav) in enumerate(rows):
                self.db.execute('UPDATE cities SET position=?,favorite=? WHERE name=? AND zone=?',(i,fav,n,z))
            self.db.commit()

    def favorites(self):
        return {(n,z) for n,z in self.db.execute('SELECT name,zone FROM cities WHERE favorite=1')}

    def toggle_favorite(self,name,zone):
        self.db.execute('UPDATE cities SET favorite=CASE favorite WHEN 1 THEN 0 ELSE 1 END WHERE name=? AND zone=?',(name,zone))
        self.db.commit()

    def get(self,k,default=''):
        r=self.db.execute('SELECT value FROM settings WHERE key=?',(k,)).fetchone()
        return r[0] if r else default

    def set(self,k,v):
        self.db.execute('INSERT OR REPLACE INTO settings VALUES (?,?)',(k,str(v)))
        self.db.commit()

    def alarms(self):
        return self.db.execute(
            'SELECT id,title,city,zone,local_at,enabled,fired FROM alarms ORDER BY local_at'
        ).fetchall()

    def add_alarm(self,title,city,zone,local_at):
        self.db.execute(
            'INSERT INTO alarms(title,city,zone,local_at,enabled,fired) VALUES (?,?,?,?,1,0)',
            (title,city,zone,local_at)
        )
        self.db.commit()

    def delete_alarm(self,alarm_id):
        self.db.execute('DELETE FROM alarms WHERE id=?',(alarm_id,))
        self.db.commit()

    def due_alarms(self,now_utc):
        due = self.db.execute(
            'SELECT id,title,city,zone,local_at FROM alarms WHERE enabled=1 AND fired=0'
        ).fetchall()
        result=[]
        for row in due:
            alarm_id,title,city,zone,local_at=row
            try:
                target=datetime.fromisoformat(local_at).replace(tzinfo=ZoneInfo(zone)).astimezone(timezone.utc)
                if target <= now_utc:
                    result.append(row)
            except Exception:
                # Keep malformed entries visible rather than crashing the clock.
                continue
        return result

    def mark_alarm_fired(self,alarm_id):
        self.db.execute('UPDATE alarms SET fired=1 WHERE id=?',(alarm_id,))
        self.db.commit()

    def snooze_alarm(self,alarm_id,local_at):
        self.db.execute('UPDATE alarms SET local_at=?,enabled=1,fired=0 WHERE id=?',(local_at,alarm_id))
        self.db.commit()

    def currency_cache(self, base):
        row = self.db.execute('SELECT rates_json,updated_at FROM currency_cache WHERE base=?', (base,)).fetchone()
        if not row:
            return None
        try:
            return json.loads(row[0]), row[1]
        except (TypeError, ValueError):
            return None

    def save_currency_cache(self, base, rates, updated_at):
        self.db.execute('INSERT OR REPLACE INTO currency_cache(base,rates_json,updated_at) VALUES (?,?,?)',
                        (base, json.dumps(rates, separators=(',', ':')), updated_at))
        self.db.commit()

class RateWorker(QThread):
    completed = Signal(str, dict, str)
    failed = Signal(str, str)

    def __init__(self, base):
        super().__init__()
        self.base = base

    def run(self):
        url = f'https://open.er-api.com/v6/latest/{self.base}'
        request = urllib.request.Request(url, headers={'User-Agent': 'SmartDesk/1.0'})
        try:
            with urllib.request.urlopen(request, timeout=8) as response:
                payload = json.loads(response.read().decode('utf-8'))
            if payload.get('result') != 'success' or not isinstance(payload.get('rates'), dict):
                raise ValueError(payload.get('error-type', 'Unexpected exchange-rate response'))
            rates = {str(k): float(v) for k, v in payload['rates'].items() if isinstance(v, (int, float))}
            stamp = str(payload.get('time_last_update_utc') or datetime.now(timezone.utc).isoformat())
            self.completed.emit(self.base, rates, stamp)
        except Exception as exc:
            self.failed.emit(self.base, str(exc))

class HotkeyBridge(QObject):
    show_currency = Signal()

CURRENCIES = [
    ('AED', 'UAE Dirham', 'د.إ'), ('USD', 'US Dollar', '$'), ('EGP', 'Egyptian Pound', 'E£'),
    ('SAR', 'Saudi Riyal', 'ر.س'), ('EUR', 'Euro', '€'), ('GBP', 'British Pound', '£'),
    ('JPY', 'Japanese Yen', '¥'), ('CAD', 'Canadian Dollar', 'C$'), ('AUD', 'Australian Dollar', 'A$'),
    ('CHF', 'Swiss Franc', 'CHF'), ('CNY', 'Chinese Yuan', '¥'), ('INR', 'Indian Rupee', '₹'),
    ('KWD', 'Kuwaiti Dinar', 'د.ك'), ('QAR', 'Qatari Riyal', 'ر.ق'), ('BHD', 'Bahraini Dinar', 'د.ب'),
    ('OMR', 'Omani Rial', 'ر.ع.'), ('TRY', 'Turkish Lira', '₺'), ('RUB', 'Russian Ruble', '₽'),
]
CURRENCY_SYMBOLS = {code: symbol for code, _name, symbol in CURRENCIES}

class CurrencyPanel(QWidget):
    def __init__(self, store, compact=False, parent=None):
        super().__init__(parent)
        self.store = store
        self.compact = compact
        self.worker = None
        self.rates = {}
        self.rate_updated = ''
        root = QVBoxLayout(self)
        root.setContentsMargins(2 if compact else 14, 2 if compact else 14, 2 if compact else 14, 2 if compact else 14)
        root.setSpacing(6 if compact else 10)
        if not compact:
            heading = QLabel('Convert currencies instantly')
            heading.setStyleSheet('font-size:16pt;font-weight:700;')
            hint = QLabel('Live reference rates with an offline cache. Rates are indicative, not bank or card settlement rates.')
            hint.setObjectName('muted'); hint.setWordWrap(True)
            root.addWidget(heading); root.addWidget(hint)
        form = QGridLayout()
        form.setHorizontalSpacing(8); form.setVerticalSpacing(5)
        self.amount = QDoubleSpinBox(); self.amount.setRange(0, 1_000_000_000); self.amount.setDecimals(2); self.amount.setValue(100); self.amount.setSingleStep(10)
        self.base = QComboBox(); self.target = QComboBox()
        for code, name, _symbol in CURRENCIES:
            label = f'{code} — {name}'
            self.base.addItem(label, code); self.target.addItem(label, code)
        self.base.setCurrentIndex(max(0, self.base.findData('AED')))
        self.target.setCurrentIndex(max(0, self.target.findData('USD')))
        self.swap = QPushButton('⇄ Swap'); self.swap.clicked.connect(self.swap_currencies)
        form.addWidget(QLabel('Amount'), 0, 0); form.addWidget(self.amount, 0, 1, 1, 2)
        form.addWidget(QLabel('From'), 1, 0); form.addWidget(self.base, 1, 1, 1, 2)
        form.addWidget(QLabel('To'), 2, 0); form.addWidget(self.target, 2, 1); form.addWidget(self.swap, 2, 2)
        root.addLayout(form)
        self.result = QLabel('$ —')
        self.result.setStyleSheet('font-size:19pt;font-weight:800;color:#64e0c0;padding:1px 0;' if compact else 'font-size:22pt;font-weight:750;color:#55d6b2;padding:3px 0;')
        self.result.setTextInteractionFlags(Qt.TextSelectableByMouse)
        root.addWidget(self.result)
        actions = QHBoxLayout()
        self.copy_button = QPushButton('Copy with symbol'); self.copy_button.setObjectName('primary'); self.copy_button.clicked.connect(lambda: self.copy_result(True))
        self.copy_plain = QPushButton('Copy amount'); self.copy_plain.clicked.connect(lambda: self.copy_result(False))
        self.refresh_button = QPushButton('Refresh rates'); self.refresh_button.clicked.connect(self.refresh_rates)
        actions.addWidget(self.copy_button); actions.addWidget(self.copy_plain); actions.addWidget(self.refresh_button)
        root.addLayout(actions)
        self.status = QLabel('Loading exchange rates…'); self.status.setObjectName('muted'); self.status.setWordWrap(True); root.addWidget(self.status)
        self.amount.valueChanged.connect(self.calculate)
        self.base.currentIndexChanged.connect(self.base_changed)
        self.target.currentIndexChanged.connect(self.calculate)
        cached = self.store.currency_cache(self.base.currentData())
        if cached:
            self.rates, self.rate_updated = cached
            self.calculate()
            self.status.setText(f'Cached rates · Last update: {self.rate_updated}')
        self.refresh_rates()

    def base_changed(self):
        cached = self.store.currency_cache(self.base.currentData())
        if cached:
            self.rates, self.rate_updated = cached
            self.calculate()
            self.status.setText(f'Cached rates · Last update: {self.rate_updated}')
        else:
            self.rates = {}
            self.calculate()
        self.refresh_rates()

    def swap_currencies(self):
        a, b = self.base.currentData(), self.target.currentData()
        self.base.setCurrentIndex(self.base.findData(b))
        self.target.setCurrentIndex(self.target.findData(a))

    def refresh_rates(self):
        base = self.base.currentData()
        if self.worker and self.worker.isRunning():
            return
        self.refresh_button.setEnabled(False)
        self.status.setText(f'Updating {base} reference rates…')
        self.worker = RateWorker(base)
        self.worker.completed.connect(self.rates_loaded)
        self.worker.failed.connect(self.rates_failed)
        self.worker.finished.connect(lambda: self.refresh_button.setEnabled(True))
        self.worker.start()

    def rates_loaded(self, base, rates, updated):
        self.store.save_currency_cache(base, rates, updated)
        if base == self.base.currentData():
            self.rates, self.rate_updated = rates, updated
            self.calculate()
            self.status.setText(f'Live reference rates · Updated: {updated}')
        else:
            QTimer.singleShot(300, self.refresh_rates)

    def rates_failed(self, failed_base, message):
        if failed_base != self.base.currentData():
            QTimer.singleShot(300, self.refresh_rates)
            return
        cached = self.store.currency_cache(self.base.currentData())
        if cached:
            self.rates, self.rate_updated = cached
            self.calculate()
            self.status.setText(f'Offline mode · Cached rates from {self.rate_updated}. Refresh failed: {message}')
        else:
            self.status.setText(f'Unable to load rates. Check your connection. {message}')
            self.result.setText('Rate unavailable')

    def calculate(self):
        if not self.rates:
            return
        source, target = self.base.currentData(), self.target.currentData()
        rate = self.rates.get(target)
        if rate is None:
            self.result.setText('Rate unavailable'); return
        value = self.amount.value() * rate
        symbol = CURRENCY_SYMBOLS.get(target, target + ' ')
        formatted = f'{symbol}{value:,.2f}' if symbol in ('$','€','£','¥','₹','₺','C$','A$','E£') else f'{value:,.2f} {symbol}'
        self.result.setText(formatted)
        self.result.setProperty('copy_value', formatted)
        self.result.setProperty('copy_plain', f'{value:,.2f}')

    def copy_result(self, with_symbol=True):
        value = self.result.property('copy_value' if with_symbol else 'copy_plain')
        if value:
            QApplication.clipboard().setText(value)
            self.status.setText(f'Copied: {value}')

class CurrencyPopup(QDialog):
    def __init__(self, store, parent=None):
        super().__init__(parent)
        self.drag_position = None
        self.setWindowTitle('SmartDesk · Quick Currency')
        self.setWindowFlags(Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setObjectName('currencyMiniRoot')
        self.setMinimumSize(350, 300)
        self.resize(390, 330)
        self.setStyleSheet("""
            QWidget#currencyMiniRoot { background:#0b1220; color:#e8eef9; font-family:'Segoe UI'; }
            QFrame#currencyMiniPanel { background:#111d30; border:1px solid #263750; border-radius:11px; }
            QLabel#currencyBrand { color:#64e0c0; font-size:8pt; font-weight:800; letter-spacing:1px; }
            QLabel#currencySub { color:#71839d; font-size:7pt; }
            QLabel#currencyResult { color:#64e0c0; font-size:23pt; font-weight:800; padding:4px 0; }
            QLabel#currencyCaption { color:#8ea2bd; font-size:7pt; font-weight:750; letter-spacing:1px; }
            QLabel#currencyStatus { color:#8ea2bd; font-size:7pt; }
            QLabel { color:#dce7f7; }
            QDoubleSpinBox, QComboBox { color:#edf2ff; background:#17263b; border:1px solid #2a3c56;
                border-radius:6px; padding:6px 8px; min-height:25px; selection-background-color:#185f55; }
            QDoubleSpinBox:focus, QComboBox:focus { border:1px solid #55d6b2; }
            QPushButton { color:#c9d6e8; background:#1b2b43; border:1px solid #2b405d;
                border-radius:6px; padding:6px 8px; font-size:8pt; font-weight:650; min-height:25px; }
            QPushButton:hover { background:#263b58; border-color:#4b6b91; }
            QPushButton#currencyPrimary { color:#071b19; background:#64e0c0; border:0; }
            QPushButton#currencyPrimary:hover { background:#83ecd1; }
            QPushButton#currencyClose { font-size:13pt; padding:0; min-height:24px; max-height:24px; }
            QMenu { background:#111b2e; color:#edf2ff; border:1px solid #344761; padding:5px; }
        """)
        root = QVBoxLayout(self)
        root.setContentsMargins(4, 4, 4, 4)
        root.setSpacing(0)
        panel = QFrame()
        panel.setObjectName('currencyMiniPanel')
        body = QVBoxLayout(panel)
        body.setContentsMargins(10, 8, 10, 9)
        body.setSpacing(7)

        header = QHBoxLayout()
        mark = QLabel('$')
        mark.setStyleSheet('color:#64e0c0;font-size:17pt;font-weight:800;')
        header.addWidget(mark)
        brand_col = QVBoxLayout()
        brand_col.setSpacing(0)
        brand = QLabel('QUICK CURRENCY')
        brand.setObjectName('currencyBrand')
        subtitle = QLabel('INSTANT EXCHANGE')
        subtitle.setObjectName('currencySub')
        brand_col.addWidget(brand)
        brand_col.addWidget(subtitle)
        header.addLayout(brand_col)
        header.addStretch()
        pin = QPushButton('PIN')
        pin.setToolTip('Keep this converter above other windows')
        pin.clicked.connect(self.toggle_pin)
        self.pin_button = pin
        header.addWidget(pin)
        close = QPushButton('×')
        close.setObjectName('currencyClose')
        close.setFixedWidth(28)
        close.clicked.connect(self.hide)
        header.addWidget(close)
        body.addLayout(header)

        self.panel = CurrencyPanel(store, compact=True, parent=self)
        # Compact mode is styled locally so the full-page converter remains unchanged.
        self.panel.setStyleSheet("""
            QWidget { background:transparent; color:#dce7f7; }
            QLabel#muted { color:#8ea2bd; font-size:7pt; }
            QDoubleSpinBox, QComboBox { color:#edf2ff; background:#17263b; border:1px solid #2a3c56;
                border-radius:6px; padding:5px 7px; min-height:25px; }
            QDoubleSpinBox:focus, QComboBox:focus { border:1px solid #55d6b2; }
            QPushButton { color:#c9d6e8; background:#1b2b43; border:1px solid #2b405d;
                border-radius:6px; padding:5px 6px; font-size:7.5pt; font-weight:650; min-height:25px; }
            QPushButton:hover { background:#263b58; border-color:#4b6b91; }
            QPushButton#primary { color:#071b19; background:#64e0c0; border:0; }
            QLabel { color:#dce7f7; }
        """)
        body.addWidget(self.panel)
        root.addWidget(panel)

    def toggle_pin(self):
        pinned = not bool(self.windowFlags() & Qt.WindowStaysOnTopHint)
        self.setWindowFlag(Qt.WindowStaysOnTopHint, pinned)
        self.pin_button.setText('PINNED' if pinned else 'PIN')
        self.show()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.drag_position = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if self.drag_position is not None and event.buttons() & Qt.LeftButton:
            self.move(event.globalPosition().toPoint() - self.drag_position)
            event.accept()

    def mouseReleaseEvent(self, event):
        self.drag_position = None
        event.accept()

class CityCard(QFrame):
    def __init__(self,name,zone,store):
        super().__init__(); self.setObjectName('card'); self.zone=zone; self.name=name; self.store=store
        lay=QVBoxLayout(self); lay.setContentsMargins(14,12,14,12); lay.setSpacing(3)
        top=QHBoxLayout(); title=QLabel(name.upper()); title.setStyleSheet('color:#55d6b2;font-weight:700;letter-spacing:1px')
        self.zone_label=QLabel(zone); self.zone_label.setObjectName('muted'); self.zone_label.setText(zone); self.zone_label.setToolTip(zone); top.addWidget(title); top.addStretch(); lay.addLayout(top)
        self.clock=QLabel('--:--:--'); self.clock.setObjectName('clock'); lay.addWidget(self.clock)
        self.date=QLabel(''); self.date.setObjectName('muted'); lay.addWidget(self.date)
        self.offset=QLabel(''); self.offset.setObjectName('muted'); lay.addWidget(self.offset); self.refresh()
    def refresh(self):
        try: dt=datetime.now(timezone.utc).astimezone(ZoneInfo(self.zone))
        except Exception: return
        if self.store.get('time_format','12')=='24': self.clock.setText(dt.strftime('%H:%M:%S'))
        else: self.clock.setText(dt.strftime('%I:%M:%S %p').lstrip('0'))
        self.date.setText(dt.strftime('%A, %d %B %Y'))
        off=dt.strftime('%z'); self.offset.setText('UTC' + off[:3] + ':' + off[3:] if off else 'UTC')

class FloatingWidget(QWidget):
    def __init__(self,store,host):
        super().__init__(None, Qt.Tool | Qt.FramelessWindowHint)
        self.store=store; self.host=host; self.pinned=False; self.drag=None
        self.setWindowTitle('WorldClock Mini')
        self.setMinimumSize(260,120); self.resize(310,188); self.compact=True
        self.setWindowOpacity(max(0.90, float(store.get('opacity','1.0'))))
        self.setStyleSheet("""
            QWidget#miniRoot { background:#0b1220; color:#e8eef9; font-family:'Segoe UI'; }
            QFrame#miniPanel { background:#111d30; border:1px solid #263750; border-radius:10px; }
            QFrame#miniCard { background:#17263b; border:1px solid #2a3c56; border-radius:8px; }
            QLabel#brand { color:#64e0c0; font-size:8pt; font-weight:800; letter-spacing:1px; }
            QLabel#eyebrow { color:#8ea2bd; font-size:7.5pt; font-weight:700; }
            QLabel#city { color:#dce7f7; font-size:7.5pt; font-weight:700; }
            QLabel#time { color:#ffffff; font-size:14pt; font-weight:750; }
            QLabel#date { color:#a9bad0; font-size:8pt; }
            QLabel#offset { color:#6fdcc0; font-size:7.5pt; font-weight:700; }
            QLabel#period { color:#f4c979; font-size:7pt; font-weight:800; }
            QLabel#home { color:#64e0c0; font-size:7pt; font-weight:800; }
            QLabel#muted { color:#71839d; font-size:7.5pt; }
            QPushButton { color:#c9d6e8; background:#1b2b43; border:1px solid #2b405d;
                border-radius:5px; padding:2px 5px; font-size:7pt; font-weight:650; }
            QPushButton:hover { background:#263b58; border-color:#4b6b91; }
            QPushButton#close { font-size:12pt; padding:1px 8px; }
            QPushButton#open { color:#071b19; background:#64e0c0; border:0; }
            QPushButton#open:hover { background:#83ecd1; }
        """)
        self.setObjectName('miniRoot')
        root=QVBoxLayout(self); root.setContentsMargins(4,4,4,4); root.setSpacing(2)
        panel=QFrame(); panel.setObjectName('miniPanel')
        outer=QVBoxLayout(panel); outer.setContentsMargins(6,5,6,5); outer.setSpacing(4)
        head=QHBoxLayout()
        mark=QLabel('◷'); mark.setStyleSheet('color:#64e0c0;font-size:14pt;font-weight:700;')
        head.addWidget(mark)
        brand_col=QVBoxLayout(); brand_col.setSpacing(0)
        self.brand=QLabel('WORLD CLOCK'); self.brand.setObjectName('brand'); brand=self.brand
        self.subtitle=QLabel('WORLD TIME AT A GLANCE'); self.subtitle.setObjectName('muted'); sub=self.subtitle
        brand_col.addWidget(brand); brand_col.addWidget(sub); head.addLayout(brand_col); head.addStretch()
        self.pin=QPushButton('PIN'); self.pin.clicked.connect(self.toggle_pin); head.addWidget(self.pin)
        close=QPushButton('×'); close.setObjectName('close'); close.setFixedWidth(30); close.clicked.connect(self.hide); head.addWidget(close)
        outer.addLayout(head)
        self.cards_layout=QGridLayout(); self.cards_layout.setHorizontalSpacing(4); self.cards_layout.setVerticalSpacing(4)
        outer.addLayout(self.cards_layout)
        foot=QHBoxLayout()
        foot.addStretch()
        addb=QPushButton('+'); addb.clicked.connect(self.add_city)
        foot.addWidget(addb)
        openb=QPushButton('DASHBOARD ↗'); openb.setObjectName('open'); openb.clicked.connect(self.host.show_dashboard)
        self.open_button=openb; foot.addWidget(openb); outer.addLayout(foot)
        root.addWidget(panel)
        self.refresh_cities()


    def apply_language(self,language):
        labels={
            'ru': {'WORLD CLOCK':'МИРОВЫЕ ЧАСЫ','WORLD TIME AT A GLANCE':'МИРОВОЕ ВРЕМЯ',
                   'PIN':'ЗАКРЕПИТЬ','PINNED':'ЗАКРЕПЛЕНО','DASHBOARD ↗':'ПАНЕЛЬ ↗',
                   'Add cities from the main dashboard to see them here.':'Добавьте города на главной панели.'},
            'de': {'WORLD CLOCK':'WELTUHR','WORLD TIME AT A GLANCE':'WELTZEIT AUF EINEN BLICK',
                   'PIN':'FIXIEREN','PINNED':'FIXIERT','DASHBOARD ↗':'ÜBERSICHT ↗',
                   'Add cities from the main dashboard to see them here.':'Fügen Sie Städte im Dashboard hinzu.'},
            'fr': {'WORLD CLOCK':'HORLOGE MONDIALE','WORLD TIME AT A GLANCE':'HEURE MONDIALE EN UN COUP D’ŒIL',
                   'PIN':'ÉPINGLER','PINNED':'ÉPINGLÉ','DASHBOARD ↗':'TABLEAU ↗',
                   'Add cities from the main dashboard to see them here.':'Ajoutez des villes depuis le tableau de bord.'},
            'es': {'WORLD CLOCK':'RELOJ MUNDIAL','WORLD TIME AT A GLANCE':'HORA MUNDIAL DE UN VISTAZO',
                   'PIN':'FIJAR','PINNED':'FIJADO','DASHBOARD ↗':'PANEL ↗',
                   'Add cities from the main dashboard to see them here.':'Añade ciudades desde el panel principal.'},
            'it': {'WORLD CLOCK':'OROLOGIO MONDIALE','WORLD TIME AT A GLANCE':'ORA MONDIALE A COLPO D’OCCHIO',
                   'PIN':'FISSA','PINNED':'FISSATO','DASHBOARD ↗':'PANNELLO ↗',
                   'Add cities from the main dashboard to see them here.':'Aggiungi città dalla dashboard.'},
            'en': {'WORLD CLOCK':'WORLD CLOCK','WORLD TIME AT A GLANCE':'WORLD TIME AT A GLANCE',
                   'PIN':'PIN','PINNED':'PINNED','DASHBOARD ↗':'DASHBOARD ↗',
                   'Add cities from the main dashboard to see them here.':'Add cities from the main dashboard to see them here.'}
        }
        labels=labels.get(language,labels['en'])
        self.brand.setText(labels['WORLD CLOCK'])
        self.subtitle.setText(labels['WORLD TIME AT A GLANCE'])
        self.pin.setText(labels['PINNED'] if self.pinned else labels['PIN'])
        self.open_button.setText(labels['DASHBOARD ↗'])
        if not self.cards:
            item=self.cards_layout.itemAt(0)
            if item and item.widget():
                item.widget().setText(labels['Add cities from the main dashboard to see them here.'])

    def refresh_cities(self):
        while self.cards_layout.count():
            item=self.cards_layout.takeAt(0); w=item.widget()
            if w: w.deleteLater()
        self.cards=[]
        home_zone=self.store.get('home_zone','')
        for i,(name,zone) in enumerate(self.store.cities()[:4]):
            card=QFrame(); card.setObjectName('miniCard')
            layout=QVBoxLayout(card); layout.setContentsMargins(6,4,6,4); layout.setSpacing(1)
            top=QHBoxLayout()
            city=QLabel(name.upper()); city.setObjectName('city'); city.setMaximumWidth(105); top.addWidget(city); top.addStretch()
            period=QLabel(''); period.setObjectName('period'); period.hide()
            offset=QLabel(''); offset.setObjectName('offset'); top.addWidget(offset)
            layout.addLayout(top)
            tm=QLabel('--:--'); tm.setObjectName('time'); layout.addWidget(tm)
            date=QLabel(''); date.setObjectName('date'); layout.addWidget(date)
            self.cards.append((zone,tm,date,offset,period))
            self.cards_layout.addWidget(card,i//2,i%2)
        if not self.cards:
            empty=QLabel('Add cities from the main dashboard to see them here.')
            empty.setObjectName('muted'); empty.setWordWrap(True)
            self.cards_layout.addWidget(empty,0,0,1,2)
        self.refresh()

    def refresh(self):
        home_zone=self.store.get('home_zone','')
        for zone,tm,date,offset,period in self.cards:
            try: d=datetime.now(timezone.utc).astimezone(ZoneInfo(zone))
            except Exception: continue
            is24=self.store.get('time_format','12')=='24'
            tm.setText(d.strftime('%H:%M:%S') if is24 else d.strftime('%I:%M:%S %p').lstrip('0'))
            date.setText(d.strftime('%a, %d %b'))
            off=d.strftime('%z')
            offset.setText('UTC'+off[:3]+':'+off[3:] if off else 'UTC')
            period.setText('DAY' if 6 <= d.hour < 18 else 'NIGHT')
            date.hide()

    def add_city(self):
        raw,ok=QInputDialog.getText(
            self,'Add a city',
            'Enter a city name or time zone (e.g. Paris or Europe/Paris):'
        )
        if not ok or not raw.strip():
            return
        query=raw.strip().casefold()
        matches=[]
        for label,zone,city in TIMEZONE_CATALOG:
            if query in label.casefold() or query in city.casefold() or query == zone.casefold():
                matches.append((city,zone))
        aliases=[
            ('Jeddah','Asia/Riyadh'),('Riyadh','Asia/Riyadh'),
            ('Mecca','Asia/Riyadh'),('Medina','Asia/Riyadh'),
            ('Dammam','Asia/Riyadh'),('Taif','Asia/Riyadh'),
            ('Al Khobar','Asia/Riyadh'),('Alexandria','Africa/Cairo'),
            ('Giza','Africa/Cairo'),('Dubai','Asia/Dubai'),
            ('Abu Dhabi','Asia/Dubai')
        ]
        for city,zone in aliases:
            if query in city.casefold():
                matches.append((city,zone))
        # Preserve order and avoid duplicate city/time-zone pairs.
        matches=list(dict.fromkeys(matches))
        if not matches:
            QMessageBox.information(
                self,'City not found',
                'No matching city or time zone was found. Try an IANA zone such as Europe/Paris.'
            )
            return
        if len(matches)>1:
            labels=[f'{city} — {zone}' for city,zone in matches[:100]]
            chosen,ok=QInputDialog.getItem(self,'Choose a location','Matching locations:',labels,0,False)
            if not ok:
                return
            city,zone=matches[labels.index(chosen)]
        else:
            city,zone=matches[0]
        self.store.add_city(city,zone)
        self.host.refresh_world()

    def toggle_pin(self):
        self.pinned=not self.pinned
        self.setWindowFlag(Qt.WindowStaysOnTopHint,self.pinned)
        self.show()
        if self.pinned:
            screen=QGuiApplication.screenAt(self.frameGeometry().center()) or QGuiApplication.primaryScreen()
            if screen:
                area=screen.availableGeometry()
                margin=12
                self.move(area.right()-self.width()-margin, area.top()+margin)
        self.pin.setText('PINNED' if self.pinned else 'PIN')

    def mousePressEvent(self,e):
        if e.button()==Qt.LeftButton:
            self.drag=e.globalPosition().toPoint()-self.frameGeometry().topLeft(); e.accept()
    def mouseMoveEvent(self,e):
        if self.drag is not None and e.buttons() & Qt.LeftButton:
            self.move(e.globalPosition().toPoint()-self.drag); e.accept()
    def mouseReleaseEvent(self,e): self.drag=None


class NavigationWorkspace(QWidget):
    """Sidebar navigation + stacked pages, compatible with the former QTabWidget API."""
    NAV_ICONS = {
        'World clock': '◷', 'Time converter': '⇄', 'Currency converter': '$',
        'Meeting planner': '▦', 'Time comparison': '◴', 'World alarms': '◉',
        'Quick tools': '⌘', 'QR generator': '▦', 'Clipboard': '▤', 'Settings': '⚙'
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName('navigationWorkspace')
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)
        self.navigation = QListWidget()
        self.navigation.setObjectName('mainNavigation')
        self.navigation.setFrameShape(QFrame.NoFrame)
        self.navigation.setFixedWidth(184)
        self.navigation.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.navigation.setSpacing(3)
        self.pages = QStackedWidget()
        self.pages.setObjectName('workspacePages')
        layout.addWidget(self.navigation)
        layout.addWidget(self.pages, 1)
        self.navigation.currentRowChanged.connect(self.pages.setCurrentIndex)

    def addTab(self, page, label):
        icon = self.NAV_ICONS.get(label, '•')
        item = QListWidgetItem(f'{icon}    {label}')
        item.setData(Qt.UserRole, label)
        item.setSizeHint(QSize(166, 42))
        self.navigation.addItem(item)
        self.pages.addWidget(page)
        if self.navigation.count() == 1:
            self.navigation.setCurrentRow(0)
        return self.pages.count() - 1

    def count(self):
        return self.pages.count()

    def widget(self, index):
        return self.pages.widget(index)

    def currentIndex(self):
        return self.pages.currentIndex()

    def setCurrentIndex(self, index):
        self.navigation.setCurrentRow(index)

    def tabText(self, index):
        item = self.navigation.item(index)
        return item.data(Qt.UserRole) if item else ''

    def setTabText(self, index, label):
        item = self.navigation.item(index)
        if item:
            icon = self.NAV_ICONS.get(label, '•')
            item.setText(f'{icon}    {label}')
            item.setData(Qt.UserRole, label)

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__(); self.store=Store(); self.setWindowTitle(f'SmartDesk · WorldClock v{APP_VERSION}')
        screen=QGuiApplication.primaryScreen()
        area=screen.availableGeometry() if screen else None
        if area:
            width=min(1040,max(760,int(area.width()*0.86)))
            height=min(680,max(540,int(area.height()*0.78)))
            self.resize(width,height)
            self.setMinimumSize(min(720,width),min(520,height))
            self.move(area.x()+(area.width()-width)//2,area.y()+(area.height()-height)//2)
        else:
            self.resize(1000,700); self.setMinimumSize(720,520)
        self.setStyleSheet(DARK); self.cards=[]
        central=QWidget(); self.setCentralWidget(central); root=QVBoxLayout(central); root.setContentsMargins(14,10,14,12); root.setSpacing(8)
        header=QHBoxLayout(); header.setSpacing(10); title=QLabel('SmartDesk'); title.setStyleSheet('font-size:20pt;font-weight:750; letter-spacing:-0.5px;'); subtitle=QLabel('  YOUR TIME, MONEY & PRODUCTIVITY'); subtitle.setObjectName('muted'); header.addWidget(title); header.addWidget(subtitle); header.addStretch()
        self.language_flags={'en':'gb','ru':'ru','de':'de','fr':'fr','es':'es','it':'it'}
        self.language_items=[('English','en'),('Русский','ru'),('Deutsch','de'),('Français','fr'),('Español','es'),('Italiano','it')]
        self.flag_pixmaps={key:self.create_flag_pixmap(key) for key in self.language_flags}
        self.lang_button=QToolButton(); self.lang_button.setObjectName('languageSelector')
        self.lang_button.setPopupMode(QToolButton.InstantPopup)
        self.lang_button.setToolButtonStyle(Qt.ToolButtonIconOnly); self.lang_button.setFixedSize(44, 38); self.lang_button.setIconSize(QSize(28, 18)); self.lang_button.setToolTip('Change language')
        self.lang_menu=QMenu(self.lang_button); self.lang_group=QActionGroup(self.lang_menu); self.lang_group.setExclusive(True)
        for label,lang_code in self.language_items:
            action=QAction(QIcon(self.flag_pixmaps[lang_code]),label,self.lang_menu)
            action.setCheckable(True); action.setData(lang_code)
            action.triggered.connect(lambda checked=False, code=lang_code:self.change_language_code(code))
            self.lang_group.addAction(action); self.lang_menu.addAction(action)
        self.lang_button.setMenu(self.lang_menu); self.update_language_button(self.store.get('language','en'))
        header.addWidget(self.lang_button)
        self.mini_btn=QPushButton('Open mini clock'); self.mini_btn.clicked.connect(self.show_mini); header.addWidget(self.mini_btn)
        self.currency_popup_btn=QPushButton('Quick currency'); self.currency_popup_btn.setObjectName('quickCurrencyButton'); self.currency_popup_btn.setToolTip('Open the floating currency converter · Alt + Shift + C')
        self.currency_popup_btn.clicked.connect(self.show_currency_popup); header.addWidget(self.currency_popup_btn)
        root.addLayout(header)
        self.tabs=NavigationWorkspace(); root.addWidget(self.tabs, 1); self.setStatusBar(QStatusBar())
        self.build_world_tab(); self.build_converter_tab(); self.build_currency_tab(); self.build_meeting_tab(); self.build_comparison_tab(); self.build_alarms_tab(); self.build_tools_tab(); self.build_qr_tab(); self.build_clipboard_tab(); self.build_settings_tab()
        self.currency_popup=CurrencyPopup(self.store,self)
        self.mini=FloatingWidget(self.store,self)
        self.timer=QTimer(self); self.timer.timeout.connect(self.tick); self.timer.start(1000); self.refresh_world()
        self.create_tray()
        self.install_currency_hotkey()
        self.apply_language(self.store.get('language','en'))
        if self.store.get('show_mini','1')=='1': self.mini.show()
    def build_world_tab(self):
        tab=QWidget(); lay=QVBoxLayout(tab); lay.setSpacing(12)
        intro=QLabel('Your saved places'); intro.setStyleSheet('font-size:15pt;font-weight:650;color:#edf2ff;')
        hint=QLabel('Search by city, country or IANA time zone. The catalog includes the full installed time-zone database.')
        hint.setObjectName('muted'); lay.addWidget(intro); lay.addWidget(hint)
        bar=QHBoxLayout(); self.search=QLineEdit()
        self.search.setPlaceholderText('Search any country or city… e.g. Japan, Paris, New York, Asia/Tokyo')
        self.search.setClearButtonEnabled(True)
        comp=QCompleter(CITY_NAMES,self); comp.setCaseSensitivity(Qt.CaseInsensitive); comp.setFilterMode(Qt.MatchContains)
        comp.setCompletionMode(QCompleter.PopupCompletion); comp.setMaxVisibleItems(14)
        comp.popup().setStyleSheet('QListView{background:#111b2e;color:#edf2ff;border:1px solid #344761;padding:5px;} QListView::item{padding:7px 9px;border-radius:5px;} QListView::item:selected{background:#24594f;color:white;}')
        self.search.setCompleter(comp); self.search.returnPressed.connect(self.add_city); comp.activated.connect(lambda _text:self.add_city())
        bar.addWidget(self.search,1)
        add=QPushButton('＋  Add location'); add.setObjectName('primary'); add.clicked.connect(self.add_city); bar.addWidget(add)
        lay.addLayout(bar)
        split=QSplitter(); split.setChildrenCollapsible(False)
        self.city_list=QListWidget(); self.city_list.setMaximumWidth(250); self.city_list.setMinimumWidth(190)
        self.city_list.currentRowChanged.connect(self.select_city); split.addWidget(self.city_list)
        self.world_scroll=QScrollArea(); self.world_scroll.setWidgetResizable(True); self.world_scroll.setFrameShape(QFrame.NoFrame)
        right=QWidget(); self.world_grid=QGridLayout(right); self.world_grid.setContentsMargins(4,4,8,4); self.world_grid.setAlignment(Qt.AlignTop); self.world_grid.setSpacing(12)
        self.world_scroll.setWidget(right); split.addWidget(self.world_scroll)
        split.setStretchFactor(0,0); split.setStretchFactor(1,1); split.setSizes([220,700]); lay.addWidget(split,1)
        actions=QHBoxLayout(); self.remove_btn=QPushButton('Remove selected'); self.remove_btn.setObjectName('danger'); self.remove_btn.clicked.connect(self.remove_city)
        self.favorite_btn=QPushButton('☆ Toggle favorite'); self.favorite_btn.clicked.connect(self.toggle_favorite); actions.addWidget(self.favorite_btn)
        self.up_btn=QPushButton('↑ Move up'); self.up_btn.clicked.connect(lambda:self.move_city(-1))
        self.down_btn=QPushButton('↓ Move down'); self.down_btn.clicked.connect(lambda:self.move_city(1))
        actions.addWidget(self.remove_btn); actions.addWidget(self.up_btn); actions.addWidget(self.down_btn); actions.addStretch()
        lay.addLayout(actions); self.tabs.addTab(tab,'World clock')
    def build_converter_tab(self):
        tab=QWidget(); lay=QVBoxLayout(tab); intro=QLabel('Convert a local date and time into every city you follow.'); intro.setObjectName('muted'); lay.addWidget(intro)
        form=QFormLayout(); self.conv_city=QComboBox(); self.conv_dt=QDateTimeEdit(QDateTime.currentDateTime()); self.conv_dt.setCalendarPopup(True); self.conv_dt.setDisplayFormat('yyyy-MM-dd  HH:mm'); form.addRow('Time in:',self.conv_city); form.addRow('Date & time:',self.conv_dt); lay.addLayout(form)
        b=QPushButton('Convert time'); b.setObjectName('primary'); b.clicked.connect(self.convert_time); lay.addWidget(b,0,Qt.AlignLeft)
        self.conv_table=QTableWidget(0,3); self.conv_table.setHorizontalHeaderLabels(['City','Local date & time','UTC offset']); self.conv_table.horizontalHeader().setStretchLastSection(True); lay.addWidget(self.conv_table,1); self.tabs.addTab(tab,'Time converter')
    def build_currency_tab(self):
        self.currency_panel = CurrencyPanel(self.store, parent=self)
        self.tabs.addTab(self.currency_panel, 'Currency converter')

    def build_tools_tab(self):
        tab = QWidget(); root = QVBoxLayout(tab); root.setSpacing(12)
        intro = QLabel('Everyday tools'); intro.setStyleSheet('font-size:16pt;font-weight:700;')
        root.addWidget(intro)
        unit = QGroupBox('Unit converter'); form = QGridLayout(unit)
        self.unit_value = QDoubleSpinBox(); self.unit_value.setRange(-1_000_000_000, 1_000_000_000); self.unit_value.setDecimals(4); self.unit_value.setValue(1)
        self.unit_kind = QComboBox(); self.unit_kind.addItems(['Kilometres → Miles','Miles → Kilometres','Kilograms → Pounds','Pounds → Kilograms','Centimetres → Inches','Inches → Centimetres','Celsius → Fahrenheit','Fahrenheit → Celsius','Litres → US Gallons','US Gallons → Litres'])
        self.unit_result = QLabel('0.6214'); self.unit_result.setStyleSheet('font-size:18pt;font-weight:700;color:#55d6b2;')
        self.unit_value.valueChanged.connect(self.update_unit_result); self.unit_kind.currentIndexChanged.connect(self.update_unit_result)
        form.addWidget(QLabel('Value'),0,0); form.addWidget(self.unit_value,0,1); form.addWidget(QLabel('Conversion'),1,0); form.addWidget(self.unit_kind,1,1); form.addWidget(QLabel('Result'),2,0); form.addWidget(self.unit_result,2,1)
        root.addWidget(unit)
        calc = QGroupBox('Quick calculator'); calc_lay = QHBoxLayout(calc)
        self.calc_input = QLineEdit(); self.calc_input.setPlaceholderText('Example: (125 * 1.05) + 20')
        calc_btn = QPushButton('Calculate'); calc_btn.setObjectName('primary'); calc_btn.clicked.connect(self.calculate_expression)
        self.calc_result = QLabel('Result will appear here'); self.calc_result.setObjectName('muted')
        calc_lay.addWidget(self.calc_input,2); calc_lay.addWidget(calc_btn); calc_lay.addWidget(self.calc_result,2)
        root.addWidget(calc)
        text_tools = QGroupBox('Text tools'); text_lay = QVBoxLayout(text_tools)
        self.text_input = QPlainTextEdit(); self.text_input.setPlaceholderText('Enter text to transform…'); self.text_input.setMaximumHeight(90)
        row = QHBoxLayout()
        for label, mode in [('UPPERCASE','upper'),('lowercase','lower'),('Title Case','title'),('Base64 Encode','b64e'),('Base64 Decode','b64d')]:
            btn=QPushButton(label); btn.clicked.connect(lambda _checked=False,m=mode:self.transform_text(m)); row.addWidget(btn)
        self.text_output = QLineEdit(); self.text_output.setReadOnly(True); self.text_output.setPlaceholderText('Output')
        copy = QPushButton('Copy output'); copy.clicked.connect(lambda: QApplication.clipboard().setText(self.text_output.text()) if self.text_output.text() else None)
        text_lay.addWidget(self.text_input); text_lay.addLayout(row); text_lay.addWidget(self.text_output); text_lay.addWidget(copy,0,Qt.AlignRight)
        root.addWidget(text_tools); root.addStretch()
        self.tabs.addTab(tab,'Quick tools')

    def build_qr_tab(self):
        tab=QWidget(); root=QVBoxLayout(tab)
        title=QLabel('QR code generator'); title.setStyleSheet('font-size:16pt;font-weight:700;')
        hint=QLabel('Create a QR code from a URL, text, contact details or Wi-Fi information.'); hint.setObjectName('muted')
        self.qr_input=QPlainTextEdit(); self.qr_input.setPlaceholderText('Paste a URL or enter text…'); self.qr_input.setMaximumHeight(88)
        actions=QHBoxLayout()
        make=QPushButton('Generate QR now'); make.setObjectName('primary'); make.clicked.connect(self.generate_qr); actions.addWidget(make)
        save=QPushButton('Save PNG'); save.clicked.connect(self.save_qr); actions.addWidget(save)
        clear=QPushButton('Clear'); clear.clicked.connect(self.qr_input.clear); actions.addWidget(clear); actions.addStretch()
        self.qr_preview=QLabel('Your QR code will appear here as you type')
        self.qr_preview.setAlignment(Qt.AlignCenter); self.qr_preview.setMinimumSize(430,430); self.qr_preview.setMaximumSize(500,500)
        self.qr_preview.setStyleSheet('background:#ffffff;color:#526078;border:1px solid #30445f;border-radius:12px;padding:8px;')
        self.qr_status=QLabel('Enter text or a URL. QR preview updates automatically.'); self.qr_status.setObjectName('muted')
        root.addWidget(title); root.addWidget(hint); root.addWidget(self.qr_input); root.addLayout(actions)
        root.addWidget(self.qr_preview,0,Qt.AlignHCenter); root.addWidget(self.qr_status,0,Qt.AlignHCenter); root.addStretch()
        self.qr_pixmap=None
        self.qr_timer=QTimer(self); self.qr_timer.setSingleShot(True); self.qr_timer.setInterval(350)
        self.qr_timer.timeout.connect(self.generate_qr); self.qr_input.textChanged.connect(lambda:self.qr_timer.start())
        self.tabs.addTab(tab,'QR generator')

    def generate_qr(self):
        value = self.qr_input.toPlainText().strip()
        if not value:
            self.qr_pixmap = None
            self.qr_preview.clear()
            self.qr_preview.setText('Your QR code will appear here as you type')
            self.qr_status.setText('Enter text or a URL to create a QR code.')
            return

        try:
            import qrcode

            qr = qrcode.QRCode(
                version=None,
                error_correction=qrcode.constants.ERROR_CORRECT_H,
                box_size=1,
                border=4
            )
            qr.add_data(value)
            qr.make(fit=True)
            matrix = qr.get_matrix()

            # Render the boolean module matrix directly into a Qt image.
            # This deliberately avoids Pillow wrappers, PNG byte signatures,
            # and Qt's PNG decoder, which caused the blank preview.
            module_count = len(matrix)
            scale = max(2, min(16, 480 // max(1, module_count)))
            image_size = module_count * scale
            image = QImage(image_size, image_size, QImage.Format_RGB32)
            if image.isNull():
                raise RuntimeError('Qt could not allocate the QR image buffer.')
            image.fill(QColor('#FFFFFF'))

            painter = QPainter(image)
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor('#000000'))
            for row_index, row in enumerate(matrix):
                for col_index, is_dark in enumerate(row):
                    if is_dark:
                        painter.drawRect(
                            col_index * scale,
                            row_index * scale,
                            scale,
                            scale
                        )
            painter.end()

            pixmap = QPixmap.fromImage(image)
            if pixmap.isNull() or pixmap.width() == 0 or pixmap.height() == 0:
                raise RuntimeError('Qt could not create a displayable QR preview.')

            self.qr_pixmap = pixmap
            self.qr_preview.clear()
            # Keep the QR at its native module resolution. Fractional downscaling
            # can soften module edges and make camera scanning less reliable.
            self.qr_preview.setPixmap(pixmap)
            self.qr_preview.setToolTip(value)
            self.qr_status.setText(
                f'QR ready · {len(value)} characters · {pixmap.width()} × {pixmap.height()} px'
            )

        except ImportError:
            self.qr_pixmap = None
            self.qr_preview.clear()
            self.qr_preview.setText('QR library is not installed')
            self.qr_status.setText(
                'Missing qrcode dependency. Run Install.bat again.'
            )
        except Exception as exc:
            self.qr_pixmap = None
            self.qr_preview.clear()
            self.qr_preview.setText('QR generation failed')
            self.qr_status.setText(
                f'Could not generate QR code: {type(exc).__name__}: {exc}'
            )

    def save_qr(self):
        if self.qr_pixmap is None:
            self.generate_qr()
        if self.qr_pixmap is None: return
        from PySide6.QtWidgets import QFileDialog
        path,_=QFileDialog.getSaveFileName(self,'Save QR code','smartdesk-qr.png','PNG image (*.png)')
        if path:
            if self.qr_pixmap is None or self.qr_pixmap.isNull():
                self.qr_status.setText('No valid QR image is available to save.')
                return
            if self.qr_pixmap.save(path, 'PNG'):
                self.qr_status.setText(f'Saved QR image: {path}')
            else:
                self.qr_status.setText('Could not save the QR image. Check the destination folder permissions.')

    def build_clipboard_tab(self):
        tab=QWidget(); root=QVBoxLayout(tab)
        title=QLabel('Clipboard history'); title.setStyleSheet('font-size:16pt;font-weight:700;')
        warning=QLabel('Clipboard monitoring is OFF by default. Turn it on only when you want SmartDesk to collect copied text during this session. History stays in memory and is cleared when the app closes.'); warning.setObjectName('muted'); warning.setWordWrap(True)
        self.clipboard_optin=QCheckBox('Enable clipboard history for this session')
        self.clipboard_list=QListWidget(); self.clipboard_list.itemDoubleClicked.connect(lambda item: QApplication.clipboard().setText(item.text()))
        actions=QHBoxLayout(); copy=QPushButton('Copy selected'); copy.clicked.connect(self.copy_clipboard_item); actions.addWidget(copy)
        clear=QPushButton('Clear history'); clear.clicked.connect(self.clipboard_list.clear); actions.addWidget(clear); actions.addStretch()
        self.clipboard_timer=QTimer(self); self.clipboard_timer.setInterval(700); self.clipboard_timer.timeout.connect(self.capture_clipboard)
        self.clipboard_optin.toggled.connect(lambda enabled:self.clipboard_timer.start() if enabled else self.clipboard_timer.stop())
        root.addWidget(title); root.addWidget(warning); root.addWidget(self.clipboard_optin); root.addWidget(self.clipboard_list,1); root.addLayout(actions)
        self.last_clipboard=''
        self.tabs.addTab(tab,'Clipboard')

    def capture_clipboard(self):
        value=QApplication.clipboard().text().strip()
        if not value or value==self.last_clipboard: return
        self.last_clipboard=value
        if len(value)>4000: value=value[:4000]+'…'
        self.clipboard_list.insertItem(0,value)
        while self.clipboard_list.count()>50: self.clipboard_list.takeItem(self.clipboard_list.count()-1)

    def copy_clipboard_item(self):
        item=self.clipboard_list.currentItem()
        if item: QApplication.clipboard().setText(item.text())

    def update_unit_result(self):
        value=self.unit_value.value(); index=self.unit_kind.currentIndex()
        operations=[lambda x:x*0.621371,lambda x:x/0.621371,lambda x:x*2.2046226218,lambda x:x/2.2046226218,lambda x:x/2.54,lambda x:x*2.54,lambda x:x*9/5+32,lambda x:(x-32)*5/9,lambda x:x*0.2641720524,lambda x:x/0.2641720524]
        self.unit_result.setText(f'{operations[index](value):,.4f}'.rstrip('0').rstrip('.'))

    def calculate_expression(self):
        import ast, operator
        ops={ast.Add:operator.add,ast.Sub:operator.sub,ast.Mult:operator.mul,ast.Div:operator.truediv,ast.Pow:operator.pow,ast.USub:operator.neg,ast.UAdd:operator.pos,ast.Mod:operator.mod}
        def evaluate(node):
            if isinstance(node,ast.Expression): return evaluate(node.body)
            if isinstance(node,ast.Constant) and isinstance(node.value,(int,float)): return node.value
            if isinstance(node,ast.BinOp) and type(node.op) in ops:
                left,right=evaluate(node.left),evaluate(node.right)
                if isinstance(node.op,ast.Pow) and abs(right)>8: raise ValueError('Exponent must be between -8 and 8.')
                return ops[type(node.op)](left,right)
            if isinstance(node,ast.UnaryOp) and type(node.op) in ops: return ops[type(node.op)](evaluate(node.operand))
            raise ValueError('Only numbers and + - * / % ** parentheses are allowed.')
        try:
            if len(self.calc_input.text())>120: raise ValueError('Expression is too long.')
            tree=ast.parse(self.calc_input.text(),mode='eval')
            result=evaluate(tree)
            if not isinstance(result,(int,float)) or abs(result)>1e100: raise ValueError('Result is outside the supported range.')
            self.calc_result.setText(f'= {result:,.10g}')
        except Exception as exc:
            self.calc_result.setText(f'Invalid expression: {exc}')

    def transform_text(self, mode):
        import base64
        value=self.text_input.toPlainText()
        try:
            if mode=='upper': result=value.upper()
            elif mode=='lower': result=value.lower()
            elif mode=='title': result=value.title()
            elif mode=='b64e': result=base64.b64encode(value.encode('utf-8')).decode('ascii')
            else: result=base64.b64decode(value.encode('ascii'),validate=True).decode('utf-8')
            self.text_output.setText(result)
        except Exception as exc:
            self.text_output.setText(f'Error: {exc}')

    def install_currency_hotkey(self):
        self.hotkey_module = None
        self.hotkey_bridge = HotkeyBridge(self)
        self.hotkey_bridge.show_currency.connect(self.show_currency_popup)
        try:
            import keyboard
            self.hotkey_module = keyboard
            keyboard.add_hotkey('alt+shift+c', self.hotkey_bridge.show_currency.emit)
            self.statusBar().showMessage('Currency popup shortcut: Alt + Shift + C', 7000)
        except Exception:
            self.statusBar().showMessage('Global popup shortcut unavailable. Install the keyboard package; use the tray menu meanwhile.', 9000)

    def show_currency_popup(self):
        self.currency_popup.show(); self.currency_popup.raise_(); self.currency_popup.activateWindow()
        self.currency_popup.move(QGuiApplication.primaryScreen().availableGeometry().center() - self.currency_popup.rect().center())

    def build_meeting_tab(self):
        tab=QWidget(); lay=QVBoxLayout(tab); lay.addWidget(QLabel('Find a suitable meeting time across your selected cities.'))
        form=QFormLayout(); self.meet_base=QComboBox(); self.meet_dt=QDateTimeEdit(QDateTime.currentDateTime().addDays(1)); self.meet_dt.setCalendarPopup(True); self.meet_dt.setDisplayFormat('yyyy-MM-dd  HH:mm'); form.addRow('Reference city:',self.meet_base); form.addRow('Meeting time:',self.meet_dt); lay.addLayout(form)
        buttons=QHBoxLayout(); b=QPushButton('Compare participant times'); b.setObjectName('primary'); b.clicked.connect(self.plan_meeting); buttons.addWidget(b)
        best=QPushButton('Find best meeting hours'); best.clicked.connect(self.find_best_meeting); buttons.addWidget(best); buttons.addStretch(); lay.addLayout(buttons)
        self.meet_summary=QLabel('Choose a date and compare local times across your saved cities.'); self.meet_summary.setObjectName('muted'); self.meet_summary.setWordWrap(True); lay.addWidget(self.meet_summary)
        self.meet_table=QTableWidget(0,4); self.meet_table.setHorizontalHeaderLabels(['City','Local time','Day','Working hours']); self.meet_table.horizontalHeader().setStretchLastSection(True); lay.addWidget(self.meet_table,1)
        self.tabs.addTab(tab,'Meeting planner')
    def build_comparison_tab(self):
        tab=QWidget(); lay=QVBoxLayout(tab); lay.setSpacing(10)
        title=QLabel('Live world time comparison'); title.setStyleSheet('font-size:15pt;font-weight:650;')
        hint=QLabel('A live overview of every saved city, including date, UTC offset and typical business-hour status.')
        hint.setObjectName('muted'); hint.setWordWrap(True); lay.addWidget(title); lay.addWidget(hint)
        self.compare_table=QTableWidget(0,5)
        self.compare_table.setHorizontalHeaderLabels(['City','Local time','Local date','UTC offset','Local status'])
        self.compare_table.horizontalHeader().setStretchLastSection(True)
        self.compare_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.compare_table.setSelectionBehavior(QTableWidget.SelectRows)
        lay.addWidget(self.compare_table,1)
        self.tabs.addTab(tab,'Time comparison')

    def refresh_comparison(self):
        if not hasattr(self,'compare_table'): return
        rows=self.store.cities(); self.compare_table.setRowCount(len(rows))
        fmt='%H:%M:%S' if self.store.get('time_format','12')=='24' else '%I:%M:%S %p'
        for i,(name,zone) in enumerate(rows):
            local=datetime.now(timezone.utc).astimezone(ZoneInfo(zone))
            offset=local.strftime('%z'); offset='UTC'+offset[:3]+':'+offset[3:] if offset else 'UTC'
            status='Business hours' if 9 <= local.hour < 17 and local.weekday()<5 else ('Weekend' if local.weekday()>=5 else 'Outside business hours')
            values=(name,local.strftime(fmt).lstrip('0') if fmt.startswith('%I') else local.strftime(fmt),
                    local.strftime('%A, %d %b %Y'),offset,status)
            for j,value in enumerate(values):
                self.compare_table.setItem(i,j,QTableWidgetItem(value))

    def build_alarms_tab(self):
        tab=QWidget(); lay=QVBoxLayout(tab); lay.setSpacing(10)
        title=QLabel('World alarms'); title.setStyleSheet('font-size:15pt;font-weight:650;')
        hint=QLabel('Create a one-time alarm using the selected city’s local date and time. Alarms are saved on this PC.')
        hint.setObjectName('muted'); hint.setWordWrap(True); lay.addWidget(title); lay.addWidget(hint)
        form=QFormLayout()
        self.alarm_title=QLineEdit(); self.alarm_title.setPlaceholderText('e.g. Call the Dubai office')
        self.alarm_city=QComboBox()
        self.alarm_dt=QDateTimeEdit(QDateTime.currentDateTime().addSecs(3600))
        self.alarm_dt.setCalendarPopup(True); self.alarm_dt.setDisplayFormat('yyyy-MM-dd  HH:mm')
        self.alarm_city.currentIndexChanged.connect(self.sync_alarm_datetime)
        form.addRow('Alarm title:',self.alarm_title); form.addRow('City / time zone:',self.alarm_city); form.addRow('Local date & time:',self.alarm_dt)
        lay.addLayout(form)
        actions=QHBoxLayout()
        add=QPushButton('＋ Add alarm'); add.setObjectName('primary'); add.clicked.connect(self.add_alarm)
        delete=QPushButton('Delete selected'); delete.setObjectName('danger'); delete.clicked.connect(self.delete_alarm)
        actions.addWidget(add); actions.addWidget(delete); actions.addStretch(); lay.addLayout(actions)
        self.alarm_table=QTableWidget(0,4)
        self.alarm_table.setHorizontalHeaderLabels(['Title','City','Local date & time','Status'])
        self.alarm_table.horizontalHeader().setStretchLastSection(True)
        self.alarm_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.alarm_table.setSelectionBehavior(QTableWidget.SelectRows)
        lay.addWidget(self.alarm_table,1)
        self.tabs.addTab(tab,'World alarms')
        self.refresh_alarms()

    def refresh_alarms(self):
        if not hasattr(self,'alarm_table'): return
        rows=self.store.alarms(); self.alarm_table.setRowCount(len(rows))
        for i,(alarm_id,title,city,zone,local_at,enabled,fired) in enumerate(rows):
            try: shown=datetime.fromisoformat(local_at).strftime('%Y-%m-%d %H:%M')
            except Exception: shown=local_at
            status='Triggered' if fired else ('Scheduled' if enabled else 'Disabled')
            for j,value in enumerate((title,city,shown,status)):
                item=QTableWidgetItem(str(value))
                if j==0: item.setData(Qt.UserRole,alarm_id)
                self.alarm_table.setItem(i,j,item)

    def sync_alarm_datetime(self,*_):
        zone=self.alarm_city.currentData() if hasattr(self,'alarm_city') else None
        if not zone:
            return
        try:
            suggested=(datetime.now(timezone.utc).astimezone(ZoneInfo(zone))+timedelta(minutes=5)).replace(tzinfo=None)
            self.alarm_dt.setDateTime(QDateTime(suggested))
        except Exception:
            pass

    def add_alarm(self):
        if self.alarm_city.count()==0:
            QMessageBox.information(self,'No cities','Add at least one city in the World clock tab first.')
            return
        title=self.alarm_title.text().strip() or 'WorldClock alarm'
        city=self.alarm_city.currentText()
        zone=self.alarm_city.currentData()
        try:
            local_dt=self.alarm_dt.dateTime().toPython().replace(tzinfo=None)
            tz=ZoneInfo(zone)
            target=local_dt.replace(tzinfo=tz,fold=0)
            # Reject local times skipped by a daylight-saving transition.
            roundtrip=target.astimezone(timezone.utc).astimezone(tz).replace(tzinfo=None)
            if roundtrip != local_dt:
                QMessageBox.warning(self,'Invalid local time',
                    'This local time does not exist because the clock changes for daylight saving time. Choose another time.')
                return
            target_utc=target.astimezone(timezone.utc)
        except Exception as exc:
            QMessageBox.warning(self,'Invalid alarm',f'Could not validate this alarm time: {exc}')
            return
        if target_utc <= datetime.now(timezone.utc):
            QMessageBox.warning(self,'Choose a future time','Please choose a future date and time in the selected city.')
            return
        self.store.add_alarm(title,city,zone,local_dt.strftime('%Y-%m-%dT%H:%M:%S'))
        self.alarm_title.clear()
        self.refresh_alarms()
        QMessageBox.information(self,'Alarm saved',
            f'Alarm saved for {city} at {local_dt.strftime("%Y-%m-%d %H:%M")} ({zone}).')

    def delete_alarm(self):
        row=self.alarm_table.currentRow()
        if row<0: return
        item=self.alarm_table.item(row,0)
        if item:
            self.store.delete_alarm(item.data(Qt.UserRole)); self.refresh_alarms()

    def check_alarms(self):
        due=self.store.due_alarms(datetime.now(timezone.utc))
        for alarm_id,title,city,zone,local_at in due:
            # Mark first to guarantee a single notification even if the user delays responding.
            self.store.mark_alarm_fired(alarm_id)
            try: local=datetime.fromisoformat(local_at).strftime('%Y-%m-%d %H:%M')
            except Exception: local=local_at
            QApplication.beep()
            box=QMessageBox(self)
            box.setWindowTitle('WorldClock alarm')
            box.setIcon(QMessageBox.Information)
            box.setText(f'{title}\\n{city} — {local}\\nTime zone: {zone}')
            dismiss=box.addButton('Dismiss',QMessageBox.AcceptRole)
            snooze=box.addButton('Snooze 5 minutes',QMessageBox.ActionRole)
            if hasattr(self,'tray') and QSystemTrayIcon.isSystemTrayAvailable():
                self.tray.showMessage('WorldClock alarm',f'{title}\\n{city} — {local}',
                                      QSystemTrayIcon.Information,10000)
            box.exec()
            if box.clickedButton()==snooze:
                try:
                    now_local=datetime.now(timezone.utc).astimezone(ZoneInfo(zone))
                    snooze_local=(now_local+timedelta(minutes=5)).replace(tzinfo=None)
                    self.store.snooze_alarm(alarm_id,snooze_local.strftime('%Y-%m-%dT%H:%M:%S'))
                except Exception:
                    pass
        if due:
            self.refresh_alarms()

    def build_settings_tab(self):
        tab=QWidget(); lay=QVBoxLayout(tab); group=QGroupBox('Appearance & behavior'); form=QFormLayout(group)
        self.home_city=QComboBox(); self.home_city.currentIndexChanged.connect(self.save_home_city); form.addRow('My reference city:',self.home_city)
        self.time_format=QComboBox(); self.time_format.addItems(['12-hour clock','24-hour clock']); self.time_format.setCurrentIndex(1 if self.store.get('time_format','12')=='24' else 0); self.time_format.currentIndexChanged.connect(lambda i:self.store.set('time_format','24' if i else '12')); form.addRow('Time format:',self.time_format)
        self.opacity=QSlider(Qt.Horizontal); self.opacity.setRange(90,100); self.opacity.setValue(max(90,int(float(self.store.get('opacity','1.0'))*100))); self.opacity.valueChanged.connect(self.change_opacity); form.addRow('Mini widget opacity:',self.opacity)
        self.mini_toggle=QCheckBox('Show mini widget'); self.mini_toggle.setChecked(self.store.get('show_mini','1')=='1'); self.mini_toggle.toggled.connect(self.toggle_mini); form.addRow('',self.mini_toggle)
        self.top_toggle=QCheckBox('Keep mini widget always on top'); self.top_toggle.toggled.connect(self.set_topmost); form.addRow('',self.top_toggle)
        self.autostart_toggle=QCheckBox('Auto start WorldClock')
        self.autostart_toggle.setToolTip('When checked, WorldClock launches automatically when you sign in to Windows. Uncheck to disable auto start.')
        self.autostart_toggle.setChecked(self.startup_enabled())
        self.autostart_toggle.toggled.connect(self.set_startup)
        form.addRow('Windows startup:',self.autostart_toggle)
        lay.addWidget(group); note=QLabel('Quick currency popup: Alt + Shift + C. Time zones use the system IANA database and automatically follow daylight-saving changes where applicable. City preferences are stored locally on this PC.'); note.setWordWrap(True); note.setObjectName('muted'); lay.addWidget(note); lay.addStretch(); self.tabs.addTab(tab,'Settings')
    def refresh_world(self):
        for c in self.cards: c.deleteLater()
        self.cards=[]
        while self.world_grid.count(): self.world_grid.takeAt(0)
        self.city_list.clear(); rows=self.store.cities(); favorites=self.store.favorites()
        for i,(name,zone) in enumerate(rows):
            item=QListWidgetItem(('★  ' if (name,zone) in favorites else '   ') + name); item.setToolTip(zone); item.setData(Qt.UserRole,(name,zone)); self.city_list.addItem(item)
            card=CityCard(name,zone,self.store); self.cards.append(card); self.world_grid.addWidget(card,i//2,i%2)
        preferred=self.store.get('home_zone', rows[0][1] if rows else '')
        self.conv_city.clear(); self.meet_base.blockSignals(True); self.home_city.blockSignals(True); self.meet_base.clear(); self.home_city.clear()
        for n,z in rows:
            self.conv_city.addItem(n,z); self.meet_base.addItem(n,z); self.home_city.addItem(n,z)
        idx=self.home_city.findData(preferred)
        if idx>=0: self.home_city.setCurrentIndex(idx)
        midx=self.meet_base.findData(preferred)
        if midx>=0: self.meet_base.setCurrentIndex(midx)
        self.home_city.blockSignals(False); self.meet_base.blockSignals(False)
        if hasattr(self,'alarm_city'):
            self.alarm_city.blockSignals(True)
            self.alarm_city.clear()
            for n,z in rows: self.alarm_city.addItem(n,z)
            self.alarm_city.blockSignals(False)
            self.sync_alarm_datetime()
        self.refresh_comparison()
        self.refresh_alarms()
        self.mini.refresh_cities()
        self.mini.apply_language(self.store.get('language','en'))
    def tick(self):
        for c in self.cards: c.refresh()
        self.mini.refresh()
        self.refresh_comparison()
        self.check_alarms()
    def add_city(self):
        raw=self.search.text().strip()
        if not raw: return
        zone=raw if raw in available_timezones() else None
        catalog_match = next((item for item in TIMEZONE_CATALOG
                              if raw.casefold() == item[2].casefold()
                              or raw.casefold() == item[0].casefold()
                              or (len(raw) >= 3 and raw.casefold() in item[0].casefold() and
                                  any(ord(ch) > 127 for ch in raw))), None)
        if not zone and catalog_match:
            zone = catalog_match[1]
        # Catalog format: Country — City / local name (Area/Location)
        if not zone:
            match=re.search(r'\(([^()]+)\)\s*$', raw)
            if match and match.group(1) in available_timezones():
                zone=match.group(1)
        if not zone:
            # Also accept a plain IANA identifier typed by the user.
            candidate=raw.replace(' ','_')
            if candidate in available_timezones(): zone=candidate
        if not zone:
            QMessageBox.information(self,'Choose a location',
                'Select a suggested result, or enter an IANA time zone such as Europe/Paris or America/Los_Angeles.')
            return
        # Preserve the selected city alias (e.g. Jeddah) even when it shares
        # its IANA zone with another city (e.g. Riyadh).
        if catalog_match and catalog_match[1] == zone:
            city = catalog_match[2]
        else:
            selected = next(((label, city) for label, z, city in TIMEZONE_CATALOG if z == zone and raw == label), None)
            if selected:
                city = selected[1]
            else:
                city = next((city for label,z,city in TIMEZONE_CATALOG if z==zone and label.endswith(f"({zone})")), zone.split('/')[-1].replace('_',' '))
        self.store.add_city(city,zone); self.search.clear(); self.refresh_world()
    def select_city(self,row): self.city_list.setCurrentRow(row)
    def remove_city(self):
        item=self.city_list.currentItem()
        if item:
            name,zone=item.data(Qt.UserRole); self.store.remove_city(zone,name); self.refresh_world()
    def toggle_favorite(self):
        item=self.city_list.currentItem()
        if item:
            name,zone=item.data(Qt.UserRole); self.store.toggle_favorite(name,zone); self.refresh_world()
    def save_home_city(self,i):
        if i>=0 and hasattr(self,'home_city'):
            self.store.set('home_zone',self.home_city.currentData())
    def move_city(self,d):
        row=self.city_list.currentRow()
        if row>=0: self.store.move(row,d); self.refresh_world(); self.city_list.setCurrentRow(max(0,min(row+d,self.city_list.count()-1)))
    def convert_time(self):
        if not self.store.cities(): return
        zone=self.conv_city.currentData()
        dt=self.conv_dt.dateTime().toPython().replace(tzinfo=ZoneInfo(zone))
        utc=dt.astimezone(timezone.utc); rows=self.store.cities(); self.conv_table.setRowCount(len(rows))
        for i,(name,z) in enumerate(rows):
            local=utc.astimezone(ZoneInfo(z))
            time_fmt='%Y-%m-%d  %H:%M' if self.store.get('time_format','12')=='24' else '%a, %d %b %Y  %I:%M %p'
            for j,val in enumerate((name,local.strftime(time_fmt),local.strftime('UTC%z'))): self.conv_table.setItem(i,j,QTableWidgetItem(val))
    def plan_meeting(self):
        rows=self.store.cities()
        if not rows:return
        base=self.meet_base.currentData() or rows[0][1]; local=self.meet_dt.dateTime().toPython().replace(tzinfo=ZoneInfo(base)); utc=local.astimezone(timezone.utc); self.meet_table.setRowCount(len(rows))
        for i,(name,z) in enumerate(rows):
            d=utc.astimezone(ZoneInfo(z)); work='Within 09:00–17:00' if 9<=d.hour<17 else 'Outside typical work hours'
            vals=(name,d.strftime('%H:%M' if self.store.get('time_format','12')=='24' else '%I:%M %p'),d.strftime('%A, %d %b'),work)
            for j,v in enumerate(vals): self.meet_table.setItem(i,j,QTableWidgetItem(v))
        self.meet_summary.setText(f'Meeting reference: {self.meet_base.currentText()} · {local.strftime("%A, %d %B %Y %I:%M %p")}')
    def find_best_meeting(self):
        rows=self.store.cities()
        if not rows: return
        base=self.meet_base.currentData() or rows[0][1]
        chosen=self.meet_dt.dateTime().toPython()
        start=datetime(chosen.year,chosen.month,chosen.day,0,0,tzinfo=ZoneInfo(base)).astimezone(timezone.utc)
        scored=[]
        for hour in range(24):
            instant=start.replace(minute=0,second=0,microsecond=0)+__import__('datetime').timedelta(hours=hour)
            good=[]; details=[]
            for name,zone in rows:
                local=instant.astimezone(ZoneInfo(zone)); ok=9<=local.hour<17
                if ok: good.append(name)
                details.append(f'{name} {local.strftime("%H:%M")}')
            scored.append((len(good),instant,details,good))
        scored.sort(key=lambda x:(-x[0],x[1]))
        self.meet_table.setRowCount(min(5,len(scored)))
        for i,(score,instant,details,good) in enumerate(scored[:5]):
            vals=(f'{score}/{len(rows)} cities in work hours', ' · '.join(details), instant.astimezone(ZoneInfo(base)).strftime('%A, %d %b'), ', '.join(good) if good else 'No cities in typical work hours')
            for j,v in enumerate(vals): self.meet_table.setItem(i,j,QTableWidgetItem(v))
        self.meet_summary.setText('Best overlap candidates ranked by number of cities within 09:00–17:00. This is a simple working-hours heuristic; adjust for local business schedules and holidays.')
    def change_opacity(self,v):
        self.store.set('opacity',v/100); self.mini.setWindowOpacity(v/100)
    def toggle_mini(self,v): self.store.set('show_mini','1' if v else '0'); self.mini.show() if v else self.mini.hide()
    def set_topmost(self,v):
        self.mini.pinned=v
        self.mini.setWindowFlag(Qt.WindowStaysOnTopHint,v)
        self.mini.show()
        if v:
            screen=QGuiApplication.screenAt(self.mini.frameGeometry().center()) or QGuiApplication.primaryScreen()
            if screen:
                area=screen.availableGeometry()
                self.mini.move(area.right()-self.mini.width()-12,area.top()+12)
        self.mini.pin.setText('PINNED' if v else 'PIN')
    def create_flag_pixmap(self,language):
        # Draw flags into QPixmap at runtime: no external image path, working-directory,
        # Qt image plugin, or PyInstaller asset-bundling dependency.
        w,h=90,60
        pix=QPixmap(w,h); pix.fill(QColor("white"))
        p=QPainter(pix); p.setRenderHint(QPainter.Antialiasing,False)
        def rect(x,y,rw,rh,color):
            p.fillRect(x,y,rw,rh,QColor(color))
        if language=='ru':
            rect(0,0,w,20,'#ffffff'); rect(0,20,w,20,'#0039a6'); rect(0,40,w,20,'#d52b1e')
        elif language=='de':
            rect(0,0,w,20,'#000000'); rect(0,20,w,20,'#dd0000'); rect(0,40,w,20,'#ffce00')
        elif language=='fr':
            rect(0,0,30,h,'#002395'); rect(30,0,30,h,'#ffffff'); rect(60,0,30,h,'#ed2939')
        elif language=='es':
            rect(0,0,w,15,'#aa151b'); rect(0,15,w,30,'#f1bf00'); rect(0,45,w,15,'#aa151b')
        elif language=='it':
            rect(0,0,30,h,'#009246'); rect(30,0,30,h,'#ffffff'); rect(60,0,30,h,'#ce2b37')
        else:  # United Kingdom
            rect(0,0,w,h,'#012169')
            p.setPen(QPen(QColor('#ffffff'),12)); p.drawLine(0,0,w,h); p.drawLine(w,0,0,h)
            p.setPen(QPen(QColor('#c8102e'),5)); p.drawLine(0,0,w,h); p.drawLine(w,0,0,h)
            rect(36,0,18,h,'#ffffff'); rect(0,21,w,18,'#ffffff')
            rect(40,0,10,h,'#c8102e'); rect(0,25,w,10,'#c8102e')
        p.end()
        border=QPainter(pix); border.setPen(QPen(QColor('#aeb9c9'),2)); border.drawRect(1,1,w-3,h-3); border.end()
        return pix

    def change_language_code(self,code):
        self.store.set('language',code)
        self.update_language_button(code)
        self.apply_language(code)

    def update_language_button(self,code):
        labels={code_:label for label,code_ in self.language_items}
        self.lang_button.setText('')
        self.lang_button.setIcon(QIcon(self.flag_pixmaps.get(code,self.flag_pixmaps['en'])))
        self.lang_button.setToolTip('Language: ' + labels.get(code,'English') + ' · Click to change')
        for action in self.lang_group.actions():
            action.setChecked(action.data()==code)

    def apply_language(self,code):
        mapping=TRANSLATIONS.get(code,{})
        # Always derive displayed text from the immutable original text.
        # This guarantees switching back to English restores every control.
        for widget in self.findChildren(QWidget):
            if widget is self.lang_button:
                continue
            if isinstance(widget,QLabel):
                original=widget.property('wc_original_text')
                if original is None:
                    original=widget.text(); widget.setProperty('wc_original_text',original)
                widget.setText(mapping.get(original,original))
            elif isinstance(widget,QPushButton):
                original=widget.property('wc_original_text')
                if original is None:
                    original=widget.text(); widget.setProperty('wc_original_text',original)
                widget.setText(mapping.get(original,original))
            elif isinstance(widget,QCheckBox):
                original=widget.property('wc_original_text')
                if original is None:
                    original=widget.text(); widget.setProperty('wc_original_text',original)
                widget.setText(mapping.get(original,original))
            elif isinstance(widget,QLineEdit):
                original=widget.property('wc_original_placeholder')
                if original is None:
                    original=widget.placeholderText(); widget.setProperty('wc_original_placeholder',original)
                widget.setPlaceholderText(mapping.get(original,original))
            elif isinstance(widget,QGroupBox):
                original=widget.property('wc_original_title')
                if original is None:
                    original=widget.title(); widget.setProperty('wc_original_title',original)
                widget.setTitle(mapping.get(original,original))
            elif isinstance(widget,QComboBox):
                for index in range(widget.count()):
                    original=widget.itemData(index,Qt.UserRole+1)
                    if original is None:
                        original=widget.itemText(index)
                        widget.setItemData(index,original,Qt.UserRole+1)
                    widget.setItemText(index,mapping.get(original,original))
        for tab_index in range(self.tabs.count()):
            page=self.tabs.widget(tab_index)
            original=page.property('wc_original_tab')
            if original is None:
                original=self.tabs.tabText(tab_index); page.setProperty('wc_original_tab',original)
            self.tabs.setTabText(tab_index,mapping.get(original,original))
        for table in self.findChildren(QTableWidget):
            for col in range(table.columnCount()):
                item=table.horizontalHeaderItem(col)
                if item:
                    original=item.data(Qt.UserRole+1)
                    if original is None:
                        original=item.text(); item.setData(Qt.UserRole+1,original)
                    item.setText(mapping.get(original,original))
        if hasattr(self,'mini'):
            self.mini.apply_language(code)
        self.update_language_button(code)
        self.setWindowTitle(f'SmartDesk · WorldClock v{APP_VERSION}')
    def startup_command(self):
        if getattr(sys,'frozen',False):
            return f'"{Path(sys.executable).resolve()}"'
        script=Path(__file__).resolve()
        python=Path(sys.executable).resolve()
        # Prefer pythonw.exe to avoid opening a console window for .pyw.
        if python.name.lower()=='python.exe':
            candidate=python.with_name('pythonw.exe')
            if candidate.exists():
                python=candidate
        return f'"{python}" "{script}"'

    def startup_enabled(self):
        if os.name!='nt':
            return False
        try:
            import winreg
            key=winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                r'Software\\Microsoft\\Windows\\CurrentVersion\\Run',0,winreg.KEY_READ)
            try:
                value,_=winreg.QueryValueEx(key,'WorldClock')
                return bool(value)
            finally:
                winreg.CloseKey(key)
        except (FileNotFoundError,OSError):
            return False

    def set_startup(self,enabled):
        if os.name!='nt':
            QMessageBox.warning(self,'Windows startup','Auto-start controls are available on Windows only.')
            if hasattr(self,'autostart_toggle'):
                self.autostart_toggle.blockSignals(True)
                self.autostart_toggle.setChecked(False)
                self.autostart_toggle.blockSignals(False)
            return
        try:
            import winreg
            key=winreg.CreateKey(winreg.HKEY_CURRENT_USER,
                r'Software\\Microsoft\\Windows\\CurrentVersion\\Run')
            try:
                if enabled:
                    winreg.SetValueEx(key,'WorldClock',0,winreg.REG_SZ,self.startup_command())
                else:
                    try: winreg.DeleteValue(key,'WorldClock')
                    except FileNotFoundError: pass
            finally:
                winreg.CloseKey(key)
            if hasattr(self,'autostart_toggle'):
                self.autostart_toggle.blockSignals(True)
                self.autostart_toggle.setChecked(enabled)
                self.autostart_toggle.blockSignals(False)
            self.store.set('autostart','1' if enabled else '0')
            state='enabled' if enabled else 'disabled'
            self.statusBar().showMessage(f'WorldClock auto-start {state}.',4000) if self.statusBar() else None
        except Exception as exc:
            QMessageBox.critical(self,'Auto-start setting failed',
                f'Windows could not update the startup setting.\\n\\n{exc}')
            if hasattr(self,'autostart_toggle'):
                self.autostart_toggle.blockSignals(True)
                self.autostart_toggle.setChecked(self.startup_enabled())
                self.autostart_toggle.blockSignals(False)

    def shutdown(self):
        # Unregister global hooks and let any in-flight HTTP workers finish cleanly.
        try:
            if self.hotkey_module:
                self.hotkey_module.unhook_all_hotkeys()
        except Exception:
            pass
        for panel in (getattr(self, 'currency_panel', None), getattr(getattr(self, 'currency_popup', None), 'panel', None)):
            worker = getattr(panel, 'worker', None) if panel else None
            if worker and worker.isRunning():
                worker.wait(9000)

    def create_tray(self):
        self.tray=QSystemTrayIcon(self); self.tray.setToolTip('SmartDesk'); menu=QMenu(); a=QAction('Open dashboard',self); a.triggered.connect(self.show_dashboard); menu.addAction(a); b=QAction('Show mini widget',self); b.triggered.connect(self.show_mini); menu.addAction(b); fx=QAction('Quick currency · Alt+Shift+C',self); fx.triggered.connect(self.show_currency_popup); menu.addAction(fx); c=QAction('Quit',self); c.triggered.connect(QApplication.quit); menu.addAction(c); self.tray.setContextMenu(menu); self.tray.activated.connect(lambda reason:self.show_dashboard() if reason==QSystemTrayIcon.DoubleClick else None)
        if QSystemTrayIcon.isSystemTrayAvailable(): self.tray.show()
    def show_dashboard(self): self.show(); self.raise_(); self.activateWindow()
    def show_mini(self): self.mini.show(); self.mini.raise_()
    def closeEvent(self,e):
        e.ignore(); self.hide(); self.tray.showMessage('WorldClock','Still running in the system tray.',QSystemTrayIcon.Information,1800)

def main():
    app=QApplication(sys.argv)
    app.setApplicationName('SmartDesk')
    app.setQuitOnLastWindowClosed(False)
    bundle_dir = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent))
    icon_path = bundle_dir / 'assets' / 'smartdesk.ico'
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))
    w=MainWindow()
    if icon_path.exists():
        w.setWindowIcon(QIcon(str(icon_path)))
    app.aboutToQuit.connect(w.shutdown)
    w.show()
    sys.exit(app.exec())
if __name__=='__main__': main()

