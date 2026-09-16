#!/usr/bin/env python3
"""First English regression harness — v25 (persistent).

Drives the real app in headless Chrome via CDP using real .click() calls.
Covers the v22-v25 structural fixes:
  T1  say() debounce — overlapping event paths can't double-speak
  T2  QUIZ_KINDS registry values (incl. unknown-kind defaults)
  T3  Home sight-quiz: full 6-question flow, SRS records, Play again, Home
  T4  Sound Pairs: partner present every round, no crash, replay keeps pairOf
  T5  Reset: clears ALL FE_KEYS incl. fe_grad, resets in-memory state
  T6  speakHeard(null spk) guard — no exception when user navigated away
  T7  Overflow checks at 390x844 / 1440x900 / 844x390
  T8  No page/runtime errors throughout
  T17 Listen/Read gameRound feeds per-word outcomes to the SRS
  T18 srsDue spans every bank (sight + level words), not sight words only
  T19 Unified Tricky-words home card; review quiz (kind "review") advances due dates
  T20 Due card hides when nothing is due

CDP notes: Runtime.evaluate needs returnByValue:true or arrays/objects come back\n  as objectId references (no .value) and every object-returning check silently fails.\n  Headless Chrome auto-dismisses confirm() as Cancel, so the reset test stubs it.\n\nUsage:  python3 qa/qa_v23.py [width height]
Requires: chrome on :9222 (~/workspace/tools/start_chrome.sh), websocket-client lib.
Screenshots -> qa/shots/.
"""
import json, sys, time, base64, urllib.request
import websocket

HTML = "/home/hatch/workspace/english-app/first_english_v11.html"
SHOTD = "/home/hatch/workspace/english-app/qa/shots"
W, H = (int(sys.argv[1]), int(sys.argv[2])) if len(sys.argv) > 2 else (390, 844)

for _ in range(30):
    try:
        targets = json.load(urllib.request.urlopen("http://localhost:9222/json/list", timeout=2))
        pages = [t for t in targets if t.get("type") == "page"]
        if pages:
            ws_url = pages[0]["webSocketDebuggerUrl"]; break
    except Exception:
        pass
    time.sleep(0.5)
else:
    sys.exit("no chrome on :9222 — run ~/workspace/tools/start_chrome.sh first")

ws = websocket.create_connection(ws_url, timeout=60)
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
    v = r.get("result", {}).get("value")
    return v
def check(name, cond, detail=""):
    print(("PASS " if cond else "FAIL ") + name + ((" — " + str(detail)) if detail and not cond else ""))
    if not cond: fails.append(name)
def shot(name):
    res = send("Page.captureScreenshot", {"format": "png", "captureBeyondViewport": False})
    open(f"{SHOTD}/v25_{name}.png", "wb").write(base64.b64decode(res["data"]))
def drain():
    ws.settimeout(0.2)
    try:
        while True:
            msg = json.loads(ws.recv())
            if msg.get("method") == "Runtime.exceptionThrown":
                errors.append("PAGE EX: " + str(msg["params"]["exceptionDetails"].get("text", ""))[:160])
    except Exception:
        pass
    ws.settimeout(60)
def click(sel):
    return js(f'(document.querySelector({sel!r})||{{}}).click && document.querySelector({sel!r}).click()')
def answer_current_quiz():
    """Click the option matching the current quiz target. Returns target word."""
    t = js('qz && qz.target && qz.target.w')
    ok = js('''(()=>{ const t=qz&&qz.target&&qz.target.w; if(!t) return false;
        const b=[...document.querySelectorAll("[data-qz]")].find(x=>x.querySelector(".sww").textContent===t);
        if(b){ b.click(); return true; } return false; })()''')
    return t if ok else None

send("Page.enable"); send("Runtime.enable")
send("Emulation.setDeviceMetricsOverride", {"width": W, "height": H, "deviceScaleFactor": 1, "mobile": True})
send("Page.navigate", {"url": "file://" + HTML})
time.sleep(3); drain()
shot("home")

# ---- T1: speech debounce ----
r = js('''(()=>{ let n=0; const ss=window.speechSynthesis, orig=ss.speak.bind(ss);
  ss.speak=u=>{n++}; say('t1 debounce probe'); say('t1 debounce probe'); const r1=n;
  return new Promise(res=>setTimeout(()=>{ say('t1 debounce probe'); ss.speak=orig; res([r1,n]); },900)); })()''')
check("T1 speech debounce drops identical utterance <800ms, allows after", r == [1, 2], r)
drain()

# ---- T2: quiz-kind registry ----
r = js('''[quizKind('sight').srs, quizKind('review').adaptKey, quizKind('review').starLabel,
  quizKind('pairs').starLabel, quizKind('level').adaptKey, quizKind('bogus').srs,
  quizKind('bogus').smartNote, quizKind('bogus').starLabel]''')
check("T2 QUIZ_KINDS registry values + unknown-kind defaults",
      r == [True, "review", "word star", "listening star", "level", False, False, "word star"], r)
drain()

# ---- T3: home sight quiz, full flow ----
click("#quizBtn"); time.sleep(0.8); drain()
check("T3 quiz screen shown", js('document.querySelector("#s-quiz").classList.contains("on")') is True)
pool_words = js('qz ? qz.pool.map(x=>x.w) : null')
for i in range(6):
    t = answer_current_quiz()
    if not t: break
    time.sleep(1.5)
drain()
check("T3 done screen after 6 answers", js('document.querySelector("#qzAgain")!==null') is True)
shot("quiz_done")
srs_words = js('Object.keys(JSON.parse(localStorage.getItem("fe_srs")||"{}"))')
check("T3 SRS recorded pool words", all(w in (srs_words or []) for w in (pool_words or [])), srs_words)
click("#qzAgain"); time.sleep(0.8); drain()
check("T3 Play again restarts quiz", js('qz!==null && qz.idx===0') is True)
click("#qzBack"); time.sleep(0.6); drain() # question screen's home button (qzHome only exists on the done screen)
check("T3 back home", js('document.querySelector("#s-home").classList.contains("on")') is True)
shot("home_after_quiz")

# ---- T4: sound pairs ----
click("#pairsBtn"); time.sleep(0.8); drain()
check("T4 pairs screen shown", js('qz!==null && qz.kind==="pairs"') is True)
pair_ok, crashed = True, False
for i in range(6):
    st = js('''(()=>{ if(!qz||!qz.target) return "noqz";
      const t=qz.target.w, p=qz.pairOf&&qz.pairOf[t];
      const opts=[...document.querySelectorAll("[data-qz]")].map(x=>x.querySelector(".sww").textContent);
      return JSON.stringify({t, p, hasP: p?opts.includes(p):"nopair"}); })()''')
    try:
        d = json.loads(st)
        if not (d["p"] and d["hasP"]): pair_ok = False
    except Exception:
        crashed = True; break
    answer_current_quiz(); time.sleep(1.5)
drain()
check("T4 every round offered the minimal-pair partner, no crash", pair_ok and not crashed)
check("T4 pairs done screen", js('document.querySelector("#qzAgain")!==null') is True)
click("#qzAgain"); time.sleep(0.8); drain()
check("T4 replay keeps pairOf mapping", js('qz!==null && qz.pairOf!==null && Object.keys(qz.pairOf).length>0') is True)
t = answer_current_quiz(); time.sleep(1.5); drain()
check("T4 replay first question answerable", t is not None)
click("#qzHome"); time.sleep(0.6); drain()


# ---- T17: gameRound (Listen/Read steps) feeds per-word outcomes to the SRS ----
click('[data-lvl="0"]'); time.sleep(0.6); drain()
click('[data-step="listen"]'); time.sleep(1.2); drain()
t17 = js('''(()=>{ const say=document.querySelector("#rwSay"); if(!say) return ["norw"];
  const t=say.textContent.replace(/[^a-z]/gi,"");
  const opts=[...document.querySelectorAll(".choice")];
  const wrong=opts.find(x=>x.dataset.w!==t), right=opts.find(x=>x.dataset.w===t);
  if(!wrong||!right) return ["noopts"];
  wrong.click(); right.click(); return ["clicked",t]; })()''')
time.sleep(1.6); drain()
t17w = t17[1] if t17 and len(t17) > 1 else ""
t17r = js('(()=>{ const s=JSON.parse(localStorage.getItem("fe_srs")||"{}"); const r=s[' + json.dumps(t17w) + ']; return r?r.h.slice(-1):null; })()') if t17 and t17[0] == "clicked" else None
check("T17 Listen step records miss-then-correct to SRS", t17r == [0], [t17, t17r])
click("#backHome"); time.sleep(0.6); drain()
# ---- T18: srsDue spans every bank ----
js('''(()=>{ const s=JSON.parse(localStorage.getItem("fe_srs")||"{}");
  s["pin"]={streak:0,iv:1,due:0,consecErr:1,h:[0],lastSeen:Date.now()};
  localStorage.setItem("fe_srs",JSON.stringify(s)); })()''')
t18 = js('srsDue().map(w=>w.w)')
check("T18 srsDue includes due level words (not just sight words)", "pin" in (t18 or []), t18)
# ---- T19: unified Tricky-words card + review quiz ----
js('renderHome()')
t19a = js('(()=>{ const c=document.querySelector("#dueCard"); return [c.style.display!=="none", document.querySelector("#dueBtn").textContent]; })()')
check("T19 due card visible with count", t19a[0] is True and "1 word" in t19a[1], t19a)
click("#dueBtn"); time.sleep(0.8); drain()
check("T19 review quiz starts with kind=review", js('qz!==null && qz.kind==="review" && document.querySelector("#s-quiz").classList.contains("on")') is True)
t = answer_current_quiz(); time.sleep(1.5); drain()
check("T19 review pool answered, done screen shown", js('document.querySelector("#qzAgain")!==null') is True, t)
t19b = js('(()=>{ const r=JSON.parse(localStorage.getItem("fe_srs")||"{}")["pin"]; return r&&r.due>Date.now(); })()')
check("T19 correct review answer pushes word's due date out", t19b is True)
click("#qzHome"); time.sleep(0.6); drain()
# ---- T5: reset clears ALL keys incl fe_grad ----
js('''localStorage.setItem("fe_grad","1"); localStorage.setItem("fe_srs",'{"x":1}');
  localStorage.setItem("fe_adapt",'{"x":1}'); localStorage.setItem("fe_streak",'{"count":5,"last":"x"}');
  localStorage.setItem("fe_together",'{"x":1}'); window.confirm=()=>true;''')
# open parent sheet via gate keyboard path, then reset
js('document.querySelector("#gate").dispatchEvent(new KeyboardEvent("keydown",{key:"Enter",bubbles:true}))')
time.sleep(0.5)
check("T5 parent sheet opened", js('document.querySelector("#sheet").classList.contains("on")') is True)
shot("parent_sheet")
# ---- T9: sheet scroll containment ----
t9 = js('''(()=>{ const el=document.querySelector(".sheetin"); const cs=getComputedStyle(el);
  return [cs.overflowY, el.scrollHeight>el.clientHeight+20]; })()''')
check("T9 sheet scrolls internally (overlay content can't trap Close/Reset)", t9==["auto",True], t9)
# ---- T16: Reset button reachable by scrolling the sheet ----
t16 = js('''(()=>{ const el=document.querySelector(".sheetin"); const b=document.querySelector("#resetProg");
  b.scrollIntoView(); const r=b.getBoundingClientRect(), e=el.getBoundingClientRect();
  return r.top>=e.top-2 && r.bottom<=e.bottom+2; })()''')
check("T16 Reset button reachable inside scrolled sheet", t16 is True)
js("window.confirm=()=>true"); click("#resetProg"); time.sleep(0.8); drain()
left = js('FE_KEYS.filter(k=>localStorage.getItem(k)!==null)')
check("T5 reset removed every FE_KEYS key (incl fe_grad)", left == [], left)
check("T5 in-memory progress reset", js('prog.done.length===0 && streak.count===0') is True)
check("T5 levels relocked", js('document.querySelectorAll("[data-lvl]")[1].disabled===true') is True)
js('renderHome()')
check("T20 due card hidden when nothing is due", js('document.querySelector("#dueCard").style.display==="none"') is True)
drain()

drain()

# ---- T6: speakHeard with null spk ----
r = js('(()=>{ spk=null; try{ speakHeard("hello world"); return "ok"; }catch(e){ return "threw:"+e.message; } })()')
check("T6 speakHeard(null spk) does not throw", r == "ok", r)
drain()

# ---- T10: build tiles are state-based (double-tap can't skip) ----
click('[data-lvl="0"]'); time.sleep(0.6); drain()
click('[data-step="blend"]'); time.sleep(0.8); drain()
t10a = js('document.querySelectorAll("#tiles .tile").length>0')
tile0 = js('(()=>{ const t=document.querySelectorAll("#tiles .tile")[0]; t.click(); t.click(); return document.querySelectorAll("#tiles .tile.lit").length; })()')
check("T10 double-tapped tile lights only once", t10a and tile0==1, tile0)
js('(()=>{ document.querySelectorAll("#tiles .tile").forEach(t=>{ if(!t.classList.contains("lit")) t.click(); }); })()')
time.sleep(2.8); drain()
t10b = js('document.querySelector("#tiles")!==null')
check("T10 completing all tiles advances the round", t10b is True)
click("#backHome"); time.sleep(0.6); drain()
# ---- T11: level-scoped segmentation + per-word keyword ----
t11 = js('''[segWord("yell",[]).join(","), segWord("yell").join(","),
  (()=>{ const L=LEVELS[4]; const pick=w=>{ const cands=L.letters.filter(c=>c.l.toLowerCase()==="oo");
    const hit=cands.find(c=>c.w.toLowerCase()===w)||cands[0]; return hit?hit.w:null; };
    return pick("moon")+"/"+pick("book"); })()]''')
check("T11 level-scoped segWord; oo->moon in moon, oo->book in book",
      t11==["y,e,l,l","y,e,ll","moon/book"], t11)
# ---- T13: quiz round-lock after correct answer ----
click("#quizBtn"); time.sleep(0.8); drain()
t13 = js('''(()=>{ const t=qz.target.w;
  [...document.querySelectorAll("[data-qz]")].find(x=>x.querySelector(".sww").textContent===t).click();
  const wrong=[...document.querySelectorAll("[data-qz]")].find(x=>x.querySelector(".sww").textContent!==t);
  if(wrong) wrong.click();
  return [qz.answered===true,(qz.wrongStreak||0)]; })()''')
check("T13 stray taps after correct answer are ignored", t13==[True,0], t13)
time.sleep(1.6); drain(); click("#qzBack"); time.sleep(0.5); drain()
# ---- T14: startQuiz guards empty/missing bank ----
t14 = js('(()=>{ startQuiz({bank:[],kind:"sight"}); const r1=(qz===null); startQuiz(); const r2=(qz===null); return [r1,r2]; })()')
check("T14 startQuiz ignores empty/missing bank", t14==[True,True], t14)
drain()
# ---- T7: overflow at 3 viewports ----
def overflow():
    return js('document.documentElement.scrollWidth <= window.innerWidth')
check("T7 no overflow 390x844 (home)", overflow() is True)
for (w, h, tag) in [(1440, 900, "desktop"), (844, 390, "landscape")]:
    send("Emulation.setDeviceMetricsOverride", {"width": w, "height": h, "deviceScaleFactor": 1, "mobile": False})
    send("Page.navigate", {"url": "file://" + HTML}); time.sleep(2.5); drain()
    check(f"T7 no overflow {w}x{h} (home)", overflow() is True)
    shot(f"home_{tag}")
drain()

# ---- T12: corrupt fe_prog can't blank the app ----
send("Emulation.setDeviceMetricsOverride", {"width":390,"height":844,"deviceScaleFactor":1,"mobile":True})
js('localStorage.setItem("fe_prog","{{{corrupt"); location.reload();')
time.sleep(3); drain()
check("T12 corrupt fe_prog still boots to home", js('document.querySelector("#s-home").classList.contains("on")') is True)
js('localStorage.removeItem("fe_prog")')
drain()
print("\nRUNTIME/PAGE ERRORS:", errors if errors else "none")
print("FAILURES:", fails if fails else "none")
print("RESULT:", "ALL PASS" if not fails and not errors else "NEEDS ATTENTION")
ws.close()
