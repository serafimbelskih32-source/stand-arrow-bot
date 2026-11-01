"""
Arrow Bot: окно управления для arrow_bot.py (двойной клик, терминал не нужен).
Старт/Стоп, статистика, редактор правил (какие стенды с какими атрибутами оставлять), настройки.
Кладётся в одну папку с arrow_bot.py. Правила и настройки хранятся в arrow_settings.json рядом.
"""
import os, sys, json, time, queue, threading, subprocess, importlib.util
import tkinter as tk
from tkinter import ttk, messagebox

APP_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, APP_DIR)
import arrow_bot as ab

BUILTIN_STANDS = frozenset(ab.STANDS)      # стенды из таблицы шансов; остальные добавил игрок и их можно убрать

BOT = os.path.join(APP_DIR, "arrow_bot.py")
CREATE_NO_WINDOW = 0x08000000
REQUIRED = ["mss", "pyautogui", "keyboard", "rapidocr_onnxruntime", "cv2", "numpy"]
PIP_PACKAGES = ["mss", "pyautogui", "keyboard", "rapidocr-onnxruntime", "opencv-python", "numpy"]

# палитра
# чернильный индиго, золото DIO для нужного, фиолет Star Platinum для данных, розовый для остановки и сноса
BG, PANEL, CARD, FG, MUTED = "#130E26", "#1A1438", "#221A4A", "#F1EEFF", "#9A91CF"
OUTLINE, PAPER, INK = "#06030D", "#EAE6FF", "#130E26"
GREEN, RED, YELLOW, BLUE = "#FFC93C", "#FF4F8B", "#FF9F43", "#8B7BFF"          # GREEN = золото (хорошее/нужное)
VIOLET_DEEP = "#5B3FD6"


def pick_font(*names):
    import tkinter.font as tkfont
    have = set(tkfont.families())
    for n in names:
        if n in have:
            return n
    return "Segoe UI"


_DISPLAY = None


def disp(size, weight="normal"):
    """Плакатный узкий шрифт для цифр и заголовков (Bahnschrift Condensed, иначе Impact)."""
    global _DISPLAY
    if _DISPLAY is None:
        _DISPLAY = pick_font("Bahnschrift SemiBold Condensed", "Bahnschrift SemiCondensed", "Impact", "Arial Black")
    return (_DISPLAY, size, weight)

# цвет каждого стенда по его образу (строка таблицы подкрашивается этим цветом)
STAND_COLORS = {
    "Silver Chariot": "#b8c4d6", "Crazy Diamond": "#f472b6", "Star Platinum": "#8b5cf6", "Hierophant Green": "#22c55e",
    "Killer Queen": "#e879f9", "The Hand": "#3b82f6", "Golden Experience": "#f59e0b", "King Crimson": "#ef4444",
    "Tusk Act 1": "#fb923c", "The World": "#facc15", "Dirty Deeds Done Dirt Cheap": "#38bdf8", "Whitesnake": "#e5e7eb",
    "The World: Alternate Universe": "#f97316", "Vanilla Ice's Cream": "#67e8f9", "The World OVA": "#eab308",
    "Star Platinum OVA": "#a78bfa", "Magician's Red OVA": "#dc2626", "Silver Chariot OVA": "#cbd5e1",
    "DIO's The World": "#fde047", "Jotaro's Star Platinum": "#7c3aed", "Putrid Whine": "#84cc16",
    "The Universe, Vestige": "#6366f1", "Shadow The Universe": "#a855f7", "Sol Spirit": "#fb923c",
    "Sol Spirit, Obscura": "#c2410c", "Doppio's King Crimson, Alternate Universe": "#be123c",
}


def auto_color(name):
    """Цвет для стенда без заданного: стабильно по названию (один и тот же стенд всегда один и тот же цвет)."""
    import colorsys, hashlib
    h = int(hashlib.md5(name.encode("utf-8")).hexdigest()[:6], 16) / 0xFFFFFF
    r, g, b = colorsys.hsv_to_rgb(h, 0.55, 0.92)
    return "#%02x%02x%02x" % (int(r * 255), int(g * 255), int(b * 255))


def blend(c1, c2, k):
    """Смешать два цвета #rrggbb: k - доля второго."""
    a = [int(c1[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(c2[i:i + 2], 16) for i in (1, 3, 5)]
    return "#%02x%02x%02x" % tuple(round(x + (y - x) * k) for x, y in zip(a, b))


ATTRS = list(ab.ALL_ATTRS)
BAD_ATTRS = {"None", "Strong", "Tough", "Sloppy", "Powerful", "Enrage", "Manic", "Lethargic", "Godly"}
DEFAULT_RULES = {k: sorted(v) for k, v in ab.STAND_RULES.items()}


UPDATE_FILES = ("arrow_bot.py", "arrow_gui.pyw", "install.bat", "README.txt", "INSTALL.txt", "history_import.jsonl")
IMPORT_FILE = os.path.join(APP_DIR, "history_import.jsonl")


def ver_tuple(v):
    try:
        return tuple(int(x) for x in str(v).split("."))
    except ValueError:
        return (0,)


def zip_version(zip_path):
    """Версия из arrow_bot.py внутри архива (строка VERSION = "x.y") или None, если это не наш архив."""
    import zipfile, re
    try:
        with zipfile.ZipFile(zip_path) as z:
            names = {os.path.basename(n): n for n in z.namelist()}
            if "arrow_bot.py" not in names or "arrow_gui.pyw" not in names:
                return None
            m = re.search(r'^VERSION\s*=\s*"([\d.]+)"', z.read(names["arrow_bot.py"]).decode("utf-8", "replace"), re.M)
            return m.group(1) if m else "0"
    except Exception:
        return None


def find_update_zips():
    """Свежие архивы arrow_bot*.zip в обычных местах (Загрузки, Telegram Desktop, рабочий стол), новые первыми."""
    home = os.path.expanduser("~")
    dirs = [os.path.join(home, "Downloads"), os.path.join(home, "Downloads", "Telegram Desktop"),
            os.path.join(home, "Desktop"), os.path.join(home, "OneDrive", "Desktop"), os.path.join(home, "Documents"),
            APP_DIR, os.path.join(APP_DIR, "dist"), os.path.dirname(APP_DIR)]
    found = []
    for d in dirs:
        try:
            for f in os.listdir(d):
                if f.lower().startswith("arrow_bot") and f.lower().endswith(".zip"):
                    p = os.path.join(d, f)
                    if zip_version(p) is not None:
                        found.append((os.path.getmtime(p), p))
        except OSError:
            pass
    return [p for _, p in sorted(found, reverse=True)]


def apply_update(zip_path, app_dir):
    """Положить файлы из архива в app_dir, старые версии сохранить в backup/<время>. Настройки и статистику не трогает."""
    import zipfile, shutil
    backup = os.path.join(app_dir, "backup", time.strftime("%Y%m%d_%H%M%S"))
    os.makedirs(backup, exist_ok=True)
    with zipfile.ZipFile(zip_path) as z:
        names = {os.path.basename(n): n for n in z.namelist()}
        for fn in UPDATE_FILES:
            if fn not in names:
                continue
            dst = os.path.join(app_dir, fn)
            if os.path.exists(dst):
                shutil.copy2(dst, os.path.join(backup, fn))
            with open(dst, "wb") as f:
                f.write(z.read(names[fn]))
    return backup


def import_history():
    """Подмешать в статистику историю из history_import.jsonl (приходит в архиве). Свои броски не трогаем,
    дубли (то же время, стенд и атрибут) пропускаем, так что импорт можно повторять безопасно."""
    if not os.path.exists(IMPORT_FILE):
        return 0
    own = read_stats()
    key = lambda r: (round(float(r.get("t", 0)), 1), r.get("stand"), str(r.get("attr")))
    seen = {key(r) for r in own}
    new = []
    try:
        with open(IMPORT_FILE, encoding="utf-8") as f:
            for line in f:
                try:
                    r = json.loads(line)
                except Exception:
                    continue
                if key(r) in seen:
                    continue
                r.setdefault("src", "import")
                seen.add(key(r))
                new.append(r)
    except OSError:
        return 0
    if not new:
        return 0
    rows = sorted(own + new, key=lambda r: r.get("t", 0))
    tmp = ab.STATS_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    os.replace(tmp, ab.STATS_FILE)
    return len(new)


def python_exe():
    exe = sys.executable
    if os.path.basename(exe).lower() == "pythonw.exe":
        cand = os.path.join(os.path.dirname(exe), "python.exe")
        if os.path.exists(cand):
            return cand
    return exe


def default_cfg():
    return {"stand_rules": dict(DEFAULT_RULES), "arrow_names": list(ab.ARROW_NAMES),
            "slots": dict(ab.SLOT_DEFAULTS), "roll_timeout": ab.ROLL_TIMEOUT, "dialog_wait": ab.DIALOG_WAIT,
            "reconnect_min": 30, "overlay": True, "minimize": True,
            "custom_stands": [], "stand_chances": {}, "stand_colors": {}, "defaults_version": 2}


def load_cfg():
    cfg = default_cfg()
    fd = {}
    try:
        with open(ab.SETTINGS_FILE, encoding="utf-8") as f:
            fd = json.load(f)
            cfg.update(fd)
    except Exception:
        pass
    if fd and int(fd.get("defaults_version", 0)) < 2:           # старый файл настроек: добавляем новые стенды по умолчанию
        cfg["stand_rules"].setdefault("Premier Macho", ["Legendary"])
        cfg["defaults_version"] = 2
    if cfg.get("arrow_names") == ["Charged Arrow"]:               # старое значение по умолчанию -> список по приоритету
        cfg["arrow_names"] = ["Charged Arrow", "Stand Arrow"]
    return cfg


def save_cfg(cfg):
    with open(ab.SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=1)
    try:
        ab.load_settings()                       # окно считает шансы и статистику по тем же правилам, что и бот
    except Exception:
        pass


def read_stats():
    rows = []
    try:
        with open(ab.STATS_FILE, encoding="utf-8") as f:
            for line in f:
                try:
                    rows.append(json.loads(line))
                except Exception:
                    pass
    except Exception:
        pass
    return rows


class App:
    def __init__(self, root):
        self.root = root
        root.title(f"Arrow Bot  v{getattr(ab, 'VERSION', '?')}")
        root.geometry("1280x820")
        root.minsize(980, 640)
        root.configure(bg=BG)
        self.cfg = load_cfg()
        self.scrollables = []                 # области, которые крутятся колесом мыши (под курсором)
        self._saved_sig = None
        try:
            ab.load_settings()                # свои стенды и шансы из настроек
        except Exception:
            pass
        self.proc = None
        self.q = queue.Queue()
        self.t_start = None
        self.session_from = 0
        self.stop_asked = None
        self.rule_vars = {}
        self._style()
        self._build()
        self._refresh_rules_grid()
        self.tick()
        root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.check_deps()
        imported = import_history()
        if imported:
            self.add_log(f"Добавлена история прошлых бросков: {imported} (вкладки «Статистика» и «История»)")

    # ---------- оформление ----------
    def _style(self):
        s = ttk.Style()
        s.theme_use("clam")
        s.configure(".", background=BG, foreground=FG, fieldbackground=CARD, bordercolor=OUTLINE, lightcolor=CARD,
                    darkcolor=CARD, troughcolor=PANEL, font=("Segoe UI", 10))
        s.configure("TNotebook", background=BG, borderwidth=0)
        s.configure("TNotebook.Tab", background=PANEL, foreground=MUTED, padding=(20, 9), font=disp(12))
        s.map("TNotebook.Tab", background=[("selected", GREEN)], foreground=[("selected", INK)])
        s.configure("TFrame", background=BG)
        s.configure("Card.TFrame", background=CARD)
        s.configure("TLabel", background=BG, foreground=FG)
        s.configure("Card.TLabel", background=CARD, foreground=FG)
        s.configure("Muted.TLabel", background=BG, foreground=MUTED)
        s.configure("Big.TLabel", background=CARD, foreground=FG, font=disp(24))
        s.configure("Cap.TLabel", background=CARD, foreground=MUTED, font=("Segoe UI", 9))
        s.configure("TButton", background=CARD, foreground=FG, padding=(14, 8), borderwidth=2, bordercolor=OUTLINE, relief="solid")
        s.map("TButton", background=[("active", "#33296B")])
        s.configure("Go.TButton", background=GREEN, foreground=INK, font=disp(16), padding=(26, 8), borderwidth=3, bordercolor=OUTLINE)
        s.map("Go.TButton", background=[("active", "#FFD96B"), ("disabled", "#4a4130")], foreground=[("disabled", "#8d8366")])
        s.configure("Stop.TButton", background=RED, foreground="white", font=disp(16), padding=(26, 8), borderwidth=3, bordercolor=OUTLINE)
        s.map("Stop.TButton", background=[("active", "#FF7BA6"), ("disabled", "#4d2a41")], foreground=[("disabled", "#9c6f86")])
        s.configure("TCheckbutton", background=BG, foreground=FG, indicatorbackground=CARD, indicatorforeground=BG)
        s.map("TCheckbutton", indicatorbackground=[("selected", GREEN), ("!selected", CARD)],
              indicatorforeground=[("selected", INK), ("!selected", CARD)])
        s.configure("Vertical.TScrollbar", background=CARD, troughcolor=PANEL, arrowcolor=FG, bordercolor=PANEL,
                    lightcolor=CARD, darkcolor=CARD)
        s.configure("Card.TCheckbutton", background=CARD, foreground=FG)
        s.map("TCheckbutton", background=[("active", BG)])
        s.map("Card.TCheckbutton", background=[("active", CARD)])
        s.configure("TEntry", fieldbackground=CARD, foreground=FG, insertcolor=FG)
        s.configure("TSpinbox", fieldbackground=CARD, foreground=FG, insertcolor=FG, arrowcolor=FG)
        s.configure("Treeview", background=PANEL, fieldbackground=PANEL, foreground=FG, rowheight=27, borderwidth=0, font=("Segoe UI", 10))
        s.configure("Treeview.Heading", background=CARD, foreground=GREEN, font=disp(12), relief="flat", padding=(8, 6))
        s.map("Treeview", background=[("selected", "#33296B")], foreground=[("selected", PAPER)])
        s.map("Treeview.Heading", background=[("active", "#33296B")])

    def _wheel(self, e):
        """Колесо мыши крутит ту прокручиваемую область, над которой стоит курсор."""
        w = self.root.winfo_containing(e.x_root, e.y_root)
        while w is not None:
            if w in self.scrollables:
                w.yview_scroll(int(-e.delta / 120), "units")
                return
            w = w.master

    def scroll_canvas(self, host, **kw):
        """Холст с полосой прокрутки внутри host."""
        cv = tk.Canvas(host, highlightthickness=0, **kw)
        sb = ttk.Scrollbar(host, command=cv.yview)
        cv.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        cv.pack(side="left", fill="both", expand=True)
        self.scrollables.append(cv)
        return cv

    def hard_panel(self, parent, bg, bd=3, shadow=0, shadow_color=OUTLINE):
        """Панель в стиле манги: жирный контур и (по желанию) жёсткая тень вправо-вниз без размытия."""
        outer = tk.Frame(parent, bg=shadow_color if shadow else BG)
        inner = tk.Frame(outer, bg=bg, highlightthickness=bd, highlightbackground=OUTLINE, highlightcolor=OUTLINE)
        inner.pack(fill="both", expand=True, padx=(0, shadow), pady=(0, shadow))
        return outer, inner

    def card(self, parent, **kw):
        f = ttk.Frame(parent, style="Card.TFrame", padding=12)
        f.grid(**kw)
        return f

    # ---------- каркас ----------
    def _build(self):
        nb = ttk.Notebook(self.root)
        nb.pack(fill="both", expand=True, padx=12, pady=12)
        self.nb = nb
        self.tab_main = ttk.Frame(nb, padding=10)
        self.tab_rules = ttk.Frame(nb, padding=10)
        self.tab_set = ttk.Frame(nb, padding=16)
        self.tab_stats = ttk.Frame(nb, padding=10)
        self.tab_hist = ttk.Frame(nb, padding=10)
        self.tab_help = ttk.Frame(nb, padding=16)
        for tab, name in ((self.tab_main, "Главная"), (self.tab_rules, "Стенды и атрибуты"), (self.tab_set, "Настройки"),
                          (self.tab_stats, "Статистика"), (self.tab_hist, "История"), (self.tab_help, "Справка")):
            nb.add(tab, text=name)
        self._build_main()
        self._build_rules()
        self._build_settings()
        self._build_stats()
        self._build_history()
        self._build_help()

        def on_tab(_e):
            i = nb.index(nb.select())
            if i == 3:
                self.refresh_stats()
            elif i == 4:
                self.refresh_history(force=True)
        nb.bind("<<NotebookTabChanged>>", on_tab)

    # ---------- Главная ----------
    def _build_main(self):
        t = self.tab_main
        t.columnconfigure(0, weight=1)
        # шапка: логотип слева, кнопки и статус справа
        top = ttk.Frame(t)
        top.grid(row=0, column=0, sticky="ew")
        logo = tk.Frame(top, bg=BG)
        logo.pack(side="left")
        tk.Label(logo, text="ARROW BOT", font=disp(30), fg=PAPER, bg=BG).pack(side="left")
        tk.Label(logo, text=f"v{getattr(ab, 'VERSION', '?')}", font=("Segoe UI", 9, "bold"), fg=INK, bg=GREEN, padx=6, pady=1).pack(side="left", padx=(10, 0), pady=(10, 0))
        self.lbl_status = tk.Label(top, text="Остановлен", font=disp(16), fg=MUTED, bg=CARD, padx=16, pady=6,
                                   highlightthickness=3, highlightbackground=OUTLINE)
        self.lbl_status.pack(side="right")
        btns = ttk.Frame(top)
        btns.pack(side="right", padx=18)
        self.btn_start = ttk.Button(btns, text="СТАРТ", style="Go.TButton", command=self.start)
        self.btn_stop = ttk.Button(btns, text="СТОП", style="Stop.TButton", command=self.stop, state="disabled")
        self.btn_start.pack(side="left")
        self.btn_stop.pack(side="left", padx=(8, 0))
        ttk.Button(btns, text="Проверить, что бот видит", command=self.analyze).pack(side="left", padx=(14, 0))
        ttk.Button(btns, text="Обновить", command=self.update_app).pack(side="left", padx=(8, 0))

        self.banner = ttk.Label(t, text="", foreground=YELLOW, wraplength=1050)
        self.banner.grid(row=1, column=0, sticky="w")
        self.btn_install = ttk.Button(t, text="Установить недостающие библиотеки", command=self.install_deps)

        # центр: карта выпавшего | счётчики | пятиугольник параметров
        mid = ttk.Frame(t)
        mid.grid(row=3, column=0, sticky="ew", pady=(12, 10))
        for i, wgt in enumerate((5, 5, 5)):
            mid.columnconfigure(i, weight=wgt, uniform="mid")

        outer, card = self.hard_panel(mid, PAPER, bd=4, shadow=7, shadow_color="#6D4DFF")
        outer.grid(row=0, column=0, sticky="nsew", padx=(0, 14))
        tk.Label(card, text="последний выпавший", font=("Segoe UI", 9, "bold"), fg=VIOLET_DEEP, bg=PAPER).pack(anchor="w", padx=16, pady=(14, 0))
        self.lbl_last = tk.Label(card, text="–", font=disp(30), fg=INK, bg=PAPER, wraplength=330, justify="left", anchor="w")
        self.lbl_last.pack(anchor="w", padx=16, pady=(2, 0), fill="x")
        self.lbl_attr = tk.Label(card, text="", font=("Segoe UI Semibold", 16), fg=VIOLET_DEEP, bg=PAPER, anchor="w")
        self.lbl_attr.pack(anchor="w", padx=16, fill="x")
        self.lbl_verdict = tk.Label(card, text="", font=disp(20), fg=MUTED, bg=PAPER, padx=12, pady=3)
        self.lbl_verdict.pack(anchor="w", padx=16, pady=(14, 0))
        self.lbl_hint = tk.Label(card, text="", font=("Segoe UI", 10), fg=VIOLET_DEEP, bg=PAPER, wraplength=330, justify="left", anchor="w")
        self.lbl_hint.pack(anchor="w", padx=16, pady=(12, 14), fill="x")

        grid = ttk.Frame(mid)
        grid.grid(row=0, column=1, sticky="nsew", padx=(0, 14))
        self.vals = {}
        spec = (("n", "бросков", BLUE), ("rate", "секунд на бросок", BLUE), ("time", "время работы", BLUE),
                ("arrows", "стрел осталось", GREEN), ("fruits", "Rokakaka осталось", GREEN), ("kept", "найдено нужных", RED))
        for i, (key, cap, accent) in enumerate(spec):
            grid.columnconfigure(i % 2, weight=1, uniform="g")
            grid.rowconfigure(i // 2, weight=1)
            o, inner = self.hard_panel(grid, CARD, bd=3)
            o.grid(row=i // 2, column=i % 2, sticky="nsew", padx=(0 if i % 2 == 0 else 8, 0), pady=(0 if i < 2 else 8, 0))
            tk.Frame(inner, bg=accent, height=5).pack(fill="x")
            v = tk.Label(inner, text="–", font=disp(26), fg=FG, bg=CARD, anchor="w")
            v.pack(anchor="w", padx=12, pady=(6, 0), fill="x")
            tk.Label(inner, text=cap, font=("Segoe UI", 9), fg=MUTED, bg=CARD, anchor="w").pack(anchor="w", padx=12, pady=(0, 8), fill="x")
            self.vals[key] = v

        po, pin = self.hard_panel(mid, PANEL, bd=3)
        po.grid(row=0, column=2, sticky="nsew")
        self.cv_pent = tk.Canvas(pin, bg=PANEL, highlightthickness=0, height=250)
        self.cv_pent.pack(fill="both", expand=True)

        # низ: журнал и живые топы
        t.rowconfigure(5, weight=1)
        bottom = ttk.Frame(t)
        bottom.grid(row=5, column=0, sticky="nsew")
        bottom.rowconfigure(1, weight=1)
        bottom.columnconfigure(0, weight=3, uniform="b"); bottom.columnconfigure(1, weight=2, uniform="b")
        tk.Label(bottom, text="Журнал", font=disp(14), fg=PAPER, bg=BG).grid(row=0, column=0, sticky="w", pady=(0, 4))
        self.lbl_live = tk.Label(bottom, text="Статистика", font=disp(14), fg=PAPER, bg=BG)
        self.lbl_live.grid(row=0, column=1, sticky="w", padx=(14, 0), pady=(0, 4))
        lo, lin = self.hard_panel(bottom, PANEL, bd=3)
        lo.grid(row=1, column=0, sticky="nsew")
        lin.rowconfigure(0, weight=1); lin.columnconfigure(0, weight=1)
        self.log = tk.Text(lin, bg=PANEL, fg="#C9C2EE", insertbackground=FG, relief="flat", font=("Consolas", 10),
                           wrap="word", state="disabled", height=8, padx=8, pady=6)
        sb = ttk.Scrollbar(lin, command=self.log.yview)
        self.log.configure(yscrollcommand=sb.set)
        self.log.grid(row=0, column=0, sticky="nsew"); sb.grid(row=0, column=1, sticky="ns")
        live = ttk.Frame(bottom)
        live.grid(row=1, column=1, sticky="nsew", padx=(14, 0))
        live.columnconfigure(0, weight=1); live.rowconfigure(0, weight=1); live.rowconfigure(1, weight=1)
        o1, i1 = self.hard_panel(live, CARD, bd=3)
        o2, i2 = self.hard_panel(live, CARD, bd=3)
        o1.grid(row=0, column=0, sticky="nsew", pady=(0, 8)); o2.grid(row=1, column=0, sticky="nsew")
        self.cv_live_st = self.scroll_canvas(i1, bg=CARD, height=100)
        self.cv_live_at = self.scroll_canvas(i2, bg=CARD, height=100)
        self.log.tag_configure("good", foreground=GREEN)
        self.log.tag_configure("bad", foreground=MUTED)
        self.log.tag_configure("warn", foreground=YELLOW)
        self.log.tag_configure("err", foreground=RED)

    def reset_card(self):
        self.lbl_last.configure(text="–")
        self.lbl_attr.configure(text="")
        self.lbl_verdict.configure(text="", bg=PAPER)
        self.lbl_hint.configure(text="")

    def draw_pentagon(self, items):
        """Схема «параметров забега» как схема характеристик стенда: пять осей, ранги A-E на вершинах."""
        import math
        cv = self.cv_pent
        cv.delete("all")
        w, h = max(cv.winfo_width(), 300), max(cv.winfo_height(), 240)
        cx, cy, R = w / 2, h / 2 + 12, min(w, h) * 0.28
        pt = lambda i, k: (cx + R * k * math.cos(math.radians(-90 + 72 * i)), cy + R * k * math.sin(math.radians(-90 + 72 * i)))
        cv.create_text(14, 16, text="параметры забега", fill=PAPER, anchor="w", font=disp(14))
        for k in (0.25, 0.5, 0.75, 1.0):
            cv.create_polygon([c for i in range(5) for c in pt(i, k)], fill="", outline="#5b49b8" if k == 1.0 else "#33296B", width=2 if k == 1.0 else 1)
        for i in range(5):
            cv.create_line(cx, cy, *pt(i, 1.0), fill="#33296B")
        vals = [max(0.04, min(1.0, v)) for _, v in items]
        cv.create_polygon([c for i, v in enumerate(vals) for c in pt(i, v)], fill=BLUE, stipple="gray50", outline=GREEN, width=3)
        for i, v in enumerate(vals):
            x, y = pt(i, v)
            cv.create_oval(x - 4, y - 4, x + 4, y + 4, fill=GREEN, outline=OUTLINE, width=2)
        rank = lambda v: "A" if v >= 0.8 else "B" if v >= 0.6 else "C" if v >= 0.4 else "D" if v >= 0.2 else "E"
        rcol = {"A": GREEN, "B": "#B7A9FF", "C": FG, "D": MUTED, "E": RED}
        for i, (name, v) in enumerate(items):
            x, y = pt(i, 1.0)
            ox = x + (x - cx) * 0.34
            oy = y + (y - cy) * 0.34
            r = rank(v)
            cv.create_text(ox, oy - 9, text=r, fill=rcol[r], font=disp(22))
            cv.create_text(ox, oy + 11, text=name, fill=MUTED, font=("Segoe UI", 9))

    def refresh_pentagon(self):
        a = ab.analytics(read_stats())
        try:
            with open(ab.STATE_FILE, encoding="utf-8") as f:
                st = json.load(f)
        except Exception:
            st = {}
        speed = min(1.0, a["per_hour"] / 240) if a["per_hour"] else 0.0
        arrows = (st.get("arrows") or 0) / 20000
        fruits = (st.get("fruits") or 0) / 20000
        attrs = min(1.0, a["good_attr"] / 0.25)
        chance = a["p_hour"] or 0.0
        self.draw_pentagon([("Скорость", speed), ("Стрелы", arrows), ("Rokakaka", fruits), ("Атрибуты", attrs), ("Шанс за час", chance)])

    def add_log(self, line):
        tag = ""
        if "keep" in line or "ПОДХОДИТ" in line:
            tag = "good"
        elif "-> delete" in line:
            tag = "bad"
        elif "Стоп" in line or "Не уверен" in line or "Disconnected" in line:
            tag = "warn"
        elif "Ошибка" in line or "Traceback" in line:
            tag = "err"
        self.log.configure(state="normal")
        self.log.insert("end", line + "\n", tag)
        self.log.see("end")
        self.log.configure(state="disabled")

    # ---------- процесс бота ----------
    def check_deps(self):
        self.missing = [m for m in REQUIRED if importlib.util.find_spec(m) is None]
        if self.missing:
            self.banner.configure(text="Не хватает библиотек: " + ", ".join(self.missing) + ". Без них бот не запустится.")
            self.btn_install.grid(row=2, column=0, sticky="w", pady=4)
        else:
            self.banner.configure(text="")
            self.btn_install.grid_remove()

    def install_deps(self):
        self.add_log("Устанавливаю библиотеки (это минуты 2-5)...")
        self.btn_install.configure(state="disabled")
        cmd = [python_exe(), "-m", "pip", "install"] + PIP_PACKAGES
        self._spawn(cmd, after=lambda rc: (self.check_deps(), self.btn_install.configure(state="normal"),
                                           self.add_log("Готово" if rc == 0 else f"pip завершился с кодом {rc}")))

    def _spawn(self, cmd, after=None):
        env = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8")
        p = subprocess.Popen(cmd, cwd=APP_DIR, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=env,
                             creationflags=CREATE_NO_WINDOW if sys.platform == "win32" else 0,
                             text=True, encoding="utf-8", errors="replace", bufsize=1)

        def reader():
            for line in p.stdout:
                self.q.put(line.rstrip("\n"))
            rc = p.wait()
            self.q.put(("__done__", rc, after))
        threading.Thread(target=reader, daemon=True).start()
        return p

    def analyze(self):
        if self.proc:
            messagebox.showinfo("Arrow Bot", "Сначала останови бота.")
            return
        self.add_log("Проверка: вывожу Roblox вперёд и читаю экран (~10 секунд)...")
        self._spawn([python_exe(), BOT, "analyze"])

    def start(self, confirm=True):
        if self.proc:
            return
        if self.missing:
            messagebox.showwarning("Arrow Bot", "Сначала установи недостающие библиотеки (кнопка сверху).")
            return
        if confirm and not messagebox.askyesno("Старт", "Запустить бота?\n\n• Roblox должен быть открыт в игре, Charged Arrow и Rokakaka в хотбаре\n"
                                   "• Если на персонаже уже есть стенд: подходящий бот оставит и остановится, неподходящий снесёт Rokakaka\n"
                                   "• Остановка: кнопка СТОП или F7, пауза F6\n\nАвтокликеры формально против правил Roblox, риск на тебе."):
            return
        self.commit_rules()
        save_cfg(self.cfg)
        try:
            os.remove(ab.STOP_FILE)
        except OSError:
            pass
        self.t_start = time.time()
        self.session_from = time.time()
        self.stop_asked = None
        for k in ("n", "rate", "time", "arrows", "fruits"):
            self.vals[k].configure(text="–")
        self.vals["kept"].configure(text="0")
        self.reset_card()
        self.add_log("=== запуск ===")
        self.proc = self._spawn([python_exe(), BOT, "--yes"])
        self.btn_start.configure(state="disabled")
        self.btn_stop.configure(state="normal")
        self.set_status("Работает", GREEN)
        if self.cfg.get("minimize", True):
            self.root.after(600, self.root.iconify)

    def stop(self):
        if not self.proc:
            return
        try:
            open(ab.STOP_FILE, "w").close()
        except OSError:
            pass
        self.stop_asked = time.time()
        self.set_status("Останавливаю...", YELLOW)
        self.btn_stop.configure(state="disabled")

    def update_app(self):
        """Обновление: ищет новый arrow_bot*.zip в Загрузках (куда Telegram сохраняет файлы), ставит поверх с бэкапом, перезапускает окно."""
        from tkinter import filedialog
        if self.proc:
            messagebox.showinfo("Arrow Bot", "Сначала останови бота (кнопка СТОП).")
            return
        cur = getattr(ab, "VERSION", "0")
        zips = find_update_zips()
        path = None
        for p in zips:
            v = zip_version(p)
            if ver_tuple(v) > ver_tuple(cur):
                path = p
                break
        if path is None:
            if zips and not messagebox.askyesno("Обновление", f"Новее установленной версии v{cur} архива в Загрузках нет.\n"
                                                              f"Найден: {os.path.basename(zips[0])} (v{zip_version(zips[0])}). Всё равно поставить?"):
                return
            if not zips:
                messagebox.showinfo("Обновление", "Новый архив arrow_bot.zip не найден ни в Загрузках, ни на рабочем столе.\n"
                                    "Скачай его из Telegram и нажми Обновить ещё раз, либо выбери файл вручную в следующем окне.")
            path = zips[0] if zips else filedialog.askopenfilename(
                title="Выбери архив arrow_bot.zip", filetypes=[("zip", "*.zip")],
                initialdir=os.path.join(os.path.expanduser("~"), "Downloads"))
            if not path:
                return
        newv = zip_version(path)
        if newv is None:
            messagebox.showerror("Arrow Bot", "Это не архив Arrow Bot.")
            return
        if not messagebox.askyesno("Обновление", f"Обновить v{cur} → v{newv}?\n\nФайл: {path}\nСтарые файлы сохранятся в папке backup. Правила и статистика не пропадут."):
            return
        try:
            self.commit_rules()
            save_cfg(self.cfg)                       # несохранённые правки таблицы не должны пропасть при перезапуске окна
        except Exception:
            pass
        try:
            backup = apply_update(path, APP_DIR)
        except Exception as e:
            messagebox.showerror("Arrow Bot", f"Не получилось обновить: {e}")
            return
        messagebox.showinfo("Arrow Bot", f"Готово, версия v{newv}. Окно перезапустится.\nСтарые файлы: {backup}")
        gui = os.path.join(APP_DIR, "arrow_gui.pyw")
        exe = sys.executable
        subprocess.Popen([exe, gui], cwd=APP_DIR, creationflags=CREATE_NO_WINDOW if sys.platform == "win32" else 0)
        self.root.destroy()

    def set_status(self, text, color):
        """Плашка статуса: золотая когда работает или нашлось, розовая при остановке, тусклая когда стоим."""
        if color in (GREEN,):
            bg, fg = GREEN, INK
            if text == "Работает":
                text = "Работает   ゴゴゴ"
        elif color == YELLOW:
            bg, fg = YELLOW, INK
        else:
            bg, fg = CARD, MUTED
        self.lbl_status.configure(text=text, fg=fg, bg=bg)

    def on_proc_done(self, rc):
        self.proc = None
        self.btn_start.configure(state="normal")
        self.btn_stop.configure(state="disabled")
        try:
            os.remove(ab.STOP_FILE)
        except OSError:
            pass
        found = False
        try:
            with open(ab.LOG_FILE, encoding="utf-8") as f:
                tail = f.read()[-1500:]
            found = "ПОДХОДИТ" in tail and self.t_start and os.path.getmtime(ab.LOG_FILE) >= self.t_start
        except Exception:
            pass
        if found:
            self.set_status("НАЙДЕНО!", GREEN)
            self.root.deiconify(); self.root.lift(); self.root.attributes("-topmost", True)
            self.root.after(1500, lambda: self.root.attributes("-topmost", False))
            messagebox.showinfo("Arrow Bot", "Выпал нужный стенд! Бот остановился, ничего не удалил.\n" + self.lbl_last.cget("text"))
        else:
            self.set_status("Остановлен", MUTED)
            self.root.deiconify()

    # ---------- Стенды и атрибуты ----------
    def _build_rules(self):
        t = self.tab_rules
        t.columnconfigure(0, weight=1); t.rowconfigure(1, weight=1)
        ttk.Label(t, text="Отметь атрибуты, при которых стенд ОСТАВЛЯТЬ (бот остановится). "
                          "Стенда нет в таблице или атрибут не отмечен: бот сносит.", style="Muted.TLabel", wraplength=1080).grid(row=0, column=0, sticky="w")
        outer = ttk.Frame(t)
        outer.grid(row=1, column=0, sticky="nsew", pady=8)
        outer.rowconfigure(0, weight=1); outer.columnconfigure(0, weight=1)
        self.rcanvas = tk.Canvas(outer, bg=BG, highlightthickness=0)
        vs = ttk.Scrollbar(outer, orient="vertical", command=self.rcanvas.yview)
        self.rcanvas.configure(yscrollcommand=vs.set)
        self.rcanvas.grid(row=0, column=0, sticky="nsew"); vs.grid(row=0, column=1, sticky="ns")
        self.rinner = ttk.Frame(self.rcanvas)
        self.rcanvas.create_window((0, 0), window=self.rinner, anchor="nw")
        self.rinner.bind("<Configure>", lambda e: self.rcanvas.configure(scrollregion=self.rcanvas.bbox("all")))
        self.scrollables.append(self.rcanvas)
        self.rcanvas.bind_all("<MouseWheel>", self._wheel)
        bar = ttk.Frame(t)
        bar.grid(row=2, column=0, sticky="ew")
        self.new_stand = tk.StringVar()
        self.new_chance = tk.StringVar()
        ttk.Label(bar, text="Новый стенд:").pack(side="left", padx=(0, 6))
        ttk.Entry(bar, textvariable=self.new_stand, width=30).pack(side="left")
        ttk.Label(bar, text="шанс %:").pack(side="left", padx=(8, 4))
        ttk.Entry(bar, textvariable=self.new_chance, width=7).pack(side="left")
        ttk.Button(bar, text="Добавить стенд", command=self.add_stand).pack(side="left", padx=6)
        ttk.Button(bar, text="Добавить списком", command=self.bulk_add).pack(side="left", padx=(0, 6))
        ttk.Button(bar, text="Сбросить к стандартным", command=self.reset_rules).pack(side="left", padx=6)
        ttk.Button(bar, text="Сохранить", command=self.save_rules).pack(side="right")

    def chance_of(self, name):
        return self.cfg.get("stand_chances", {}).get(name) or ab.STANDS.get(name) or 0

    def rarity_key(self, name):
        """Редкие сверху; стенды без известного шанса в конец."""
        ch = self.chance_of(name)
        return (0 if ch else 1, ch or 0, name)

    def all_stand_names(self):
        names = set(ab.STANDS) | set(self.cfg["stand_rules"]) | set(self.cfg.get("custom_stands", []))
        return sorted(names, key=self.rarity_key)

    def _refresh_rules_grid(self):
        for w in self.rinner.winfo_children():
            w.destroy()
        self.rule_vars = {}
        g = self.rinner
        g.columnconfigure(0, minsize=250)
        for j in range(len(ATTRS)):
            g.columnconfigure(1 + j, minsize=52)
        g.columnconfigure(len(ATTRS) + 1, minsize=260)
        ttk.Label(g, text="Стенд (шанс %)").grid(row=0, column=0, sticky="w", pady=(0, 6))
        for j, a in enumerate(ATTRS):
            ttk.Label(g, text=a.replace(" ", "\n"), anchor="center", justify="center", font=("Segoe UI", 8),
                      foreground=(MUTED if a in BAD_ATTRS else GREEN)).grid(row=0, column=1 + j, pady=(0, 6))
        tk.Frame(g, height=2, bg="#5b6b85").grid(row=1, column=0, columnspan=len(ATTRS) + 2, sticky="ew")   # под шапкой
        st = ttk.Style()
        for i, name in enumerate(self.all_stand_names()):
            chance = self.chance_of(name)
            col = self.stand_color(name)
            bg = blend(BG, col, 0.20)
            sty = f"R{i}"
            st.configure(f"{sty}.TLabel", background=bg, foreground=col)
            st.configure(f"{sty}.TFrame", background=bg)
            st.configure(f"{sty}.TCheckbutton", background=bg, foreground=FG, indicatorbackground=CARD, indicatorforeground=bg)
            st.map(f"{sty}.TCheckbutton", background=[("active", bg)],
                   indicatorbackground=[("selected", GREEN), ("!selected", CARD)],
                   indicatorforeground=[("selected", "#06240f"), ("!selected", CARD)])
            ttk.Label(g, text=f"{name}  ({chance}%)" if chance else f"{name}  (шанс не задан)", wraplength=244, justify="left",
                      font=("Segoe UI", 9, "bold"), style=f"{sty}.TLabel").grid(row=2 * i + 2, column=0, sticky="nsew", ipady=4)
            have = set(self.cfg["stand_rules"].get(name, []))
            self.rule_vars[name] = {}
            for j, a in enumerate(ATTRS):
                v = tk.BooleanVar(value=a in have)
                self.rule_vars[name][a] = v
                cell = ttk.Frame(g, style=f"{sty}.TFrame")
                cell.grid(row=2 * i + 2, column=1 + j, sticky="nsew")
                ttk.Checkbutton(cell, variable=v, style=f"{sty}.TCheckbutton").pack(expand=True, pady=3)
            bf = ttk.Frame(g, style=f"{sty}.TFrame")
            bf.grid(row=2 * i + 2, column=len(ATTRS) + 1, sticky="nsew", padx=(0, 0))
            ttk.Button(bf, text="все", width=3, padding=(4, 3), command=lambda n=name: self.row_set(n, True)).pack(side="left", padx=1)
            ttk.Button(bf, text="нет", width=3, padding=(4, 3), command=lambda n=name: self.row_set(n, False)).pack(side="left", padx=1)
            ttk.Button(bf, text="цвет", width=4, padding=(4, 3), command=lambda n=name: self.pick_color(n)).pack(side="left", padx=(6, 1))
            if name not in BUILTIN_STANDS:                  # добавленный игроком стенд: можно задать шанс и убрать
                ttk.Button(bf, text="шанс", width=4, padding=(4, 3), command=lambda n=name: self.set_chance(n)).pack(side="left", padx=1)
                ttk.Button(bf, text="убрать", width=6, padding=(4, 3), command=lambda n=name: self.remove_stand(n)).pack(side="left", padx=1)
            # линия под строкой, как в таблице Excel
            tk.Frame(g, height=1, bg="#3a465c").grid(row=2 * i + 3, column=0, columnspan=len(ATTRS) + 2, sticky="ew")

    def stand_color(self, name):
        return (self.cfg.get("stand_colors", {}).get(name) or STAND_COLORS.get(name) or auto_color(name))

    def pick_color(self, name):
        from tkinter import colorchooser
        _, hexcol = colorchooser.askcolor(color=self.stand_color(name), title=f"Цвет для {name}")
        if hexcol:
            self.commit_rules()
            self.cfg.setdefault("stand_colors", {})[name] = hexcol
            save_cfg(self.cfg)
            self._refresh_rules_grid()

    def row_set(self, name, val):
        for v in self.rule_vars[name].values():
            v.set(val)

    def commit_rules(self):
        rules = {}
        for name, vs in self.rule_vars.items():
            attrs = [a for a, v in vs.items() if v.get()]
            if attrs:
                rules[name] = attrs
        self.cfg["stand_rules"] = rules

    def save_rules(self):
        self.commit_rules()
        save_cfg(self.cfg)
        n = len(self.cfg["stand_rules"])
        messagebox.showinfo("Arrow Bot", f"Сохранено. Оставляем {n} стендов, остальные сносим.\nДействует со следующего запуска бота.")

    def add_stand(self):
        name = self.new_stand.get().strip()
        if not name:
            return
        chance = None
        raw = self.new_chance.get().strip().replace(",", ".").replace("%", "")
        if raw:
            try:
                chance = float(raw)
            except ValueError:
                messagebox.showerror("Arrow Bot", "Шанс должен быть числом в процентах, например 0.3")
                return
        self.commit_rules()
        self.cfg["stand_rules"].setdefault(name, ["Legendary"])
        if name not in BUILTIN_STANDS and name not in self.cfg["custom_stands"]:
            self.cfg["custom_stands"].append(name)
        if chance is not None:
            self.cfg["stand_chances"][name] = chance
        self.new_stand.set("")
        self.new_chance.set("")
        save_cfg(self.cfg)
        self._refresh_rules_grid()
        self.rcanvas.yview_moveto(0)

    def bulk_add(self):
        """Окно для вставки сразу многих стендов: по одному в строке, 'название; шанс %; атрибуты через запятую'."""
        win = tk.Toplevel(self.root)
        win.title("Добавить стенды списком")
        win.configure(bg=BG)
        win.geometry("700x470")
        tk.Label(win, text="По одному стенду в строке: название; шанс %; атрибуты через запятую.\n"
                           "Шанс и атрибуты можно не писать (тогда оставляем при Legendary). Пример:\n"
                           "Premier Macho; 0.3; Legendary, Hacker", bg=BG, fg=FG, justify="left", anchor="w", font=("Segoe UI", 10)).pack(fill="x", padx=14, pady=(12, 6))
        txt = tk.Text(win, bg=PANEL, fg=FG, insertbackground=FG, font=("Segoe UI", 11), relief="flat", padx=8, pady=6)
        txt.pack(fill="both", expand=True, padx=14)

        def apply():
            known = list(ab.STANDS) + list(self.cfg.get("custom_stands", []))
            added = updated = 0
            self.commit_rules()
            for line in txt.get("1.0", "end").splitlines():
                line = line.strip()
                if not line:
                    continue
                parts = [x.strip() for x in line.split(";")]
                name, chance, attrs_raw = parts[0], None, (parts[2] if len(parts) > 2 else "")
                if len(parts) > 1 and parts[1]:
                    try:
                        chance = float(parts[1].replace(",", ".").replace("%", ""))
                    except ValueError:
                        chance = None
                elif len(parts) == 1:                          # "Название 0,3" без точки с запятой
                    pieces = name.rsplit(None, 1)
                    if len(pieces) == 2:
                        try:
                            chance, name = float(pieces[1].replace(",", ".").replace("%", "")), pieces[0]
                        except ValueError:
                            pass
                canon = ab.fuzzy(name, known, 0.9)             # то же имя, что уже есть: не плодим дубликаты
                if canon:
                    name = canon
                attrs = [a for a in (ab.fuzzy(x, ATTRS, 0.8) for x in attrs_raw.split(",") if x.strip()) if a] or ["Legendary"]
                if name in self.cfg["stand_rules"]:
                    updated += 1
                else:
                    added += 1
                self.cfg["stand_rules"][name] = attrs
                if name not in BUILTIN_STANDS and name not in self.cfg["custom_stands"]:
                    self.cfg["custom_stands"].append(name)
                if chance is not None:
                    self.cfg["stand_chances"][name] = chance
            save_cfg(self.cfg)
            self._refresh_rules_grid()
            win.destroy()
            messagebox.showinfo("Arrow Bot", f"Добавлено {added}, обновлено {updated}. Сохранено.")

        ttk.Button(win, text="Добавить", command=apply).pack(side="right", padx=14, pady=12)
        txt.focus_set()

    def set_chance(self, name):
        from tkinter import simpledialog
        v = simpledialog.askfloat("Шанс стенда", f"Шанс выпадения «{name}» за бросок, в процентах (например 0.3):",
                                  initialvalue=self.chance_of(name) or None, minvalue=0, maxvalue=100, parent=self.root)
        if v is None:
            return
        self.commit_rules()
        self.cfg["stand_chances"][name] = v
        save_cfg(self.cfg)
        self._refresh_rules_grid()

    def remove_stand(self, name):
        if not messagebox.askyesno("Убрать стенд", f"Убрать «{name}» из таблицы?\nСтатистика бросков не пострадает."):
            return
        self.commit_rules()
        for key in ("stand_rules", "stand_chances", "stand_colors"):
            self.cfg.get(key, {}).pop(name, None)
        if name in self.cfg.get("custom_stands", []):
            self.cfg["custom_stands"].remove(name)
        if name not in BUILTIN_STANDS:
            ab.STANDS.pop(name, None)
        save_cfg(self.cfg)
        self._refresh_rules_grid()

    def reset_rules(self):
        if messagebox.askyesno("Arrow Bot", "Вернуть стандартные правила? Твои изменения в таблице пропадут."):
            self.cfg["stand_rules"] = dict(DEFAULT_RULES)
            self._refresh_rules_grid()

    # ---------- Настройки ----------
    def _build_settings(self):
        t = self.tab_set
        self.sv = {
            "arrow_names": tk.StringVar(value=", ".join(self.cfg["arrow_names"])),
            "slot_arrow": tk.StringVar(value=self.cfg["slots"].get("arrow", "1")),
            "slot_fruit": tk.StringVar(value=self.cfg["slots"].get("fruit", "2")),
            "roll_timeout": tk.StringVar(value=str(self.cfg["roll_timeout"])),
            "dialog_wait": tk.StringVar(value=str(self.cfg["dialog_wait"])),
            "reconnect_min": tk.StringVar(value=str(self.cfg["reconnect_min"])),
            "overlay": tk.BooleanVar(value=self.cfg["overlay"]),
            "minimize": tk.BooleanVar(value=self.cfg.get("minimize", True)),
        }
        rows = (("Какие стрелы открывать по порядку (как в игре, через запятую): сначала первая, когда кончится, следующая", "arrow_names", 34),
                ("Стартовый слот стрелы (1-9, 0)", "slot_arrow", 6), ("Стартовый слот Rokakaka (1-9, 0)", "slot_fruit", 6),
                ("Макс. ожидание стенда после стрелы, сек", "roll_timeout", 6),
                ("Макс. ожидание предупреждения после Rokakaka, сек", "dialog_wait", 6),
                ("Ждать перезахода после Disconnected, минут", "reconnect_min", 6))
        for i, (cap, key, w) in enumerate(rows):
            ttk.Label(t, text=cap).grid(row=i, column=0, sticky="w", pady=6)
            ttk.Entry(t, textvariable=self.sv[key], width=w).grid(row=i, column=1, sticky="w", padx=14)
        ttk.Checkbutton(t, text="Показывать панель-оверлей поверх Roblox", variable=self.sv["overlay"]).grid(row=len(rows), column=0, sticky="w", pady=6)
        ttk.Checkbutton(t, text="Сворачивать это окно после старта", variable=self.sv["minimize"]).grid(row=len(rows) + 1, column=0, sticky="w", pady=6)
        ttk.Label(t, text="Слоты только стартовые: если предмета там нет, бот сам найдёт его по названию в другом слоте.",
                  style="Muted.TLabel").grid(row=len(rows) + 2, column=0, columnspan=2, sticky="w", pady=(10, 0))
        ttk.Button(t, text="Сохранить настройки", command=self.save_settings).grid(row=len(rows) + 3, column=0, sticky="w", pady=16)

    def save_settings(self):
        try:
            self.cfg["arrow_names"] = [x.strip() for x in self.sv["arrow_names"].get().split(",") if x.strip()] or ["Charged Arrow"]
            self.cfg["slots"] = {"arrow": self.sv["slot_arrow"].get().strip() or "1", "fruit": self.sv["slot_fruit"].get().strip() or "2"}
            self.cfg["roll_timeout"] = float(self.sv["roll_timeout"].get().replace(",", "."))
            self.cfg["dialog_wait"] = float(self.sv["dialog_wait"].get().replace(",", "."))
            self.cfg["reconnect_min"] = int(float(self.sv["reconnect_min"].get().replace(",", ".")))
        except ValueError:
            messagebox.showerror("Arrow Bot", "В числовых полях должны быть числа.")
            return
        self.cfg["overlay"] = bool(self.sv["overlay"].get())
        self.cfg["minimize"] = bool(self.sv["minimize"].get())
        self.commit_rules()
        save_cfg(self.cfg)
        messagebox.showinfo("Arrow Bot", "Настройки сохранены. Действуют со следующего запуска бота.")

    # ---------- Статистика ----------
    def _build_stats(self):
        t = self.tab_stats
        t.columnconfigure(0, weight=1); t.columnconfigure(1, weight=1); t.rowconfigure(2, weight=3); t.rowconfigure(3, weight=2)
        top = ttk.Frame(t)
        top.grid(row=0, column=0, columnspan=2, sticky="ew")
        self.lbl_sum = ttk.Label(top, text="", style="Muted.TLabel")
        self.lbl_sum.pack(side="left")
        ttk.Button(top, text="Очистить статистику", command=self.clear_stats).pack(side="right")
        cards = ttk.Frame(t)
        cards.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(8, 4))
        self.scards = {}
        keys = (("n", "всего бросков"), ("time", "время работы"), ("per", "секунд на бросок"), ("ph", "бросков в час"), ("kept", "найдено нужных"),
                ("pk", "шанс нужного за бросок"), ("exp", "ждать в среднем"), ("p1h", "шанс найти за час"),
                ("since", "бросков с последнего нужного"), ("rare", "самый редкий выпавший"))
        for i, (k, cap) in enumerate(keys):
            cards.columnconfigure(i % 5, weight=1)
            c = ttk.Frame(cards, style="Card.TFrame", padding=(10, 8))
            c.grid(row=i // 5, column=i % 5, sticky="ew", padx=(0 if i % 5 == 0 else 6, 0), pady=(0 if i < 5 else 6, 0))
            v = ttk.Label(c, text="–", font=disp(22), style="Card.TLabel")
            v.pack(anchor="w")
            ttk.Label(c, text=cap, style="Cap.TLabel").pack(anchor="w")
            self.scards[k] = v
        fst = tk.Frame(t, bg=CARD)
        fat = tk.Frame(t, bg=CARD)
        fst.grid(row=2, column=0, sticky="nsew", padx=(0, 6), pady=(6, 6))
        fat.grid(row=2, column=1, sticky="nsew", padx=(6, 0), pady=(6, 6))
        self.cv_st = self.scroll_canvas(fst, bg=CARD)
        self.cv_at = self.scroll_canvas(fat, bg=CARD)
        self.cv_ln = tk.Canvas(t, bg=CARD, highlightthickness=0)
        self.cv_ln.grid(row=3, column=0, columnspan=2, sticky="nsew")

    def line_chart(self, cv, title, vals, color):
        cv.delete("all")
        w, h = max(cv.winfo_width(), 400), max(cv.winfo_height(), 120)
        cv.create_text(12, 14, text=title, fill=MUTED, anchor="w", font=("Segoe UI", 10, "bold"))
        if len(vals) < 2:
            cv.create_text(12, 44, text="пока мало данных", fill=MUTED, anchor="w")
            return
        mx = max(vals) or 1
        x0, x1, y0, y1 = 40, w - 20, 34, h - 22
        for g in range(0, 5):
            y = y1 - (y1 - y0) * g / 4
            cv.create_line(x0, y, x1, y, fill="#2a3444")
            cv.create_text(x0 - 6, y, text=f"{mx * g / 4:.0f}", fill=MUTED, anchor="e", font=("Segoe UI", 8))
        pts = [(x0 + (x1 - x0) * i / (len(vals) - 1), y1 - (y1 - y0) * v / mx) for i, v in enumerate(vals)]
        cv.create_polygon([(x0, y1)] + pts + [(x1, y1)], fill=blend(CARD, color, 0.25), outline="")
        cv.create_line([c for p in pts for c in p], fill=color, width=2, smooth=True)
        for x, y in pts:
            cv.create_oval(x - 3, y - 3, x + 3, y + 3, fill=color, outline="")
        cv.create_text(x1, y1 + 12, text="сейчас", fill=MUTED, anchor="e", font=("Segoe UI", 8))
        cv.create_text(x0, y1 + 12, text=f"{len(vals) * 10} минут назад", fill=MUTED, anchor="w", font=("Segoe UI", 8))

    def bars(self, cv, title, items, color, limit=None, step=24, x0=210):
        """Горизонтальные столбики: все строки (limit=None), число и доля справа, список прокручивается."""
        cv.delete("all")
        w = max(cv.winfo_width(), 300)
        h = max(cv.winfo_height(), 60)
        cv.create_text(12, 14, text=title, fill=MUTED, anchor="w", font=("Segoe UI", 10, "bold"))
        if not items:
            cv.create_text(12, 44, text="пока пусто", fill=MUTED, anchor="w")
            cv.configure(scrollregion=(0, 0, w, h))
            return
        shown = items if limit is None else items[:limit]
        total = sum(c for _, c in items) or 1
        mx = max(c for _, c in items)
        for i, (name, c) in enumerate(shown):
            y = 38 + i * step
            cv.create_text(12, y, text=name[: max(10, (x0 - 20) // 6)], fill=FG, anchor="w", font=("Segoe UI", 9))
            x1 = w - 96
            cv.create_rectangle(x0, y - 8, x0 + max(2, (x1 - x0) * c / mx), y + 8, fill=color[name] if isinstance(color, dict) else color, width=0)
            cv.create_text(w - 10, y, text=f"{c}   {c * 100 / total:.0f}%", fill=FG, anchor="e", font=("Segoe UI", 9, "bold"))
        cv.configure(scrollregion=(0, 0, w, max(h, 38 + len(shown) * step + 10)))

    def refresh_stats(self):
        a = ab.analytics(read_stats())
        if not a["n"]:
            self.lbl_sum.configure(text="статистика появится после первого броска")
        else:
            self.lbl_sum.configure(text=f"доля хороших атрибутов среди выпавших: {a['good_attr'] * 100:.0f}%   ·   шансы это оценка по таблице шансов стендов и реальной частоте атрибутов")
        hms = lambda s: f"{int(s) // 3600}:{int(s) % 3600 // 60:02d}:{int(s) % 60:02d}"
        c = self.scards
        c["n"].configure(text=str(a["n"]))
        c["time"].configure(text=hms(a["active"]))
        c["per"].configure(text=f"{a['per']:.1f}" if a["per"] else "–")
        c["ph"].configure(text=f"{a['per_hour']:.0f}" if a["per_hour"] else "–")
        c["kept"].configure(text=str(a["kept"]), foreground=GREEN if a["kept"] else FG)
        c["pk"].configure(text=f"{a['p_keep'] * 100:.2f}%" if a["p_keep"] else "–")
        c["exp"].configure(text=(f"~{a['exp_rolls']:.0f} бросков" + (f" / {hms(a['exp_time'])}" if a["exp_time"] else "")) if a["exp_rolls"] else "–")
        c["p1h"].configure(text=f"{a['p_hour'] * 100:.0f}%" if a["p_hour"] is not None else "–")
        c["since"].configure(text=str(a["since_keep"]) if a["n"] else "–")
        c["rare"].configure(text=(a["rarest"][1][:22] + f" ({a['rarest'][0]}%)") if a["rarest"] else "–")
        sc, ac = self.rare_first_stands(a["stands"]), self.rare_first_attrs(a["attrs"])
        self.bars(self.cv_st, f"Все выпавшие стенды ({len(sc)}), редкие сверху", sc, BLUE, step=24, x0=210)
        self.bars(self.cv_at, f"Все выпавшие атрибуты ({len(ac)}), редкие сверху", ac, {n_: (GREEN if n_ not in BAD_ATTRS else "#64748b") for n_, _ in ac},
                  step=24, x0=210)
        self.line_chart(self.cv_ln, "Бросков за каждые 10 минут (активность по времени)", a["series"], "#a78bfa")

    def rare_first_stands(self, items):
        """Стенды от самых редких (по таблице шансов), с неизвестным шансом в конце; при равенстве чаще выпавшие выше."""
        return sorted(items, key=lambda it: (self.rarity_key(it[0])[:2], -it[1], it[0]))

    def rare_first_attrs(self, items):
        """Атрибуты от самых редко выпавших (шансов атрибутов в игре мы не знаем, берём реальную частоту)."""
        return sorted(items, key=lambda it: (it[1], it[0]))

    def refresh_live_stats(self):
        """Статистика на главной: пока бот работает - только за этот запуск, иначе за всё время. Обновляется во время броска."""
        from collections import Counter
        rows = read_stats()
        scope = "за этот запуск"
        if self.proc and self.session_from:
            rows = [r for r in rows if r.get("t", 0) >= self.session_from]
        else:
            scope = "за всё время"
        kept = sum(1 for r in rows if r.get("verdict") == "keep")
        self.lbl_live.configure(text=f"Статистика {scope}: бросков {len(rows)}, нужных {kept}")
        sc = self.rare_first_stands(Counter(r.get("stand") or "?" for r in rows).most_common())
        ac = self.rare_first_attrs(Counter(str(r.get("attr")) for r in rows).most_common())
        self.bars(self.cv_live_st, f"Стенды: все выпавшие ({len(sc)}), редкие сверху", sc, BLUE, step=20, x0=150)
        self.bars(self.cv_live_at, f"Атрибуты: все выпавшие ({len(ac)}), редкие сверху", ac, {a: (GREEN if a not in BAD_ATTRS else "#64748b") for a, _ in ac},
                  step=20, x0=150)

    def clear_stats(self):
        if messagebox.askyesno("Arrow Bot", "Удалить всю статистику?"):
            for f in (ab.STATS_FILE, ab.STATE_FILE, IMPORT_FILE):
                try:
                    os.remove(f)
                except OSError:
                    pass
            self.refresh_stats()

    # ---------- Справка ----------
    # ---------- История ----------
    def _build_history(self):
        t = self.tab_hist
        t.columnconfigure(0, weight=1); t.rowconfigure(1, weight=1)
        top = ttk.Frame(t)
        top.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        self.hist_only = tk.BooleanVar(value=False)
        ttk.Checkbutton(top, text="Только нужные (оставить)", variable=self.hist_only,
                        command=lambda: self.refresh_history(force=True)).pack(side="left")
        self.lbl_hist = ttk.Label(top, text="", style="Muted.TLabel")
        self.lbl_hist.pack(side="left", padx=16)
        ttk.Button(top, text="Сохранить в CSV", command=self.export_history).pack(side="right")
        wrap = tk.Frame(t, bg=BG, highlightthickness=3, highlightbackground=OUTLINE)
        wrap.grid(row=1, column=0, sticky="nsew")
        wrap.rowconfigure(0, weight=1); wrap.columnconfigure(0, weight=1)
        cols = ("n", "time", "stand", "attr", "verdict", "src")
        self.tree = ttk.Treeview(wrap, columns=cols, show="headings", selectmode="browse")
        for c, name, w, anchor in (("n", "№", 70, "e"), ("time", "Время", 170, "w"), ("stand", "Стенд", 360, "w"),
                                   ("attr", "Атрибут", 190, "w"), ("verdict", "Решение", 150, "w"), ("src", "Откуда", 120, "w")):
            self.tree.heading(c, text=name, anchor=anchor)
            self.tree.column(c, width=w, anchor=anchor, stretch=(c == "stand"))
        sb = ttk.Scrollbar(wrap, command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.grid(row=0, column=0, sticky="nsew"); sb.grid(row=0, column=1, sticky="ns")
        self.tree.tag_configure("keep", background=GREEN, foreground=INK, font=("Segoe UI", 10, "bold"))
        self.tree.tag_configure("delete", foreground=MUTED)
        self.tree.tag_configure("unsure", background=YELLOW, foreground=INK)
        self._hist_sig = None

    HIST_VERDICT = {"keep": "ОСТАВИТЬ", "delete": "снесён", "unsure": "не уверен"}

    def refresh_history(self, force=False):
        """Журнал каждого броска (новые сверху). Перерисовываем только когда появились новые строки."""
        rows = read_stats()
        only = self.hist_only.get()
        sig = (len(rows), only)
        if not force and sig == self._hist_sig:
            return
        self._hist_sig = sig
        numbered = list(enumerate(rows, 1))
        if only:
            numbered = [(i, r) for i, r in numbered if r.get("verdict") == "keep"]
        self.tree.delete(*self.tree.get_children())
        for i, r in reversed(numbered[-1500:]):
            v = r.get("verdict")
            self.tree.insert("", "end", values=(i, time.strftime("%d.%m  %H:%M:%S", time.localtime(r.get("t", 0))), r.get("stand") or "?",
                                                 r.get("attr"), self.HIST_VERDICT.get(v, v),
                                                 {"import": "из архива", "fima": "другой ПК"}.get(r.get("src"), "этот ПК")), tags=(v or "",))
        shown = min(len(numbered), 1500)
        self.lbl_hist.configure(text=f"показано {shown} из {len(numbered)}" + (" (нужные)" if only else "") + f", всего бросков {len(rows)}")

    def export_history(self):
        from tkinter import filedialog
        import csv
        rows = read_stats()
        if not rows:
            messagebox.showinfo("Arrow Bot", "История пока пустая.")
            return
        path = filedialog.asksaveasfilename(title="Сохранить историю", defaultextension=".csv", initialfile="arrow_bot_history.csv",
                                            filetypes=[("CSV (Excel)", "*.csv")])
        if not path:
            return
        with open(path, "w", encoding="utf-8-sig", newline="") as f:
            w = csv.writer(f, delimiter=";")
            w.writerow(["№", "время", "стенд", "атрибут", "решение"])
            for i, r in enumerate(rows, 1):
                w.writerow([i, time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(r.get("t", 0))), r.get("stand"), r.get("attr"),
                            self.HIST_VERDICT.get(r.get("verdict"), r.get("verdict"))])
        messagebox.showinfo("Arrow Bot", f"Сохранено {len(rows)} строк:\n{path}")

    def _build_help(self):
        txt = ("Как пользоваться\n\n"
               "1. Открой Roblox, зайди в Stand Upright: Rebooted. Charged Arrow и Rokakaka должны лежать в хотбаре (слот любой).\n"
               "2. Нажми СТАРТ. Окно свернётся, поверх игры появится панель статуса.\n"
               "3. Бот крутит стрелу, читает стенд и атрибут, нужное оставляет (пикнет и остановится), ненужное сносит Rokakaka.\n"
               "4. Остановить: кнопка СТОП в этом окне или клавиша F7. Пауза: F6. Мышь в левый верхний угол экрана: аварийный стоп.\n\n"
               "Какие стенды оставлять: вкладка «Стенды и атрибуты». Сохрани, правила применятся со следующего запуска.\n"
               "Каждый бросок записывается: вкладка «История» показывает их списком (новые сверху, нужные подсвечены), можно сохранить в CSV для Excel.\n\n"
               "Если вылетело Disconnected: бот пикнет и подождёт, пока ты перезайдёшь сам, дальше закроет Changelogs, нажмёт Play и продолжит.\n"
               "Когда стрелы или Rokakaka кончатся, бот пикнет и остановится.\n\n"
               "Важно: Roblox и это окно запускай с одинаковыми правами (оба обычные), не блокируй ПК (Win+L), "
               "не сворачивай Roblox, не выключай экран (яркость на минимум можно).\n\n"
               "Файлы рядом: arrow_bot_log.txt (журнал), arrow_bot_last.png (что бот видел при остановке), "
               "arrow_settings.json (твои правила и настройки), arrow_bot_stats.jsonl (статистика).\n\n"
               "Автокликеры формально против правил Roblox. Бан возможен, всё на твой риск.")
        lab = ttk.Label(self.tab_help, text=txt, wraplength=1050, justify="left", font=("Segoe UI", 11))
        lab.pack(anchor="nw")

    # ---------- цикл обновления ----------
    def tick(self):
        try:
            while True:
                item = self.q.get_nowait()
                if isinstance(item, tuple) and item and item[0] == "__done__":
                    _, rc, after = item
                    if self.proc is not None and self.proc.poll() is not None:
                        self.on_proc_done(rc)
                    if after:
                        after(rc)
                else:
                    self.add_log(item)
        except queue.Empty:
            pass
        if self.proc and self.stop_asked and time.time() - self.stop_asked > 12 and self.proc.poll() is None:
            self.proc.terminate()
        self.update_live()
        self._n = getattr(self, "_n", 0) + 1
        if self._n % 60 == 0:
            self.autosave()
        if self.nb.index(self.nb.select()) == 3 and self._n % 4 == 0:
            self.refresh_stats()
        if self.nb.index(self.nb.select()) == 0 and self._n % 4 == 0:
            self.refresh_live_stats()
            self.refresh_pentagon()
        if self.nb.index(self.nb.select()) == 4 and self._n % 4 == 0:
            self.refresh_history()
        self.root.after(500, self.tick)

    def autosave(self):
        """Правки таблицы и настроек сохраняются сами раз в 30 секунд (раньше только по кнопке или при закрытии)."""
        try:
            self.commit_rules()
            sig = json.dumps(self.cfg, sort_keys=True, ensure_ascii=False, default=list)
            if self._saved_sig is None:
                self._saved_sig = sig                # первый круг: запоминаем исходное состояние
            elif sig != self._saved_sig:
                save_cfg(self.cfg)
                self._saved_sig = sig
        except Exception:
            pass

    def update_live(self):
        try:
            with open(ab.STATE_FILE, encoding="utf-8") as f:
                st = json.load(f)
        except Exception:
            return
        if not self.t_start or st.get("updated", 0) < self.session_from:
            return
        n = st.get("n", 0)
        el = max(0.0, (time.time() if self.proc else st.get("updated", time.time())) - self.t_start)
        self.vals["n"].configure(text=str(n))
        self.vals["rate"].configure(text=f"{el / n:.0f}" if n else "–")
        self.vals["time"].configure(text=f"{int(el) // 3600}:{int(el) % 3600 // 60:02d}:{int(el) % 60:02d}")
        self.vals["arrows"].configure(text=str(st.get("arrows") if st.get("arrows") is not None else "–"))
        self.vals["fruits"].configure(text=str(st.get("fruits") if st.get("fruits") is not None else "–"))
        v = st.get("verdict")
        self.lbl_last.configure(text=str(st.get("stand") or "–"))
        self.lbl_attr.configure(text=str(st.get("attr") or ""))
        if v == "keep":
            self.lbl_verdict.configure(text="ОСТАВИТЬ!!", fg=GREEN, bg=OUTLINE)
        elif v == "unsure":
            self.lbl_verdict.configure(text="не уверен", fg=INK, bg=YELLOW)
        else:
            self.lbl_verdict.configure(text="снести", fg=VIOLET_DEEP, bg=PAPER)
        kept = sum(1 for r in read_stats() if r.get("t", 0) >= self.session_from and r.get("verdict") == "keep")
        self.vals["kept"].configure(text=str(kept))
        known = ab.match_stand(str(st.get("stand") or ""))
        chance = ab.STANDS.get(known)
        if known in ab.STAND_RULES:
            keep_attrs = ", ".join(a for a in ab.ALL_ATTRS if a in ab.STAND_RULES[known])
            self.lbl_hint.configure(text=(f"шанс стенда {chance}%\n" if chance else "") + f"оставляем при: {keep_attrs}")
        elif known:
            self.lbl_hint.configure(text=f"шанс стенда {chance}%\nв твоём списке его нет, снесём при любом атрибуте")
        else:
            self.lbl_hint.configure(text="")

    def on_close(self):
        if self.proc:
            if not messagebox.askyesno("Arrow Bot", "Бот ещё работает. Остановить и закрыть окно?"):
                return
            try:
                open(ab.STOP_FILE, "w").close()
                self.proc.wait(timeout=6)
            except Exception:
                try:
                    self.proc.terminate()
                except Exception:
                    pass
        try:
            self.commit_rules(); save_cfg(self.cfg)
        except Exception:
            pass
        self.root.destroy()


def main():
    root = tk.Tk()
    app = App(root)
    if "--autostart" in sys.argv:          # перезапуск после обновления: сразу запустить бота без вопросов
        root.after(2500, lambda: app.start(confirm=False))
    root.mainloop()


if __name__ == "__main__":
    main()
