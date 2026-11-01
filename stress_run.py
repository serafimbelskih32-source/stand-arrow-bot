import os
os.environ["ARROWBOT_TEST"] = "1"
import sys, io, contextlib, random, os
sys.path.insert(0, ".")
import sim_test as st
ab, Sim = st.ab, st.Sim
ab.LOG_FILE = os.devnull
names = list(ab.STANDS)
attrs_bad = ["None","Strong","Tough","Sloppy","Powerful","Enrage","Manic","Lethargic","Godly"]
attrs_good = sorted(ab.GOOD_ATTRS)
N = int(sys.argv[1]) if len(sys.argv) > 1 else 200
fails = wrong_delete = 0; reasons = {}
for seed in range(N):
    r = random.Random(seed)
    rolls = [(r.choice(names), r.choice(attrs_bad + attrs_good if r.random() < .25 else attrs_bad)) for _ in range(r.randint(3, 25))]
    _st = r.choice(sorted(ab.STAND_RULES)); rolls.append((_st, r.choice(sorted(ab.STAND_RULES[_st]))))
    tools = ["Tool A", "Tool B", "Tool C", "Charged Arrow", "Rokakaka", "Tool D"]; r.shuffle(tools)
    hotbar = {str(i+1): t for i, t in enumerate(tools)}
    events = [(r.randint(20, 300), r.choice(["death", "menu"])) for _ in range(r.randint(0, 4))]
    sim = Sim(rolls, seed=seed, hotbar=hotbar, events=events, start_menu=r.random() < .2,
              misread_every=r.choice([0, 0, 5, 9, 13]), panel=r.random() < .5, warn_all_rare=r.random() < .8)
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            res = ab.Bot(sim, assume_yes=True).run()
    except ab.Stop as e:
        res = "STOP: " + str(e)
    except Exception as e:
        res = "EXC: " + repr(e)
    bad_del = [d for d in sim.deleted if d and ab.classify(*d) == "keep"]
    final_ok = res == "keep" and sim.stand is not None and ab.classify(*sim.stand) == "keep"
    if bad_del: wrong_delete += 1
    if not (final_ok and not bad_del):
        fails += 1; reasons[res[:80]] = reasons.get(res[:80], 0) + 1
        if fails <= 4: print("FAIL seed", seed, res[:100], "| events", events)
print(f"прогонов: {N}, успешно: {N-fails}, не дошло: {fails}, удалён нужный стенд: {wrong_delete}")
print(reasons)
