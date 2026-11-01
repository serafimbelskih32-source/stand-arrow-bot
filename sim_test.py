import os
os.environ["ARROWBOT_TEST"] = "1"
"""Симулятор Stand Upright: Rebooted для проверки логики arrow_bot.Bot (OCR-строки идут через настоящий parse_items)."""
import sys, random
sys.path.insert(0, ".")
import arrow_bot as ab

W, H = 1920, 1080
YES = (ab.YES_FRAC[0] * W, ab.YES_FRAC[1] * H)
NO = (ab.NO_FRAC[0] * W, ab.NO_FRAC[1] * H)


def flat(s):                      # OCR часто теряет пробелы
    return s.replace(" ", "")


class Sim:
    def __init__(self, rolls, seed=0, hotbar=None, events=None, start_stand=None, start_menu=False,
                 warn_all_rare=True, misread_every=0, fruit_count=10367, arrow_count=6682, panel=True):
        self.rnd = random.Random(seed)
        self.t = 0.0
        self.rolls = list(rolls)
        self.hotbar = hotbar or {"1": "Charged Arrow", "2": "Rokakaka"}
        self.counts = {"Charged Arrow": arrow_count, "Stand Arrow": 3000}
        self.equipped = None
        self.stand = start_stand            # (name, attr) | None
        self.menu = start_menu
        self.rolling_until = None
        self.pending = None
        self.dialog_t0 = None
        self.dialog_for = None
        self.events = sorted(events or [])  # [(t, 'death'|'menu')]
        self.log = []
        self.yes_clicks = 0
        self.no_clicks = 0
        self.deleted = []
        self.arrow_count = arrow_count
        self.fruit_count = fruit_count
        self.misread_every = misread_every
        self.reads = 0
        self.menu_load_until = None
        self.beeped = False
        self.warn_all_rare = warn_all_rare
        self.panel = panel

    # ---------- API окружения ----------
    def now(self): return self.t
    def region(self): return [0, 0, W, H]
    def focus(self): pass
    def beep(self): self.beeped = True

    def sleep(self, s):
        self.t += s; self._tick()

    def _tick(self):
        while self.events and self.events[0][0] <= self.t:
            _, ev = self.events.pop(0)
            if ev == "death":
                keys = list(self.hotbar.values()); self.rnd.shuffle(keys)
                self.hotbar = {str(i + 1): n for i, n in enumerate(keys)}
                self.equipped = None
                self.log.append(f"{self.t:.0f}: DEATH, hotbar={self.hotbar}")
            elif ev == "menu":
                self.menu = True; self.equipped = None
                self.log.append(f"{self.t:.0f}: KICKED TO MENU")
        if self.rolling_until and self.t >= self.rolling_until:
            self.stand = self.pending; self.rolling_until = None
        if self.menu_load_until and self.t >= self.menu_load_until:
            self.menu = False; self.menu_load_until = None; self.panel = False   # после захода панель закрыта
            keys = list(self.hotbar.values()); self.rnd.shuffle(keys)
            self.hotbar = {str(i + 1): n for i, n in enumerate(keys)}

    def key(self, k):
        self.t += 0.05; self._tick()
        if k == "m" and not self.menu:
            self.panel = not self.panel; return
        if self.menu or k not in self.hotbar:
            return
        item = self.hotbar[k]
        self.equipped = None if self.equipped == item else item

    def click(self, x, y, hard=False):
        self.t += 0.3; self._tick()
        if self.menu:
            if abs(x - 0.497 * W) < 150 and abs(y - 0.577 * H) < 30:
                self.menu_load_until = self.t + 8
            return
        if self.dialog_t0 is not None:
            if self.t - self.dialog_t0 >= 2 and abs(x - YES[0]) < 80 and abs(y - YES[1]) < 25:
                self.yes_clicks += 1
                self.deleted.append(self.stand); self.stand = None; self.dialog_t0 = None
                self.fruit_count -= 1
            elif self.t - self.dialog_t0 >= 2 and abs(x - NO[0]) < 80 and abs(y - NO[1]) < 25:
                self.no_clicks += 1; self.dialog_t0 = None
            return
        if self.equipped in ("Charged Arrow", "Stand Arrow") and not self.stand and not self.rolling_until:
            if self.counts[self.equipped] <= 0:
                return
            self.counts[self.equipped] -= 1
            self.pending = self.rolls.pop(0)
            self.rolling_until = self.t + 3.0
        elif self.equipped == "Rokakaka" and self.stand:
            name, attr = self.stand
            rare = ab.STANDS.get(ab.match_stand(name) or "", 99) <= 0.5
            if (rare or attr in ab.GOOD_ATTRS) and self.warn_all_rare:
                self.dialog_t0 = self.t
            else:
                self.deleted.append(self.stand); self.stand = None; self.fruit_count -= 1

    def click_center(self): self.click(W / 2, H / 2)
    def click_frac(self, f): self.click(f[0] * W, f[1] * H)

    def read(self):
        self.t += 1.0; self._tick(); self.reads += 1
        items = self._items()
        return ab.parse_items(items, (W, H))

    # ---------- «OCR» ----------
    def _items(self):
        it = []
        def add(text, x, y): it.append({"text": text, "x": x, "y": y})
        if self.menu:
            add("Stand Upright: Rebooted", 960, 180)
            add("Play", 0.425 * W, 0.575 * H); add("Help", 0.43 * W, 0.64 * H); add("Gamemodes", 0.45 * W, 0.71 * H)
            return it
        add("Level: 442", 1300, 100); add("729380/1758296", 760, 110)
        shown = self.stand if not self.rolling_until else None
        if not self.panel:
            shown = None
        if not self.panel:
            pass
        elif shown:
            name, attr = shown
            if self.misread_every and self.reads % self.misread_every == 0:
                attr = attr[:-1] + "x"       # единичная ошибка OCR
            add(flat("Stand: " + name), 170, 350)
            add(("Attribute: " if self.reads % 3 else "Attribute") + attr if attr != "None" else "Attribute:None", 124, 388)
        else:
            add("Stand:", 78, 352); add("Attribute:None", 122, 387)
        add("Standard Attack Damage", 360, 430); add("Stand Health", 302, 471); add("Stand Tier", 289, 553)
        if self.equipped:
            cnt = self.counts.get(self.equipped, self.fruit_count)
            label = f"{self.equipped}: {cnt} / 20000"
            add(flat(label) if self.reads % 2 else label.replace(":", "i"), 990, 940)
        if self.dialog_t0 is not None:
            dt = self.t - self.dialog_t0
            add("You have a Star Plat, are you sure?!?", 989, 588)
            add("Rokakaka [Lvl 1+]", 990, 627)
            add("Using this item will remove your Stand" if dt < 1 else "Using this item will remove your Stand and", 991, 696)
            if dt >= 1:
                add("Attribute, including rare sub-1% rolls, continue?", 990, 738)
            if dt >= 2:
                add("Yes", YES[0], YES[1]); add("No", NO[0], NO[1])
        return it


def run(label, sim, expect_keep=None, expect_stop=None, assume_yes=True):
    bot = ab.Bot(sim, assume_yes=assume_yes)
    result = None
    try:
        result = bot.run()
    except ab.Stop as e:
        result = f"STOP: {e}"
    ok = True
    if expect_keep is not None:
        ok = (result == "keep") and sim.stand == expect_keep
    if expect_stop is not None:
        ok = ok and isinstance(result, str) and expect_stop in result
    # критическое правило: ни один нужный стенд не должен быть удалён
    for d in sim.deleted:
        if d and ab.classify(*d) == "keep":
            ok = False; print("   !!! удалён нужный стенд", d)
    print(("PASS " if ok else "FAIL ") + label, "->", result, f"| t={sim.t:.0f}s deleted={len(sim.deleted)} yes={sim.yes_clicks} no={sim.no_clicks}")
    for l in sim.log: print("     ", l)
    return ok


def main():
    BAD = [("Star Platinum", "None"), ("The World", "Tough"), ("Silver Chariot", "Enrage"), ("Crazy Diamond", "Strong"),
           ("Killer Queen", "Godly"), ("Whitesnake", "Manic"), ("Hierophant Green", "Tough"), ("DIO's The World", "Sloppy"),
           ("Tusk Act 1", "Daemon"), ("Star Platinum", "Strong"), ("King Crimson", "Lethargic"), ("Hierophant Green", "None")]
    GOOD = ("DIO's The World", "Hacker")

    results = []
    results.append(run("базовый цикл, слоты 1/2", Sim(BAD + [GOOD]), expect_keep=GOOD))
    results.append(run("слоты перемешаны (стрела в 7, фрукт в 3)", Sim(BAD + [GOOD], hotbar={"1": "Tool A", "3": "Rokakaka", "7": "Charged Arrow"}), expect_keep=GOOD))
    results.append(run("смерть посреди работы (слоты перемешались)", Sim(BAD + [GOOD], events=[(60, "death"), (150, "death")]), expect_keep=GOOD))
    results.append(run("выкинуло в меню -> Play", Sim(BAD + [GOOD], events=[(70, "menu")]), expect_keep=GOOD))
    results.append(run("старт из меню", Sim(BAD + [GOOD], start_menu=True), expect_keep=GOOD))
    results.append(run("старт с чужим плохим стендом (--yes)", Sim(BAD + [GOOD], start_stand=("Star Platinum", "Tough")), expect_keep=GOOD))
    results.append(run("старт с нужным стендом -> сразу keep, фрукт не трогает", Sim([], start_stand=("Sol Spirit", "Legendary")), expect_keep=("Sol Spirit", "Legendary")))
    results.append(run("Whitesnake + Legendary оставляет", Sim([("Whitesnake", "Tough"), ("Whitesnake", "Legendary")]), expect_keep=("Whitesnake", "Legendary")))
    results.append(run("Legendary на стенде не из списка сносит, дальше нужный keep", Sim([("Silver Chariot", "Legendary"), ("Sol Spirit", "Hacker")]), expect_keep=("Sol Spirit", "Hacker")))
    results.append(run("The World + Hacker сносит, дальше находит", Sim([("The World", "Hacker"), ("Shadow The Universe", "Scourge")]), expect_keep=("Shadow The Universe", "Scourge")))
    results.append(run("единичные ошибки OCR (каждое 7-е чтение)", Sim(BAD + [GOOD], misread_every=7), expect_keep=GOOD))
    results.append(run("Charged Arrow нет в хотбаре, есть Stand Arrow", Sim(BAD + [GOOD], hotbar={"1": "Tool A", "2": "Rokakaka", "3": "Stand Arrow"}), expect_keep=GOOD))
    results.append(run("Charged кончились (3 штуки), дальше Stand Arrow", Sim(BAD + [GOOD], arrow_count=3, hotbar={"1": "Charged Arrow", "2": "Rokakaka", "3": "Stand Arrow"}), expect_keep=GOOD))
    results.append(run("нет предмета в хотбаре", Sim(BAD, hotbar={"1": "Tool A", "2": "Rokakaka"}), expect_stop="стрелы закончились"))
    results.append(run("кончились стрелы", Sim(BAD * 3, arrow_count=3), expect_stop="стрелы закончились"))
    results.append(run("панель скрыта на старте (открыть на M)", Sim(BAD + [GOOD], panel=False), expect_keep=GOOD))
    results.append(run("меню + панель закрывается после захода", Sim(BAD + [GOOD], events=[(40, "menu"), (120, "menu")]), expect_keep=GOOD))
    results.append(run("без предупреждения (игра не спрашивает)", Sim(BAD + [GOOD], warn_all_rare=False), expect_keep=GOOD))
    print("\nИТОГО:", sum(results), "/", len(results))
    sys.exit(0 if all(results) else 1)


if __name__ == "__main__":
    main()
