#!/usr/bin/env python3
"""First English regression harness -- v33 (sight-word speaker cue, sightSet persistence).

S1  Home sight grid: every button whose word has NO emoji carries a small
    .spkcue speaker icon; every button WITH emoji carries NO .spkcue.
S2  Tapping an abstract-word button calls say() with that word (test hook _sayLast).
S3  sightSet persists across reload (pill stays on, grid stays filtered).
S4  Invalid stored sightSet (99, "abc") falls back to All with a full grid.
S5  Reset clears fe_sightset and returns the pill row to All.
S6  Sight-quiz option buttons carry NO .spkcue (tapping answers, not speaks).
S7  Touch targets >=44px on sight pills + word buttons at 390x844; no
    horizontal overflow at 390x844 and 844x390 landscape.
S8  Zero page/runtime/JS errors across the whole run.

Usage: python3 qa/qa_v33.py   (chrome on :9333)
Screenshots -> qa/shots/.
"""
import json, sys, time, base64, urllib.request
import websocket

SRCD = "/home/hatch/workspace/english-app"
HTML = SRCD + "/index.html"
SHOTD = SRCD + "/qa/shots"
PORT = 9333

for _ in range(30):
    try:
        targets = json.load(urllib.request.urlopen(f"http://localhost:{PORT}/json/list", timeout=2))
        pages = [t for t in targets if t.get("type") == "page"]
        if pages:
            ws_url = pages[0]["webSocketDebuggerUrl"]; break
    except Exception:
        pass
    time.sleep(0.5)
else:
    sys.exit(f"no chrome on :{PORT}")

ws = websocket.create_connection(ws_url, timeout=90)
mid = [0]
def send(method, params=None):
    mid[0] += 1
    ws.send(json.dumps({"id": mid[0], "method": method, "params": params or {}}))
    while True:
        msg = json.loads(ws.recv())
        if msg.get("id") == mid[0]:
            return msg.get("result", {})

errors, fails = [], []
def js(expr):
    r = send("Runtime.evaluate", {"expression": expr, "awaitPromise": True, "returnByValue": True})
    if r.get("exceptionDetails"):
        errors.append("JS EX: " + str(r["exceptionDetails"].get("text", ""))[:160])
        return None
    return r.get("result", {}).get("value")
def check(name, cond, detail=""):
    print(("PASS " if cond else "FAIL ") + name + ((" -- " + str(detail)) if detail and not cond else ""), flush=True)
    if not cond: fails.append(name)
def shot(name):
    res = send("Page.captureScreenshot", {"format": "png", "captureBeyondViewport": False})
    open(f"{SHOTD}/v33_{name}.png", "wb").write(base64.b64decode(res["data"]))
def drain():
    ws.settimeout(0.2)
    try:
        while True:
            msg = json.loads(ws.recv())
            if msg.get("method") == "Runtime.exceptionThrown":
                errors.append("PAGE EX: " + str(msg["params"]["exceptionDetails"].get("text", ""))[:160])
    except Exception:
        pass
    ws.settimeout(90)
def click(sel):
    js(f'document.querySelector({sel!r}).click()')
def set_viewport(w, h, mobile=True):
    send("Emulation.setDeviceMetricsOverride",
         {"width": w, "height": h, "deviceScaleFactor": 1, "mobile": mobile})

send("Page.enable"); send("Runtime.enable")

def boot(w=390, h=844, clear=True):
    set_viewport(w, h)
    if clear: js("localStorage.clear()")
    send("Page.navigate", {"url": "file://" + HTML})
    time.sleep(2.5); drain()

def sight_btns():
    return js("""Array.from(document.querySelectorAll('#sightgrid .sw')).map(b=>({
        w: b.querySelector('.sww').textContent,
        hasEmoji: !!SIGHT_WORDS.find(s=>s.w===b.querySelector('.sww').textContent).e,
        cue: !!b.querySelector('.spkcue')}))""")

# ---------- S1: speaker icon only on emoji-less words ----------
boot()
bts = sight_btns()
check("S1 buttons rendered", bts is not None and len(bts) == js("SIGHT_WORDS.length"), len(bts) if bts else None)
if bts:
    cue_ok = all((not b["hasEmoji"] and b["cue"]) or (b["hasEmoji"] and not b["cue"]) for b in bts)
    check("S1 .spkcue iff no emoji", cue_ok,
          [b["w"] for b in bts if (not b["hasEmoji"] and not b["cue"]) or (b["hasEmoji"] and b["cue"])][:6])
    n_abstract = sum(1 for b in bts if b["cue"])
    check("S1 abstract words get the icon (n>0)", n_abstract > 0, n_abstract)

# ---------- S2: tap-to-hear on an abstract word ----------
click('#sightgrid .sw[data-say="said"]')
time.sleep(0.6); drain()
check("S2 tapping 'said' speaks it", js("_sayLast.t") == "said", js("_sayLast.t"))

# ---------- S3: sightSet persists across reload ----------
click('.setpill[data-set="2"]'); time.sleep(0.6); drain()
check("S3 pill Set 2 on after click", js("document.querySelector('.setpill[data-set=\"2\"]').classList.contains('on')"))
check("S3 grid filtered to set 2", js("Array.from(document.querySelectorAll('#sightgrid .sw .sww')).every(el=>SIGHT_WORDS.find(s=>s.w===el.textContent).set===2)"))
check("S3 fe_sightset stored", js("localStorage.getItem('fe_sightset')") == "2")
send("Page.reload"); time.sleep(2.5); drain()
check("S3 pill Set 2 on after reload", js("document.querySelector('.setpill[data-set=\"2\"]').classList.contains('on')"))
check("S3 grid still filtered after reload",
      js("Array.from(document.querySelectorAll('#sightgrid .sw .sww')).length") == js("SIGHT_WORDS.filter(s=>s.set===2).length"))

# ---------- S4: invalid stored value falls back to All ----------
js("localStorage.setItem('fe_sightset','99')")
send("Page.reload"); time.sleep(2.5); drain()
check("S4 bogus 99 -> All pill on", js("document.querySelector('.setpill[data-set=\"0\"]').classList.contains('on')"))
check("S4 bogus 99 -> full grid", js("document.querySelectorAll('#sightgrid .sw').length") == js("SIGHT_WORDS.length"))
js("localStorage.setItem('fe_sightset','abc')")
send("Page.reload"); time.sleep(2.5); drain()
check("S4 'abc' -> All pill on", js("document.querySelector('.setpill[data-set=\"0\"]').classList.contains('on')"))

# ---------- S5: reset clears sightSet ----------
click('.setpill[data-set="3"]'); time.sleep(0.6); drain()
check("S5 setup: pill 3 on", js("document.querySelector('.setpill[data-set=\"3\"]').classList.contains('on')"))
js("resetAllProgress()"); time.sleep(0.8); drain()
check("S5 fe_sightset removed", js("localStorage.getItem('fe_sightset')") is None)
check("S5 pill back to All", js("document.querySelector('.setpill[data-set=\"0\"]').classList.contains('on')"))

# ---------- S6: quiz options carry no .spkcue ----------
boot()
js("startQuiz({bank:SIGHT_WORDS.filter(s=>s.set===1),kind:'sight'})"); time.sleep(0.8); drain()
check("S6 quiz options have no .spkcue", js("document.querySelectorAll('#qzOpts .spkcue').length") == 0)

# ---------- S7: touch targets + overflow ----------
boot()
click('.setpill[data-set="1"]'); time.sleep(0.6)
under = js("""Array.from(document.querySelectorAll('#sightgrid .sw, #setpills .setpill')).map(b=>{const r=b.getBoundingClientRect();return [b.textContent.slice(0,12),Math.round(r.height)]}).filter(x=>x[1]<44)""")
check("S7 all sight buttons/pills >=44px", under == [], under)
check("S7 no horizontal overflow 390x844", js("document.documentElement.scrollWidth") <= 390)
shot("sight_home_390")
set_viewport(844, 390); time.sleep(0.8); drain()
check("S7 no horizontal overflow 844x390", js("document.documentElement.scrollWidth") <= 844)
shot("sight_home_land")

# ---------- S8: zero errors ----------
drain()
check("S8 zero page/runtime/JS errors", not errors, errors[:3])

print(f"\n{len(fails)} FAILURES, {len(errors)} ERRORS")
sys.exit(1 if fails or errors else 0)
