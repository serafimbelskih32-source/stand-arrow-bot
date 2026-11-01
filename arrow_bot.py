"""
Arrow bot v3: автономный "умный TinyTask" для Roblox (Stand Upright: Rebooted).
Только скриншоты + мышь/клавиатура, в игру не лезет.

Сам делает всё:
  - находит окно Roblox (где бы оно ни лежало, любого размера) и выводит его вперёд;
  - сам находит, в каком слоте хотбара стрела и Rokakaka (перебирает слоты 1-0, читает
    подпись внизу экрана), заново после смерти / перезахода;
  - если выкинуло в главное меню (Play / Help / Gamemodes) - нажимает Play;
  - если панель Stand/Attribute скрыта - открывает её клавишей M;
  - крутит стрелу, читает "Stand:" и "Attribute:", сверяет с правилами;
  - не подходит -> Rokakaka; если игра спросила "...are you sure? Yes / No" - перепроверяет
    панель и жмёт Yes; подходит -> бип, СТОП (ничего не удаляет), программа закрывается.

Установка (Windows, Python 3.10-3.12):
    pip install mss pyautogui keyboard rapidocr-onnxruntime opencv-python numpy

Запуск (калибровка НЕ нужна):
    python arrow_bot.py            # работа (если на тебе уже есть стенд - спросит подтверждение)
    python arrow_bot.py --yes      # без вопросов (полностью автономно)
    python arrow_bot.py analyze    # показать, что бот видит сейчас (ничего не кликает)
    python arrow_bot.py analyze shot.png   # то же на картинке

F6 - пауза/продолжить, F7 - стоп. Мышь в левый верхний угол экрана - аварийный стоп.
Лог пишется в arrow_bot_log.txt, при остановке сохраняется arrow_bot_last.png (что бот видел).
"""
import sys, os, re, json, time, difflib, ctypes

VERSION = "5.12"      # поднимай при каждом обновлении: окно по нему решает, новее ли архив
APP_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_FILE = os.path.join(APP_DIR, "arrow_bot_log.txt")
LAST_SHOT = os.path.join(APP_DIR, "arrow_bot_last.png")
SETTINGS_FILE = os.path.join(APP_DIR, "arrow_settings.json")    # правила и настройки из окна (arrow_gui.pyw)
STATS_FILE = os.path.join(APP_DIR, "arrow_bot_stats.jsonl")     # каждый бросок: время, стенд, атрибут, решение
STATE_FILE = os.path.join(APP_DIR, "arrow_bot_state.json")      # текущее состояние для окна
STOP_FILE = os.path.join(APP_DIR, "arrow_bot.stop")             # кнопка Стоп в окне

# ================= ПРАВИЛА (меняй под себя) =================
# Полный список стендов (из таблицы шансов игры) с шансом в %.
STANDS = {
    "Silver Chariot": 15, "Crazy Diamond": 15,
    "Star Platinum": 10, "Hierophant Green": 10, "Killer Queen": 10, "The Hand": 10,
    "Golden Experience": 5, "King Crimson": 5, "Tusk Act 1": 5, "The World": 5,
    "Dirty Deeds Done Dirt Cheap": 5, "Whitesnake": 4.9,
    "The World: Alternate Universe": 2, "Vanilla Ice's Cream": 0.5,
    "The World OVA": 0.1, "Star Platinum OVA": 0.05,
    "Magician's Red OVA": 0.3, "Silver Chariot OVA": 0.3,
    "DIO's The World": 0.1, "Jotaro's Star Platinum": 0.1, "Putrid Whine": 0.1,
    "The Universe, Vestige": 0.015, "Shadow The Universe": 0.015,
    "Sol Spirit": 0.015, "Sol Spirit, Obscura": 0.015,
    "Doppio's King Crimson, Alternate Universe": 0.015,
}
# Атрибуты, которые вообще могут быть нужны (для проверки OCR); решает таблица STAND_RULES ниже.
GOOD_ATTRS = {"Daemon", "Invincible", "Glass Cannon", "Tragic", "Hacker", "Scourge", "Legendary"}
# ПРАВИЛА ПО СТЕНДАМ: стенд -> при каких атрибутах оставляем. Стенда нет в таблице - сносим при любом атрибуте
# (так задумано). Legendary на стенде не из таблицы НЕ оставляем.
# Таблицу можно менять в окне (вкладка «Стенды и атрибуты») или здесь: под каждым стендом его атрибуты.
L = {"Legendary"}
LSH = {"Legendary", "Scourge", "Hacker"}
LSHG = {"Legendary", "Scourge", "Hacker", "Glass Cannon", "Tragic"}
LSHGD = {"Legendary", "Scourge", "Hacker", "Glass Cannon", "Tragic", "Daemon"}
ALL = {"None", "Strong", "Tough", "Sloppy", "Powerful", "Enrage", "Manic", "Lethargic", "Godly", "Daemon", "Invincible", "Glass Cannon", "Tragic", "Hacker", "Scourge", "Legendary"}
             
STAND_RULES = {          # стенды из Charged Arrow: при каких атрибутах оставлять
    "The Hand": L, "Dirty Deeds Done Dirt Cheap": L, "King Crimson": L, "Tusk Act 1": L, "The World": L, "Whitesnake": L, "The World: Alternate Universe": L, "Silver Chariot OVA": L, "Putrid Whine": L,
    "Vanilla Ice's Cream": LSH, "Magician's Red OVA": LSH, "The World OVA": LSH, "Star Platinum OVA": LSH,
    "DIO's The World": LSHG, "Jotaro's Star Platinum": LSHG, "The Universe, Vestige": ALL,
    "Shadow The Universe": ALL, "Sol Spirit": ALL, "Sol Spirit, Obscura": ALL,
    "Doppio's King Crimson, Alternate Universe": ALL, 
}
# Стенды, которые выпадают из обычных стрел (Stand Arrow), список с шансами. Нужен только Premier Macho
# с Legendary, остальные "не нужен": сносятся, но с известным шансом (бот их опознаёт, статистика считается честно).
STAND_ARROW_STANDS = {"Premier Macho": 1, "Purple Smoke": 2.5, "Weather Report": 1.5, "The Emperor": 5,
                      "Star Platinum Stone Ocean": 5, "Cream": 7.5, "Soft And Wet": 3.75, "Diver Down": 2.5,
                      "Jolyne's Stone Free": 1}
STAND_POOL = {name: "Stand Arrow" for name in STAND_ARROW_STANDS}      # из какой стрелы стенд; остальные из Charged Arrow
STANDS.update(STAND_ARROW_STANDS)
STAND_RULES["Premier Macho"] = L
# Все атрибуты игры. Плохие просто сносятся.
ALL_ATTRS = ["None", "Strong", "Tough", "Sloppy", "Powerful", "Enrage", "Manic", "Lethargic",
             "Godly", "Daemon", "Invincible", "Glass Cannon", "Tragic", "Hacker", "Scourge", "Legendary"]
# Если прочитан атрибут не из списка, или нужный атрибут на неопознанном стенде -
# бот останавливается и пишет, что увидел (вдруг OCR ошибся), ничего не удаляя.
# ============================================================

# Имена предметов (как в подписи внизу экрана "Charged Arrow: 6682 / 20000")
ARROW_NAMES = ["Charged Arrow", "Stand Arrow"]   # по порядку: пока есть первая, крутим её, когда кончится, переходим на следующую
FRUIT_NAMES = ["Rokakaka"]
SLOT_DEFAULTS = {"arrow": "1", "fruit": "2"}   # с каких слотов начинать поиск (дальше сам найдёт)
HOTBAR_KEYS = "1234567890"
PANEL_KEY = "m"      # клавиша, которой открывается панель Stand/Attribute (по умолчанию в игре)

CONFIRM_EXISTING_STAND = True   # если на старте уже есть стенд - спросить (отключается флагом --yes)
ROLL_TIMEOUT = 8       # макс. сек ждать появления стенда после стрелы
DIALOG_WAIT = 4          # макс. сек ждать предупреждение / исчезновение стенда после фрукта
MENU_LOAD_WAIT = 20      # сек ждать загрузки игры после нажатия Play
NO_BUTTONS_FALLBACK = 2.0   # текст предупреждения есть, а кнопки не нашлись - жать по позиции через N сек
YES_FRAC = (0.4146, 0.758)  # позиции Yes/No как доля окна игры (измерено по видео игры)
NO_FRAC = (0.5930, 0.758)

_ocr = None


class Stop(Exception):
    pass


# ---------- утилиты ----------
OVL_LINES = []                       # последние строки лога для оверлея
OVL_STATS = {"n": 0, "t0": None, "last": ""}


TESTING = bool(os.environ.get("ARROWBOT_TEST"))   # симулятор и тесты не пишут в настоящий лог и статистику


def log(msg):
    line = time.strftime("%H:%M:%S ") + msg
    print(line)
    if TESTING:
        return
    OVL_LINES.append(line)
    del OVL_LINES[:-8]
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def norm(s):
    return re.sub(r"[^a-z0-9%а-я]", "", s.lower())


def fuzzy(text, options, cutoff):
    """Сравнение без пробелов/регистра/знаков. Возвращает оригинальное имя или None."""
    t = norm(text)
    if not t:
        return None
    table = {norm(o): o for o in options}
    m = difflib.get_close_matches(t, list(table), n=1, cutoff=cutoff)
    return table[m[0]] if m else None


# ---------- разбор экрана (OCR-строки -> состояние) ----------
ARROW_YES_FRAC = (0.415, 0.775)
CLOSE_FRAC = (0.501, 0.881)          # кнопка CLOSE в окне Changelogs (доля окна)
RECONNECT_WAIT = 1800                # сек ждать, пока ты перезайдёшь после Disconnected, потом стоп
_STOP = __import__("threading").Event()   # ставится по F7 из потока клавиатуры, не пропускается во время OCR


def parse_items(items, region_wh=None):
    r = {"stand": "", "attr": None, "equipped": None, "count": None, "warning": False,
         "yes": None, "no": None, "has_panel": False, "menu_play": None, "error": False,
         "arrow_prompt": False, "inv_open": False, "changelog_close": None, "reconnect_btn": None, "equipped_name": None}
    has_menu = any("gamemodes" in norm(it["text"]) for it in items)
    has_changelog = any("changelogs" in norm(it["text"]) for it in items)
    close_pt = None
    for it in items:
        t, nt = it["text"], norm(it["text"])
        m = re.match(r"^\s*stand\s*[:;.,]\s*(.*)$", t, re.I)
        if m:
            r["stand"] = m.group(1).strip(); r["has_panel"] = True; continue
        m = re.match(r"^\s*attribute(.*)$", t, re.I)
        # строка диалога "Attribute, including rare sub-1% rolls, continue?" - это не панель
        if m and not re.search(r"[,?]|includ|roll|continue", t, re.I) and len(t) <= 32:
            rest = re.sub(r"^[^A-Za-z0-9]+", "", m.group(1)).strip()
            if norm(rest) in ("", "none"):
                r["attr"] = "None"
            else:
                r["attr"] = (fuzzy(rest, ALL_ATTRS, 0.8) or fuzzy(rest[1:], ALL_ATTRS, 0.8) or rest)
            r["has_panel"] = True; continue
        if "/" in t and re.search(r"\d", t):  # подпись снизу: "Rokakaka: 10367 / 20000"
            name = re.sub(r"[^a-z]", "", t.split("/")[0].lower())
            which = ("fruit" if fuzzy(name, FRUIT_NAMES, 0.75) else
                     "arrow" if fuzzy(name, ARROW_NAMES, 0.75) else None)
            if which:
                r["equipped"] = which
                if which == "arrow":
                    r["equipped_name"] = fuzzy(name, ARROW_NAMES, 0.75)      # какая именно стрела в руках
                mc = re.search(r"(\d[\d,.\s]*)/", t)
                if mc:
                    digits = re.sub(r"\D", "", mc.group(1))
                    r["count"] = int(digits) if digits else None
                continue
        if any(k in nt for k in ("removeyourstand", "areyousure", "rollscontinue", "sub1%")):
            r["warning"] = True
        if nt == "reconnect":
            r["reconnect_btn"] = (it["x"], it["y"])      # окно Disconnected при обрыве интернета: Leave / Reconnect
        if has_changelog and nt == "close":
            close_pt = (it["x"], it["y"])
        if nt == "search":
            r["inv_open"] = True          # открыт инвентарь (Ё): сверху поле Search
        if any(k in nt for k in ("betterstandpool", "grantyouastand", "standabilityfrom")):
            r["arrow_prompt"] = True      # окно подтверждения стрелы: "...grant you a stand ability... continue?"
        if any(k in nt for k in ("disconnected", "errorcode", "wasdisconnected", "youwerekicked")):
            r["error"] = True
        low = t.strip(" .!").lower()
        if low in ("yes", "да"):
            r["yes"] = (it["x"], it["y"])
        elif low in ("no", "нет"):
            r["no"] = (it["x"], it["y"])
        elif has_menu and nt == "play":
            r["menu_play"] = (it["x"], it["y"])
    if has_changelog:                     # после захода в игру: окно с красной кнопкой CLOSE
        r["changelog_close"] = close_pt or "frac"
    if not (r["warning"] or r["arrow_prompt"]):
        r["yes"] = r["no"] = None
    return r


# ---------- правила ----------
def match_stand(stand):
    """Лучшее совпадение с полным списком стендов (допуск на ошибки OCR) или None."""
    t = norm(stand)
    if not t:
        return None
    table = {norm(n): n for n in STANDS}
    best = max(table, key=lambda k: difflib.SequenceMatcher(None, t, k).ratio())
    return table[best] if difflib.SequenceMatcher(None, t, best).ratio() >= 0.85 else None


def classify(stand, attr):
    """-> 'keep' | 'delete' | 'unsure'"""
    if attr is None or not stand:
        return "unsure"
    a = fuzzy(attr, ALL_ATTRS, 0.85)
    if a is None:
        return "unsure"                 # атрибут не из списка игры - вдруг OCR ошибся
    st = match_stand(stand)
    if st in STAND_RULES:
        return "keep" if a in STAND_RULES[st] else "delete"
    if st is None:
        # стенд не опознан. Похож на нужный (OCR мог исказить) - не трогаем, иначе сносим
        t = norm(stand)
        if any(difflib.SequenceMatcher(None, t, norm(n)).ratio() >= 0.6 for n in STAND_RULES):
            return "unsure"
    return "delete"                     # стенда нет в таблице - сносим при любом атрибуте


# ---------- реальное окружение (Windows) ----------
def _user32():
    """user32 с правильными типами аргументов (иначе на 64-битной Windows дескрипторы окон могут обрезаться)."""
    import ctypes.wintypes as wt
    u = ctypes.windll.user32
    u.GetForegroundWindow.restype = wt.HWND
    for name in ("IsWindow", "IsIconic", "IsWindowVisible", "GetWindowTextLengthW", "SetForegroundWindow"):
        getattr(u, name).argtypes = [wt.HWND]
    u.ShowWindow.argtypes = [wt.HWND, ctypes.c_int]
    u.GetWindowTextW.argtypes = [wt.HWND, wt.LPWSTR, ctypes.c_int]
    u.GetClientRect.argtypes = [wt.HWND, ctypes.POINTER(wt.RECT)]
    u.ClientToScreen.argtypes = [wt.HWND, ctypes.POINTER(wt.POINT)]
    return u


class Env:
    def __init__(self):
        self.hwnd = None

    # --- окно ---
    def _find_hwnd(self):
        user32 = _user32()
        import ctypes.wintypes as wt
        found = []

        @ctypes.WINFUNCTYPE(ctypes.c_bool, wt.HWND, wt.LPARAM)
        def cb(hwnd, lp):
            if user32.IsWindowVisible(hwnd):
                n = user32.GetWindowTextLengthW(hwnd)
                if n:
                    buf = ctypes.create_unicode_buffer(n + 1)
                    user32.GetWindowTextW(hwnd, buf, n + 1)
                    if buf.value.strip() == "Roblox":
                        found.append(hwnd)
            return True
        user32.EnumWindows(cb, 0)
        if not found:
            return None
        fg = user32.GetForegroundWindow()
        if fg in found:
            return fg

        def area(h):
            rc = wt.RECT(); user32.GetClientRect(h, ctypes.byref(rc)); return rc.right * rc.bottom
        return max(found, key=area)

    def region(self):
        if sys.platform == "win32":
            import ctypes.wintypes as wt
            user32 = _user32()
            if not self.hwnd or not user32.IsWindow(self.hwnd):
                self.hwnd = self._find_hwnd()
            if self.hwnd:
                if user32.IsIconic(self.hwnd):
                    user32.ShowWindow(self.hwnd, 9)
                    time.sleep(0.6)
                rc = wt.RECT(); user32.GetClientRect(self.hwnd, ctypes.byref(rc))
                pt = wt.POINT(0, 0); user32.ClientToScreen(self.hwnd, ctypes.byref(pt))
                if rc.right > 200 and rc.bottom > 200:
                    return [pt.x, pt.y, rc.right, rc.bottom]
        import mss
        with mss.mss() as sct:
            m = sct.monitors[1]
        return [m["left"], m["top"], m["width"], m["height"]]   # запасной вариант: весь экран

    def focus(self):
        try:
            user32 = _user32()
            self.region()
            if self.hwnd:
                if user32.IsIconic(self.hwnd):
                    user32.ShowWindow(self.hwnd, 9)
                user32.SetForegroundWindow(self.hwnd)
                time.sleep(0.4)
        except Exception:
            pass

    # --- ввод/вывод ---
    def grab(self):
        import mss, numpy as np
        reg = self.region()
        with mss.mss() as sct:
            shot = sct.grab({"left": reg[0], "top": reg[1], "width": reg[2], "height": reg[3]})
        return reg, np.array(shot)[:, :, :3]

    def read(self):
        reg, img = self.grab()
        items = ocr_image(img, reg[0], reg[1])
        s = parse_items(items, (reg[2], reg[3]))
        self._last = img
        self.check_keys()                     # F7/F6, нажатые пока шёл OCR
        return s

    FAST_REGIONS = ((0.0, 0.18, 0.42, 0.72), (0.2, 0.76, 0.8, 0.96))      # панель Stand/Attribute, подпись предмета
    DIALOG_REGIONS = FAST_REGIONS + ((0.26, 0.48, 0.74, 0.88),)             # + центр экрана (окна Yes/No)

    def _read_regions(self, regions):
        reg, img = self.grab()
        h, w = img.shape[:2]
        items = []
        for fx0, fy0, fx1, fy1 in regions:
            x0, y0, x1, y1 = int(w * fx0), int(h * fy0), int(w * fx1), int(h * fy1)
            items += ocr_image(img[y0:y1, x0:x1], reg[0] + x0, reg[1] + y0)   # координаты сразу в экранных пикселях
        s = parse_items(items, (w, h))
        self._last = img
        self.check_keys()
        return s

    def read_fast(self):
        """Быстрое чтение: только панель Stand/Attribute и подпись предмета внизу (в разы меньше текста для OCR).
        Кнопок Yes/No, меню и окон тут нет - для них Bot.read(dialog=True / full=True)."""
        return self._read_regions(self.FAST_REGIONS)

    def read_dialog(self):
        """Как read_fast + центр экрана: видно предупреждения и кнопки Yes/No, но не весь экран."""
        return self._read_regions(self.DIALOG_REGIONS)

    def save_debug(self):
        try:
            import cv2
            _, img = self.grab()
            cv2.imwrite(LAST_SHOT, img)
        except Exception:
            pass

    SCAN = {**{str(i): i + 1 for i in range(1, 10)}, "0": 11, "m": 50, "ё": 41}   # скан-коды: работают на любой раскладке

    def key(self, k):
        import keyboard
        keyboard.send(self.SCAN.get(k, k))

    def click(self, x, y, hard=2):
        """Клик, который принимает Roblox: сначала 'наведение' (движение с небольшим сдвигом),
        пауза, потом нажатие с удержанием. Мгновенный pyautogui.click() Roblox часто игнорирует
        (кнопка подсвечивается, но не нажимается). hard=True - низкоуровневый mouse_event."""
        import pyautogui
        level = int(hard)                     # 0 pyautogui, 1 mouse_event, 2 SendInput (абсолютные координаты)
        if level < 2 or sys.platform != "win32":
            pyautogui.moveTo(x - 4, y - 3, duration=0.1)
            pyautogui.moveTo(x, y, duration=0.15)
            time.sleep(0.3)                   # дать интерфейсу Roblox заметить наведение
        if level >= 2 and sys.platform == "win32":
            self._send_input_click(x, y)
        elif level == 1 and sys.platform == "win32":
            u = ctypes.windll.user32
            u.SetCursorPos(int(x), int(y)); time.sleep(0.1)
            u.mouse_event(0x0002, 0, 0, 0, 0); time.sleep(0.15)   # LEFTDOWN
            u.mouse_event(0x0004, 0, 0, 0, 0)                      # LEFTUP
        else:
            pyautogui.mouseDown(); time.sleep(0.12); pyautogui.mouseUp()
        time.sleep(0.15)

    @staticmethod
    def _si_sender():
        from ctypes import wintypes
        u = ctypes.windll.user32
        class MI(ctypes.Structure):
            _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG), ("mouseData", wintypes.DWORD),
                        ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD),
                        ("dwExtraInfo", ctypes.c_void_p)]
        class INP(ctypes.Structure):
            class _U(ctypes.Union):
                _fields_ = [("mi", MI)]
            _anonymous_ = ("u",)
            _fields_ = [("type", wintypes.DWORD), ("u", _U)]
        vx, vy = u.GetSystemMetrics(76), u.GetSystemMetrics(77)
        vw, vh = max(1, u.GetSystemMetrics(78)), max(1, u.GetSystemMetrics(79))

        def send(flags, dx=0, dy=0):
            i = INP(type=0, mi=MI(dx, dy, 0, flags, 0, None))
            u.SendInput(1, ctypes.byref(i), ctypes.sizeof(INP))

        def move(x, y):
            send(0x8000 | 0x4000 | 0x0001, int((x - vx) * 65535 / vw), int((y - vy) * 65535 / vh))
        return send, move

    def maximize(self):
        """Развернуть окно Roblox: в маленьком окне инвентарь наезжает на панели и раскладка плывёт."""
        try:
            user32 = _user32(); self.region()
            if self.hwnd and not user32.IsZoomed(self.hwnd):
                user32.ShowWindow(self.hwnd, 3); time.sleep(1.5)
                user32.SetForegroundWindow(self.hwnd); time.sleep(1.0)
        except Exception:
            pass

    def drag(self, x1, y1, x2, y2):
        """Перетаскивание мышью через SendInput (так Roblox принимает нажатие)."""
        send, move = self._si_sender()
        move(x1, y1); time.sleep(0.25); send(0x0001, 2, 1); time.sleep(0.05); send(0x0001, -2, -1); time.sleep(0.2)
        send(0x0002); time.sleep(0.25)
        n = 12
        for i in range(1, n + 1):
            move(x1 + (x2 - x1) * i / n, y1 + (y2 - y1) * i / n); time.sleep(0.04)
        time.sleep(0.3); send(0x0004); time.sleep(0.4)

    @staticmethod
    def _send_input_click(x, y):
        """SendInput: абсолютное движение (0..65535 по виртуальному экрану) + мелкие сдвиги + клик.
        Roblox (Raw Input) иногда принимает только такой вариант."""
        from ctypes import wintypes
        u = ctypes.windll.user32
        class MI(ctypes.Structure):
            _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG), ("mouseData", wintypes.DWORD),
                        ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD),
                        ("dwExtraInfo", ctypes.c_void_p)]
        class INP(ctypes.Structure):
            class _U(ctypes.Union):
                _fields_ = [("mi", MI)]
            _anonymous_ = ("u",)
            _fields_ = [("type", wintypes.DWORD), ("u", _U)]
        vx, vy = u.GetSystemMetrics(76), u.GetSystemMetrics(77)
        vw, vh = max(1, u.GetSystemMetrics(78)), max(1, u.GetSystemMetrics(79))

        def send(flags, dx=0, dy=0):
            i = INP(type=0, mi=MI(dx, dy, 0, flags, 0, None))
            u.SendInput(1, ctypes.byref(i), ctypes.sizeof(INP))

        ax = int((x - vx) * 65535 / vw); ay = int((y - vy) * 65535 / vh)
        ABS = 0x8000 | 0x4000 | 0x0001                 # ABSOLUTE | VIRTUALDESK | MOVE
        send(ABS, ax, ay); time.sleep(0.08)
        send(0x0001, 2, 1); time.sleep(0.05)          # относительные микро-сдвиги: Raw Input видит движение
        send(0x0001, -2, -1); time.sleep(0.15)
        send(0x0002); time.sleep(0.12)                # LEFTDOWN
        send(0x0004)                                  # LEFTUP

    def click_frac(self, frac):
        x0, y0, w, h = self.region()
        self.click(x0 + w * frac[0], y0 + h * frac[1])

    def click_center(self):
        self.click_frac((0.5, 0.5))

    def check_keys(self):
        import keyboard
        if _STOP.is_set():
            raise Stop("остановлено F7")
        if os.path.exists(STOP_FILE):
            raise Stop("остановлено кнопкой в окне")
        if keyboard.is_pressed("f7"):
            raise Stop("остановлено F7")
        if keyboard.is_pressed("f6"):
            log("Пауза (F6 - продолжить)"); time.sleep(0.7)
            while not keyboard.is_pressed("f6"):
                if keyboard.is_pressed("f7"):
                    raise Stop("остановлено F7")
                time.sleep(0.1)
            time.sleep(0.7)
            self.focus()

    def sleep(self, sec):
        end = time.time() + sec
        while time.time() < end:
            self.check_keys(); time.sleep(0.1)

    def now(self):
        return time.time()

    def beep(self):
        try:
            import winsound
            for _ in range(4):
                winsound.Beep(1300, 250)
        except Exception:
            print("\a")


def get_ocr():
    """Распознавание текста. У разных версий rapidocr разные имена настроек (в 1.2.x при настройке детектора нужен
    det_model_path, иначе KeyError), поэтому пробуем варианты по очереди и берём первый, который прошёл пробный запуск."""
    global _ocr
    if _ocr is None:
        import numpy as np
        from rapidocr_onnxruntime import RapidOCR
        variants = (
            # быстрый режим: потоки 3 (16 по умолчанию тормозят), без растягивания маленьких вырезок, без классификатора угла
            ("быстрый, rapidocr 1.4", dict(intra_op_num_threads=3, inter_op_num_threads=1, det_limit_type="max",
                                         det_limit_side_len=960, use_cls=False)),
            ("быстрый, rapidocr 1.2", dict(det_model_path=None, det_limit_type="max", det_limit_side_len=960, use_angle_cls=False)),
            ("потоки", dict(intra_op_num_threads=3, inter_op_num_threads=1)),
            ("по умолчанию", {}),
        )
        probe = np.full((80, 320, 3), 255, np.uint8)
        for i, (name, kw) in enumerate(variants):
            try:
                cand = RapidOCR(**kw)
                cand(probe)                              # пробный запуск: ошибка может вылезти только на вызове
                _ocr = cand
                if i:
                    log(f"OCR: режим «{name}»")
                break
            except Exception as e:
                log(f"OCR: режим «{name}» не подошёл ({type(e).__name__}: {e})")
        if _ocr is None:
            raise RuntimeError("не удалось запустить распознавание текста (rapidocr), пришли arrow_bot_log.txt")
    return _ocr


OCR_MAX_W = 1280
AUTO_ARRANGE = "--arrange" in sys.argv   # авто-расстановка из инвентаря: по умолчанию выключена, включается флагом


def ocr_image(img, ox=0, oy=0):
    f = 1.0
    if img.shape[1] > OCR_MAX_W:          # большое окно: OCR на уменьшенной копии (в разы быстрее), координаты пересчитываем
        import cv2
        f = OCR_MAX_W / img.shape[1]
        img = cv2.resize(img, None, fx=f, fy=f, interpolation=cv2.INTER_AREA)
    res, _ = get_ocr()(img)
    items = []
    for box, text, score in (res or []):
        xs = [p[0] for p in box]; ys = [p[1] for p in box]
        items.append({"text": text.strip(), "x": ox + sum(xs) / 4 / f, "y": oy + sum(ys) / 4 / f})
    return items


# ---------- логика бота (не зависит от окружения - его можно проверять на симуляторе) ----------
class Bot:
    def __init__(self, env, assume_yes=False):
        self.env = env
        self.assume_yes = assume_yes
        self.slots = {}
        self.last_key = None
        self.counts = {"arrow": None, "fruit": None}
        self.depleted = {}               # стрела -> когда отметили "нет/закончилась" (идём дальше по списку ARROW_NAMES, через 10 минут пробуем снова)

    # --- чтение ---
    def read(self, full=False, dialog=False):
        """По умолчанию быстрое чтение (панель + подпись). Если панели нет (меню, окна, ошибка) или нужны кнопки
        диалога (full=True) - читает весь экран."""
        s = None
        if not full and hasattr(self.env, "read_fast"):
            s = self.env.read_dialog() if dialog else self.env.read_fast()
            if not s["has_panel"]:
                s = None
        if s is None:
            s = self.env.read()
        if s["error"]:
            s = self._wait_reconnect(s)
        if s["equipped"] in self.counts and s["count"] is not None:
            self.counts[s["equipped"]] = s["count"]
        return s

    def _wait_reconnect(self, s):
        """Disconnected. Есть кнопка Reconnect (обрыв интернета) - жмём её каждые ~20 сек. Нет (например, ошибка 267 после
        3 часов на публичном сервере) - ждём, пока человек зайдёт сам."""
        self.env.beep()
        log(f"Игра показывает Disconnected, жду до {RECONNECT_WAIT // 60} мин (F7 - стоп). Reconnect нажму сам, если он есть")
        end = self.env.now() + RECONNECT_WAIT
        tries = 0
        while self.env.now() < end:
            if s["error"] and s["reconnect_btn"]:
                tries += 1
                log(f"Нажимаю Reconnect (попытка {tries})")
                self.env.click(*s["reconnect_btn"])
                self.env.sleep(20)
            else:
                self.env.sleep(10)
            s = self.env.read()
            if not s["error"]:
                log("Связь вернулась, продолжаю")
                return s
        raise Stop("Disconnected, связь не вернулась за отведённое время")

    def wait_for(self, pred, timeout, interval=0.4, full=False):
        end = self.env.now() + timeout
        while True:
            self.env.sleep(0)
            s = self.read(full=full)
            if pred(s):
                return s
            if self.env.now() >= end:
                return None
            self.env.sleep(interval)

    def stable_panel(self):
        """Два одинаковых чтения подряд, чтобы не принять решение по промаху OCR."""
        prev = None
        for _ in range(6):
            s = self.read()
            if s["menu_play"]:
                return None                     # выкинуло в меню - основной цикл нажмёт Play
            cur = (norm(s["stand"]), norm(s["attr"] or ""))
            if s["stand"] and s["attr"] is not None and cur == prev:
                return s
            prev = cur; self.env.sleep(0.5)
        return None

    # --- из любого состояния -> в игру ---
    def ensure_in_game(self):
        plays = 0
        for _ in range(10):
            s = self.read()
            if s["changelog_close"]:
                log("Окно Changelogs -> нажимаю Close")
                if s["changelog_close"] == "frac":
                    self.env.click_frac(CLOSE_FRAC)
                else:
                    self.env.click(*s["changelog_close"])
                self.env.sleep(1.5)
                continue
            if not s["menu_play"]:
                return s
            if plays >= 3:
                break
            log("Главное меню -> нажимаю Play" + (f" (повтор {plays})" if plays else ""))
            self.env.click(*s["menu_play"], hard=(2, 1, 0)[plays])
            plays += 1
            self.env.sleep(4)
            self.wait_for(lambda x: not x["menu_play"], MENU_LOAD_WAIT, 1.0, full=True)
            self.env.sleep(6)   # дать игре догрузиться
        raise Stop("не смог выйти из главного меню")

    def ensure_panel(self, s=None):
        """Если панель Stand/Attribute скрыта - открыть клавишей M (клавиша переключает, поэтому не больше 2 нажатий)."""
        for _ in range(2):
            s = s or self.read()
            if s["has_panel"] or s["menu_play"]:
                return s
            log(f"Панель стенда не видна -> нажимаю {PANEL_KEY.upper()}")
            self.env.key(PANEL_KEY); self.env.sleep(0.6); s = None
        return self.read()

    # --- предметы ---
    def _probe(self, k):
        """Нажать слот k и прочитать, что в руках. Повторное нажатие той же клавиши в Roblox
        убирает предмет - тогда нажимаем ещё раз."""
        self.env.key(k); self.env.sleep(0.35)
        s = self.read()
        if s["equipped"] is None and self.last_key == k:
            self.env.key(k); self.env.sleep(0.45)
            s = self.read()
        self.last_key = k
        return s

    def equip(self, which, depth=0, name=None):
        """Взять в руки 'arrow' / 'fruit', даже если слоты перемешались (и даже если посреди поиска выкинуло в меню).
        name - конкретная стрела из ARROW_NAMES: если её в хотбаре нет, возвращает None (без остановки)."""
        if depth > 4:
            raise Stop("игра постоянно выкидывает в меню, предмет взять не удалось")
        ok = lambda x: x["equipped"] == which and (name is None or x.get("equipped_name") == name)
        mem = which if name is None else f"{which}:{name}"
        s = self.ensure_in_game()
        if ok(s):
            return s
        tried = []
        for k in [self.slots.get(mem), SLOT_DEFAULTS[which]]:
            if k and k not in tried:
                tried.append(k)
                s = self._probe(k)
                if s["menu_play"]:
                    return self.equip(which, depth + 1, name)
                if ok(s):
                    self.slots[mem] = k
                    return s
        log(f"Ищу '{name or which}' по слотам хотбара...")
        for k in HOTBAR_KEYS:
            s = self._probe(k)
            if s["menu_play"]:
                return self.equip(which, depth + 1, name)
            if s["equipped"] in ("arrow", "fruit"):
                self.slots[s["equipped"]] = k
                if s["equipped"] == "arrow" and s.get("equipped_name"):
                    self.slots[f"arrow:{s['equipped_name']}"] = k
                if ok(s):
                    log(f"'{name or which}' найден в слоте {k}")
                    return s
        if name is not None:
            return None                                # такой стрелы нет, решает вызывающий
        if AUTO_ARRANGE and sys.platform == "win32" and not getattr(self, "_arranged", {}).get(which):
            self._arranged = {**getattr(self, "_arranged", {}), which: True}
            if self.arrange(which):
                return self.equip(which, depth)
        if depth < 2:                                  # возможно, посреди поиска умер и слоты сбились - ищем заново
            log("Не нашёл, повторяю поиск...")
            return self.equip(which, depth + 1)
        raise Stop(f"в хотбаре нет предмета '{which}' (положи стрелу в хотбар и Rokakaka тоже; или запусти с --arrange)")

    def equip_arrow(self):
        """Стрела по приоритету из ARROW_NAMES: пока есть первая, крутим её; закончилась или её нет в хотбаре - следующая.
        Отметка "нет" ставится после двойной проверки (OCR мог ошибиться) и действует 10 минут, потом пробуем снова."""
        for name in ARROW_NAMES:
            if time.time() - self.depleted.get(name, 0) < 600:
                continue
            s = self.equip("arrow", name=name)
            if s is None:                                       # не нашли при полном переборе слотов: ещё один заход
                s = self.equip("arrow", name=name)
            if s is not None and s["count"] == 0:               # перепроверка: ноль мог быть ошибкой чтения
                self.env.sleep(0.5)
                s = self.read()
                if s["equipped"] != "arrow" or s.get("equipped_name") != name:
                    s = self.equip("arrow", name=name)
            if s is None or s["count"] == 0:
                self.depleted[name] = time.time()
                rest = [n for n in ARROW_NAMES if time.time() - self.depleted.get(n, 0) >= 600]
                log(f"'{name}' нет или закончились" + (f", перехожу на '{rest[0]}'" if rest else ""))
                continue
            self.arrow_name = name
            return s
        self.env.beep()
        raise Stop("стрелы закончились (ни одной из списка нет в хотбаре или счётчик 0)")

    # --- авто-расстановка предметов из инвентаря (Ё) ---
    INV_X0, INV_STEP, INV_Y, HOT_Y = 668 / 1920, 65 / 1920, 689 / 1009, 974 / 1009   # раскладка развёрнутого окна

    def arrange(self, which):
        """Предмета нет в хотбаре: по очереди перетаскиваем ячейки инвентаря в целевой слот, берём в руки и читаем
        подпись внизу. Подошло - оставляем; нет - возвращаем всё обратно. Ничего не используем (кликов по миру нет)."""
        env = self.env
        if not hasattr(env, "drag"):
            return False                                   # симулятор: инвентаря нет
        log(f"Ищу '{which}' в инвентаре (Ё)...")
        env.maximize()
        key = SLOT_DEFAULTS[which]
        idx = lambda k: 9 if k == "0" else int(k) - 1
        def pt(i, y):
            x0, y0, w, h = env.region()
            return x0 + w * (self.INV_X0 + self.INV_STEP * i), y0 + h * y
        cell = lambda i: pt(i, self.INV_Y)
        slot = lambda k: pt(idx(k), self.HOT_Y)

        def inv(open_):
            for _ in range(3):
                if self.read()["inv_open"] == open_:
                    return True
                env.key("ё"); env.sleep(1.6)
            return self.read()["inv_open"] == open_

        def slot_crop():
            reg, img = env.grab()
            x, y = slot(key)
            x -= reg[0]; y -= reg[1]
            return img[max(0, int(y) - 22):int(y) + 22, max(0, int(x) - 22):int(x) + 22].astype(int)

        for i in range(9):
            if not inv(True):
                raise Stop("инвентарь не открылся (клавиша Ё)")
            before = slot_crop()
            env.drag(*cell(i), *slot(key)); env.sleep(0.5)
            if abs(slot_crop() - before).mean() < 3:
                continue                                   # ячейка пуста: ничего не переехало
            inv(False)
            s = self._probe(key)
            if s["equipped"] == which:
                self.slots[which] = key
                log(f"'{which}' лежал в ячейке {i + 1} инвентаря -> теперь в слоте {key}")
                return True
            if s["equipped"] is not None:
                env.key(key); env.sleep(0.5)               # убрать из рук
            self.last_key = None
            inv(True)
            env.drag(*slot(key), *cell(i)); env.sleep(0.5)  # вернуть на место (обмен обратно)
            inv(False)
        inv(False)
        return False

    # --- действия ---
    def roll(self):
        for attempt in range(3):
            s = self.equip_arrow()
            self.env.click_center()
            self.confirm_arrow()
            s = self.wait_for(lambda x: x["stand"] or not x["has_panel"], ROLL_TIMEOUT)
            if s and not s["has_panel"]:
                s = self.ensure_panel(s)
                s = s if s["stand"] else self.wait_for(lambda x: x["stand"], ROLL_TIMEOUT)
            if s and s["stand"]:
                return s
            log("Стенд не появился, пробую ещё раз")
        raise Stop("после стрелы стенд не появился (проверь, что панель Stand/Attribute видна на экране)")

    def confirm_arrow(self):
        """Стрела спрашивает подтверждение (Yes/No) - жмём Yes. Если окна нет (стенд уже выпал), ничего не делаем."""
        end = self.env.now() + 5
        while self.env.now() < end:
            s = self.read(dialog=True)
            if s["arrow_prompt"]:
                if s["yes"]: self.env.click(*s["yes"])
                else: self.env.click_frac(ARROW_YES_FRAC)
                self.env.sleep(0.8)
                return True
            if s["stand"] and s["has_panel"] and not s["warning"]:
                return False
            self.env.sleep(0.3)
        return False

    def confirm_delete(self, s, stand_name):
        """Перед нажатием Yes: до 3 чтений панели за диалогом; Yes только если >=2 раза 'delete' и ни разу 'keep'."""
        verdicts = []
        for i in range(3):
            same = fuzzy(s["stand"], [stand_name], 0.8) is not None
            verdicts.append(classify(s["stand"], s["attr"]) if same else "mismatch")
            if verdicts.count("delete") >= 2 and "keep" not in verdicts:
                return True, s
            if i < 2:
                self.env.sleep(0.4)
                s = self.read(dialog=True)
                if s["menu_play"] or not s["stand"]:
                    return None, s                 # диалог пропал (меню / стенд уже снесён) - ничего не кликаем
                if not s["warning"]:
                    break
        return False, s

    def delete(self, stand_name):
        for attempt in range(3):
            s = self.equip("fruit")
            if s["count"] == 0:
                self.env.beep(); raise Stop("Rokakaka закончились")
            self.env.click_center()
            end = self.env.now() + DIALOG_WAIT
            warn_since = None
            while self.env.now() < end:
                s = self.read(dialog=True)
                if s["menu_play"]:
                    return                      # выкинуло в меню - обработаем сверху
                if not s["has_panel"]:
                    s = self.ensure_panel(s)    # панель закрылась - откроем и перечитаем
                    if s["menu_play"]:
                        return
                if not s["stand"] and s["has_panel"]:
                    return                      # снесло без предупреждения
                if s["warning"]:
                    warn_since = warn_since or self.env.now()
                    if s["yes"] or self.env.now() - warn_since > NO_BUTTONS_FALLBACK:
                        ok, s = self.confirm_delete(s, stand_name)
                        if ok is None:
                            return
                        if not ok:
                            log(">>> панель изменилась / не уверен -> жму No и останавливаюсь")
                            if s["no"]: self.env.click(*s["no"])
                            else: self.env.click_frac(NO_FRAC)
                            raise Stop("остановился на предупреждении")
                        if s["yes"]: self.env.click(*s["yes"])
                        else: self.env.click_frac(YES_FRAC)
                        if self.wait_for(lambda x: not x["stand"] or x["menu_play"], 6):
                            return
                        break
                self.env.sleep(0.3)
            log("Стенд не удалился, пробую ещё раз")
        raise Stop("стенд не удалился (клик не прошёл?)")

    # --- главный цикл ---
    def run(self):
        n = 0
        unstable = 0
        s = self.ensure_panel(self.ensure_in_game())
        if s["stand"] and CONFIRM_EXISTING_STAND and not self.assume_yes:
            log(f"!!! Сейчас на тебе уже есть стенд: {s['stand']} / {s['attr']}")
            print("Если он не подходит по правилам, бот снесёт его Rokakaka.")
            if input("Продолжить? Напиши y и Enter (иначе выход): ").strip().lower() != "y":
                raise Stop("отменено")
            self.env.focus()
        while True:
            s = self.ensure_panel(self.ensure_in_game())
            if not s["stand"]:
                s = self.roll()
            s = self.stable_panel()
            if s is None:                       # меню или панель мигнула - начинаем цикл заново
                unstable += 1
                if unstable > 5:
                    raise Stop("панель стенда не читается (смотри arrow_bot_last.png и проверь, что панель Stand/Attribute видна)")
                continue
            unstable = 0
            n += 1
            OVL_STATS["n"] = n
            OVL_STATS["last"] = f"{s['stand']} / {s['attr']}"
            verdict = classify(s["stand"], s["attr"])
            log(f"#{n}: {s['stand']} | {s['attr']} -> {verdict}")
            OVL_STATS["verdict"] = verdict
            record_roll(n, s["stand"], s["attr"], verdict, self.counts["arrow"], self.counts["fruit"], getattr(self, "arrow_name", None))
            if verdict == "keep":
                self.env.beep()
                log(">>> ПОДХОДИТ! Стенд оставлен, фрукт не использован.")
                return "keep"
            if verdict == "unsure":
                self.env.beep()
                log(f">>> Не уверен: стенд '{s['stand']}', атрибут '{s['attr']}'. Посмотри сам.")
                return "unsure"
            self.delete(s["stand"])
            self.env.sleep(0.4)


# ---------- настройки из окна ----------
SETTINGS = {"overlay": True}


def load_settings():
    """arrow_settings.json (его пишет окно arrow_gui.pyw) перекрывает правила и параметры по умолчанию."""
    global ARROW_NAMES, ROLL_TIMEOUT, DIALOG_WAIT, RECONNECT_WAIT, CONFIRM_EXISTING_STAND
    try:
        with open(SETTINGS_FILE, encoding="utf-8") as f:
            cfg = json.load(f)
    except Exception:
        return
    SETTINGS.update(cfg)
    rules = cfg.get("stand_rules")
    if isinstance(rules, dict) and rules:
        STAND_RULES.clear()
        for name, attrs in rules.items():
            STAND_RULES[name] = set(attrs)
            STANDS.setdefault(name, 0)         # своё имя тоже должно опознаваться по OCR
    if int(cfg.get("defaults_version", 0)) < 2:
        STAND_RULES.setdefault("Premier Macho", L)
    for name in cfg.get("custom_stands") or []:
        STANDS.setdefault(name, 0)
    for name, ch in (cfg.get("stand_chances") or {}).items():       # шанс стенда, который игрок ввёл руками
        try:
            STANDS[name] = float(ch)
        except (TypeError, ValueError):
            pass
    if cfg.get("arrow_names"):
        names = list(cfg["arrow_names"])
        ARROW_NAMES[:] = ["Charged Arrow", "Stand Arrow"] if names == ["Charged Arrow"] else names   # старое значение по умолчанию -> новое
    sl = cfg.get("slots") or {}
    for k in ("arrow", "fruit"):
        if str(sl.get(k, "")) in list(HOTBAR_KEYS):
            SLOT_DEFAULTS[k] = str(sl[k])
    if cfg.get("roll_timeout"):
        ROLL_TIMEOUT = float(cfg["roll_timeout"])
    if cfg.get("dialog_wait"):
        DIALOG_WAIT = float(cfg["dialog_wait"])
    if cfg.get("reconnect_min"):
        RECONNECT_WAIT = int(cfg["reconnect_min"]) * 60


def record_roll(n, stand, attr, verdict, arrows, fruits, arrow=None):
    """Статистика для окна: строка в arrow_bot_stats.jsonl и снимок состояния."""
    if TESTING:
        return
    try:
        with open(STATS_FILE, "a", encoding="utf-8") as f:
            row = {"t": time.time(), "stand": stand, "attr": attr, "verdict": verdict}
            if arrow:
                row["arrow"] = arrow
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump({"n": n, "stand": stand, "attr": attr, "verdict": verdict, "arrows": arrows, "fruits": fruits,
                       "updated": time.time()}, f, ensure_ascii=False)
    except Exception:
        pass


# ---------- оверлей поверх Roblox ----------
def read_stat_rows():
    rows = []
    try:
        with open(STATS_FILE, encoding="utf-8") as f:
            for line in f:
                try:
                    rows.append(json.loads(line))
                except Exception:
                    pass
    except OSError:
        pass
    return rows


def analytics(rows):
    """Аналитика по броскам: скорость, шансы (по таблице шансов стендов и реальной частоте атрибутов), ожидание до нужного."""
    from collections import Counter
    n = len(rows)
    ts = [r.get("t", 0) for r in rows]
    gaps, last_by_src = [], {}
    for r in rows:                                                      # интервалы считаем внутри одного ПК (поле src), паузы дольше 3 минут не работа
        src, tt = r.get("src", "own"), r.get("t", 0)
        if src in last_by_src and 0 < tt - last_by_src[src] < 180:
            gaps.append(tt - last_by_src[src])
        last_by_src[src] = tt
    active = sum(gaps)
    per = active / len(gaps) if gaps else 0.0
    kept_idx = [i for i, r in enumerate(rows) if r.get("verdict") == "keep"]
    sc = Counter(r.get("stand") or "?" for r in rows)
    ac = Counter(str(r.get("attr")) for r in rows)
    # оценка шанса "нужное за один бросок": шанс стенда из таблицы x шанс его хороших атрибутов (частота из реальных бросков, со сглаживанием)
    tot_a = n + len(ALL_ATTRS)
    pa = lambda a: (ac.get(a, 0) + 1) / tot_a
    pools = {}
    for s_name, s_chance in STANDS.items():                              # стенды делятся по стрелам: у каждой свой набор шансов (сумма ~100%)
        pools.setdefault(STAND_POOL.get(s_name, "Charged Arrow"), {})[s_name] = s_chance

    def p_pool(pool):
        tot_p = sum(pool.values()) or 1
        return sum((pool.get(s_name, 0) / tot_p) * min(1.0, sum(pa(a) for a in attrs)) for s_name, attrs in STAND_RULES.items() if s_name in pool)
    arrow_cnt = Counter(r.get("arrow") or "Charged Arrow" for r in rows)
    weights = {a_name: c / n for a_name, c in arrow_cnt.items()} if n else {"Charged Arrow": 1.0}
    p_keep = sum(w * p_pool(pools.get(a_name) or pools.get("Charged Arrow", {})) for a_name, w in weights.items())
    exp_rolls = 1 / p_keep if p_keep > 0 else None
    p_hour = 1 - (1 - p_keep) ** (3600 / per) if per > 0 and p_keep > 0 else None
    seen = [(STANDS.get(s, 0), s) for s in sc if STANDS.get(s, 0) > 0]
    bins = Counter(int(x // 600) for x in ts)                           # бросков за каждые 10 минут
    series = [bins[k] for k in range(max(bins) - 11, max(bins) + 1)] if bins else []
    return {"n": n, "kept": len(kept_idx), "active": active, "last_t": ts[-1] if ts else None, "per": per,
            "per_hour": 3600 / per if per else 0.0, "since_keep": (n - 1 - kept_idx[-1]) if kept_idx else n,
            "p_keep": p_keep, "exp_rolls": exp_rolls, "exp_time": exp_rolls * per if exp_rolls and per else None,
            "p_hour": p_hour, "rarest": min(seen) if seen else None,
            "good_attr": sum(1 for r in rows if str(r.get("attr")) in GOOD_ATTRS) / n if n else 0.0,
            "stands": sc.most_common(), "attrs": ac.most_common(), "speed": gaps[-24:], "series": series}


def total_stats():
    """Совместимость: краткая сводка за всё время (для панели поверх игры)."""
    a = analytics(read_stat_rows())
    return {"n": a["n"], "kept": a["kept"], "active": a["active"], "last_t": a["last_t"],
            "stands": a["stands"][:3], "attrs": a["attrs"][:3], "a": a}


def fmt_hms(sec):
    sec = int(sec)
    return f"{sec // 3600}:{sec % 3600 // 60:02d}:{sec % 60:02d}"


def start_overlay(env):
    """HUD поверх игры в стиле окна Arrow Bot: сквозной для мыши, без фокуса и ИСКЛЮЧЁН из захвата экрана
    (SetWindowDisplayAffinity), поэтому бот не читает собственную панель. Нет поддержки (старая Windows) - тихо не показываем."""
    if sys.platform != "win32":
        return
    import threading

    def run():
        try:
            import math
            import tkinter as tk
            import tkinter.font as tkfont
            u = ctypes.windll.user32
            INK, PANEL, CARD, OUT, PAPER = "#130E26", "#1A1438", "#221A4A", "#06030D", "#EAE6FF"
            GOLD, VIO, PINK, ORANGE, MUT, DEEP = "#FFC93C", "#8B7BFF", "#FF4F8B", "#FF9F43", "#9A91CF", "#5B3FD6"

            root = tk.Tk()
            fams = set(tkfont.families())                 # шрифты можно спрашивать только после создания окна
            D = next((f for f in ("Bahnschrift SemiBold Condensed", "Bahnschrift SemiCondensed", "Impact", "Arial Black") if f in fams), "Segoe UI")
            root.overrideredirect(True)
            root.attributes("-topmost", True)
            root.attributes("-alpha", 0.94)
            root.configure(bg=OUT)
            frame = tk.Frame(root, bg=INK)
            frame.pack(fill="both", expand=True, padx=3, pady=3)          # 3 px чёрного контура вокруг HUD

            hdr = tk.Frame(frame, bg=INK)
            hdr.pack(fill="x", padx=10, pady=(8, 0))
            tk.Label(hdr, text="ARROW BOT", font=(D, 17), fg=PAPER, bg=INK).pack(side="left")
            tk.Label(hdr, text="Работает  ゴゴゴ", font=(D, 11), fg=INK, bg=GOLD, padx=8, pady=1).pack(side="left", padx=(10, 0))
            tk.Label(hdr, text="F6 пауза   F7 стоп", font=("Segoe UI", 9), fg=MUT, bg=INK).pack(side="right")
            tk.Frame(frame, bg=GOLD, height=3).pack(fill="x", padx=10, pady=(6, 0))

            drop = tk.Frame(frame, bg=INK)
            drop.pack(fill="x", padx=10, pady=(8, 0))
            lastlbl = tk.Label(drop, text="ждём первый бросок", font=(D, 19), fg=PAPER, bg=INK, anchor="w")
            lastlbl.pack(side="left")
            stamp = tk.Label(drop, text="", font=(D, 13), padx=8, pady=1)
            stamp.pack(side="right")

            nums = tk.Frame(frame, bg=INK)
            nums.pack(fill="x", padx=10, pady=(8, 0))
            boxes = {}
            for i, (k, cap) in enumerate((("n", "бросков за сессию"), ("per", "секунд на бросок"), ("time", "время сессии"))):
                nums.columnconfigure(i, weight=1, uniform="n")
                bx = tk.Frame(nums, bg=CARD, highlightthickness=2, highlightbackground=OUT)
                bx.grid(row=0, column=i, sticky="ew", padx=(0 if i == 0 else 6, 0))
                tk.Frame(bx, bg=VIO, height=4).pack(fill="x")
                v = tk.Label(bx, text="–", font=(D, 22), fg=PAPER, bg=CARD, anchor="w")
                v.pack(fill="x", padx=8)
                tk.Label(bx, text=cap, font=("Segoe UI", 8), fg=MUT, bg=CARD, anchor="w").pack(fill="x", padx=8, pady=(0, 4))
                boxes[k] = v

            mid = tk.Frame(frame, bg=INK)
            mid.pack(fill="x", padx=10, pady=(8, 0))
            pent = tk.Canvas(mid, width=172, height=150, bg=PANEL, highlightthickness=2, highlightbackground=OUT)
            pent.pack(side="left")
            info = tk.Frame(mid, bg=INK)
            info.pack(side="left", padx=(12, 0), fill="both", expand=True)
            big = tk.Label(info, text="–", font=(D, 28), fg=GOLD, bg=INK, anchor="w")
            big.pack(fill="x")
            tk.Label(info, text="шанс нужного за бросок", font=("Segoe UI", 9), fg=MUT, bg=INK, anchor="w").pack(fill="x")
            wait = tk.Label(info, text="", font=("Segoe UI Semibold", 10), fg=PAPER, bg=INK, anchor="w", justify="left")
            wait.pack(fill="x", pady=(6, 0))
            hour = tk.Label(info, text="", font=("Segoe UI", 10), fg=PAPER, bg=INK, anchor="w", justify="left")
            hour.pack(fill="x")
            total = tk.Label(info, text="", font=("Segoe UI", 9), fg=MUT, bg=INK, anchor="w", justify="left")
            total.pack(fill="x", pady=(6, 0))

            spark = tk.Canvas(frame, height=62, bg=PANEL, highlightthickness=2, highlightbackground=OUT)
            spark.pack(fill="x", padx=10, pady=(8, 0))
            body = tk.Label(frame, text="", font=("Consolas", 9), fg=MUT, bg=INK, justify="left", anchor="w")
            body.pack(fill="x", padx=10, pady=(6, 8))

            root.update_idletasks()
            hwnd = u.GetParent(root.winfo_id()) or root.winfo_id()
            ex = u.GetWindowLongW(hwnd, -20)
            u.SetWindowLongW(hwnd, -20, ex | 0x80000 | 0x20 | 0x08000000 | 0x80)   # LAYERED | TRANSPARENT | NOACTIVATE | TOOLWINDOW
            if os.environ.get("ARROWBOT_OVERLAY_DEBUG"):
                pass                                                                   # отладка: HUD виден на скриншотах
            elif not u.SetWindowDisplayAffinity(hwnd, 0x11):                         # EXCLUDEFROMCAPTURE
                root.destroy()
                return
            W = 500
            cache = {"t": 0, "a": None, "st": {}}

            def draw_pent(an, st):
                pent.delete("all")
                w, h = 172, 150
                cx, cy, R = w / 2, h / 2 + 8, 40
                pt = lambda i, k: (cx + R * k * math.cos(math.radians(-90 + 72 * i)), cy + R * k * math.sin(math.radians(-90 + 72 * i)))
                items = (("скорость", min(1.0, an["per_hour"] / 240) if an["per_hour"] else 0.0),
                         ("стрелы", (st.get("arrows") or 0) / 20000), ("Rokakaka", (st.get("fruits") or 0) / 20000),
                         ("атрибуты", min(1.0, an["good_attr"] / 0.25)), ("шанс/час", an["p_hour"] or 0.0))
                for k in (0.5, 1.0):
                    pent.create_polygon([c for i in range(5) for c in pt(i, k)], fill="", outline="#5b49b8" if k == 1.0 else "#33296B", width=2 if k == 1.0 else 1)
                for i in range(5):
                    pent.create_line(cx, cy, *pt(i, 1.0), fill="#33296B")
                vals = [max(0.05, min(1.0, v)) for _, v in items]
                pent.create_polygon([c for i, v in enumerate(vals) for c in pt(i, v)], fill=VIO, stipple="gray50", outline=GOLD, width=2)
                rank = lambda v: "A" if v >= 0.8 else "B" if v >= 0.6 else "C" if v >= 0.4 else "D" if v >= 0.2 else "E"
                rcol = {"A": GOLD, "B": "#B7A9FF", "C": PAPER, "D": MUT, "E": PINK}
                for i, (name, v) in enumerate(items):
                    x, y = pt(i, 1.0)
                    ox, oy = x + (x - cx) * 0.52, y + (y - cy) * 0.52
                    r = rank(v)
                    pent.create_text(ox, oy - 6, text=r, fill=rcol[r], font=(D, 14))
                    pent.create_text(ox, oy + 8, text=name, fill=MUT, font=("Segoe UI", 7))

            def refresh():
                try:
                    x0, y0, w, h = env.region()
                    root.update_idletasks()
                    root.geometry(f"{W}x{root.winfo_reqheight()}+{x0 + w - W - 12}+{y0 + 44}")
                except Exception:
                    pass
                now = time.time()
                if OVL_STATS["t0"] is None:
                    OVL_STATS["t0"] = now
                el = now - OVL_STATS["t0"]
                n = OVL_STATS["n"]
                if now - cache["t"] > 2 or cache["a"] is None:               # файлы статистики читаем раз в 2 секунды
                    cache["t"], cache["a"] = now, analytics(read_stat_rows())
                    try:
                        with open(STATE_FILE, encoding="utf-8") as f:
                            cache["st"] = json.load(f)
                    except Exception:
                        pass
                an, st = cache["a"], cache["st"]
                boxes["n"].config(text=str(n))
                boxes["per"].config(text=f"{el / n:.0f}" if n else "–")
                boxes["time"].config(text=fmt_hms(el))
                if OVL_STATS["last"]:
                    lastlbl.config(text=OVL_STATS["last"][:30])
                    v = OVL_STATS.get("verdict")
                    if v == "keep":
                        stamp.config(text="ОСТАВИТЬ!!", fg=GOLD, bg=OUT)
                    elif v == "unsure":
                        stamp.config(text="не уверен", fg=INK, bg=ORANGE)
                    else:
                        stamp.config(text="снести", fg=DEEP, bg=PAPER)
                big.config(text=f"{an['p_keep'] * 100:.2f}%" if an["p_keep"] else "–")
                if an["exp_rolls"]:
                    wait.config(text=f"ждать ~{an['exp_rolls']:.0f} бросков" + (f" (~{fmt_hms(an['exp_time'])})" if an["exp_time"] else ""))
                hour.config(text=(f"за час найдём: {an['p_hour'] * 100:.0f}%\n" if an["p_hour"] is not None else "")
                            + f"с последнего нужного: {an['since_keep']}")
                act = an["active"] + (now - an["last_t"] if an["last_t"] and now - an["last_t"] < 180 else 0)
                total.config(text=f"всего {an['n']} бросков, {fmt_hms(act)}, нужных {an['kept']}")
                draw_pent(an, st)
                spark.delete("all")
                sp = an["speed"]
                if sp:
                    cw = max(spark.winfo_width(), 200)
                    mx = max(sp) or 1
                    bw = (cw - 8) / len(sp)
                    for i, val in enumerate(sp):
                        hh = 4 + 30 * val / mx
                        col = GOLD if val <= an["per"] * 1.1 else PINK
                        spark.create_rectangle(4 + i * bw, 58 - hh, 4 + (i + 1) * bw - 2, 58, fill=col, outline=OUT, width=1)
                    spark.create_text(6, 3, text=f"секунд на бросок, последние {len(sp)}: золотые быстрее среднего", fill=MUT, anchor="nw", font=("Segoe UI", 8))
                body.config(text="\n".join(l[:70] for l in OVL_LINES[-2:]))
                root.after(500, refresh)

            def report(*exc):                         # ошибки оверлея не должны исчезать молча
                import traceback
                try:
                    with open(os.path.join(APP_DIR, "arrow_overlay_error.txt"), "a", encoding="utf-8") as ef:
                        ef.write("".join(traceback.format_exception(*exc)) + "\n")
                except Exception:
                    pass
                root.after(1000, refresh)              # и не даём обновлению остановиться
            root.report_callback_exception = report
            refresh()
            root.mainloop()
        except Exception:
            import traceback
            try:
                with open(os.path.join(APP_DIR, "arrow_overlay_error.txt"), "a", encoding="utf-8") as ef:
                    ef.write(traceback.format_exc() + "\n")
            except Exception:
                pass

    threading.Thread(target=run, daemon=True).start()


# ---------- команды ----------
def analyze(path=None):
    if path:
        import cv2
        img = cv2.imread(path)
        s = parse_items(ocr_image(img), (img.shape[1], img.shape[0]))
    else:
        env = Env()
        print("Вывожу Roblox вперёд, снимок через 3 секунды...")
        env.focus(); time.sleep(3)
        s = env.read()
        print("Окно игры:", env.region())
        env.save_debug()                 # кадр в arrow_bot_last.png - его можно прислать, если бот ничего не видит
    print(json.dumps(s, ensure_ascii=False, indent=1))
    if not (s["stand"] or s["has_panel"] or s["equipped"] or s["menu_play"] or s["warning"] or s["arrow_prompt"]):
        print("Ничего не распознал. Проверь: Roblox открыт и виден, панель Stand/Attribute открыта (клавиша M),"
              " Charged Arrow взята в руки (нажми её слот: внизу должна появиться подпись 'Charged Arrow: N / M')."
              " Потом запусти analyze ещё раз. Если всё так и не видно - пришли arrow_bot_last.png из этой папки.")
    if s["stand"]:
        print("Вердикт:", classify(s["stand"], s["attr"]))
    elif s["menu_play"]:
        print("Вижу главное меню (кнопка Play) - бот нажмёт её сам.")


def main():
    if sys.platform == "win32":
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except Exception:
            pass
    args = sys.argv[1:]
    load_settings()
    try:
        os.remove(STOP_FILE)
    except OSError:
        pass
    if args and args[0] == "analyze":
        return analyze(args[1] if len(args) > 1 else None)
    import pyautogui
    pyautogui.FAILSAFE = True; pyautogui.PAUSE = 0.05
    env = Env()
    try:
        import keyboard
        keyboard.add_hotkey("f7", _STOP.set)   # стоп с первого нажатия, даже посреди OCR
    except Exception:
        pass
    if "--no-overlay" not in args and SETTINGS.get("overlay", True):
        start_overlay(env)
    log("Старт. F6 пауза, F7 стоп. Фокус на Roblox через 3 сек...")
    time.sleep(3)
    env.focus()
    try:
        Bot(env, assume_yes="--yes" in args).run()
    except Stop as e:
        log(f"Стоп: {e}")
        env.save_debug()
    except Exception as e:           # любая неожиданность - не молча
        log(f"Ошибка: {type(e).__name__}: {e}")
        env.save_debug()
        raise


if __name__ == "__main__":
    main()
