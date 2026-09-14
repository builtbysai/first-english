/* Strict decodability validator for First English Level 8 (y, x).
 * Loads the shipped L1-L3 from the app HTML, L4-L5 from levels45.json,
 * L6-L7 + sight set 2 from levels67.json, then asserts:
 *  - every keyword is decodable from the cumulative inventory (greedy longest-match)
 *  - every word is fully decodable AND uses >=1 of its level's new sounds
 *  - every story sentence is 3-6 words, each token decodable or sight-listed
 * Exit 0 + "ALL DECODABLE" on success; non-zero with failure list otherwise. */
const fs = require("fs");
const DIR = "/home/hatch/workspace/english-app/";
const html = fs.readFileSync(DIR + "first_english_v2.html", "utf8");
const m = html.match(/const LEVELS = \[([\s\S]*?)\n\];/);
const LEVELS_HTML = eval("(" + m[0].replace("const LEVELS = ", "").replace(/;\s*$/, "") + ")");
const LEVELS_13 = LEVELS_HTML.slice(0, 3); // legacy single-letter levels only
const L45 = JSON.parse(fs.readFileSync(DIR + "levels45.json", "utf8"));
const L67 = JSON.parse(fs.readFileSync(DIR + "levels67.json", "utf8"));
const L8 = JSON.parse(fs.readFileSync(DIR + "levels8.json", "utf8"));

// shape check mirrors levels45.json
for (const L of L67.levels) {
  for (const k of ["id","cls","emo","name","desc","letters","words","story"])
    if (!(k in L)) throw new Error("missing key " + k);
  if (L.letters.length !== 6 || L.words.length !== 10 || L.story.length !== 4)
    throw new Error("bad counts in " + L.name);
}
for (const L of L8.levels) {
  for (const k of ["id","cls","emo","name","desc","letters","words","story"])
    if (!(k in L)) throw new Error("missing key " + k);
  if (L.letters.length !== 2 || L.words.length !== 10 || L.story.length !== 4)
    throw new Error("bad counts in " + L.name);
}
if (L67.sight_words.length !== 10) throw new Error("sight set 2 must have 10 words");

const SIGHT1 = L45.sight_words.map(s => s.w.toLowerCase());
const SIGHT2 = L67.sight_words.map(s => s.w.toLowerCase());
const SIGHT = [...SIGHT1, ...SIGHT2];

const GRAPHEMES = ["ai","oa","ie","ee","or","ng","oo",
                   "sh","ch","th","qu","ou","oi",
                   "air","ear","igh","ue","er","ar"]; // longest-match handles air>ar, ear>er
const taught = [];
const probs = [];

function segment(w) { // returns array of graphemes or null if any char untaught
  const gs = GRAPHEMES.filter(g => taught.includes(g));
  const out = []; const lw = w.toLowerCase(); let i = 0;
  while (i < w.length) {
    let mt = null;
    for (const g of gs) if (lw.startsWith(g, i) && (!mt || g.length > mt.length)) mt = g;
    if (mt) { out.push(mt); i += mt.length; continue; }
    if (taught.includes(lw[i])) { out.push(lw[i]); i++; continue; }
    return null;
  }
  return out;
}

const allLevels = [
  ...LEVELS_13.map(L => ({ name: "L1-3", letters: L.letters, words: [], story: [] })),
  ...L45.levels.map(L => ({ name: L.name, letters: L.letters, words: L.words.map(x => x.w), story: L.story.map(s => s.t),
                            newSounds: L.letters.map(c => c.l.toLowerCase()) })),
  ...L67.levels.map(L => ({ name: L.name, letters: L.letters, words: L.words.map(x => x.w), story: L.story.map(s => s.t),
                            newSounds: L.letters.map(c => c.l.toLowerCase()) })),
  ...L8.levels.map(L => ({ name: L.name, letters: L.letters, words: L.words.map(x => x.w), story: L.story.map(s => s.t),
                            newSounds: L.letters.map(c => c.l.toLowerCase()) })),
];

allLevels.forEach((L, li) => {
  L.letters.forEach(c => { const g = c.l.toLowerCase(); if (!taught.includes(g)) taught.push(g); });
  L.letters.forEach(c => {
    if (L.newSounds) { // L4+: keyword must be fully decodable at introduction
      if (!segment(c.w)) probs.push(`${L.name} keyword "${c.w}" (${c.l}): NOT decodable`);
    } else if (!c.w.toLowerCase().startsWith(c.l.toLowerCase())) { // L1-3: initial-sound keyword
      probs.push(`${L.name} keyword "${c.w}" (${c.l}): does not start with letter`);
    }
  });
  (L.words || []).forEach(w => {
    const seg = segment(w);
    if (!seg) { probs.push(`${L.name} word "${w}": untaught sound`); return; }
    if (L.newSounds && !seg.some(g => L.newSounds.includes(g)))
      probs.push(`${L.name} word "${w}": uses none of the level's new sounds`);
  });
  (L.story || []).forEach(t => {
    const toks = t.replace(/[.,!?]/g, "").split(/\s+/);
    if (toks.length < 3 || toks.length > 6) probs.push(`${L.name} story "${t}": ${toks.length} words (need 3-6)`);
    toks.forEach(tok => {
      if (!SIGHT.includes(tok.toLowerCase()) && !segment(tok))
        probs.push(`${L.name} story "${t}": token "${tok}" not decodable/sight`);
    });
  });
});

if (probs.length) { console.log("FAILURES:\n" + probs.join("\n")); process.exit(1); }
console.log("ALL DECODABLE ✓ (L1-L8 words+keywords, stories, sight sets 1-2)");
console.log("taught graphemes:", taught.join(","));
console.log("sight set 2:", SIGHT2.join(","));
