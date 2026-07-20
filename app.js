/* =========================================================================
   くらしの仕組み化アプリ（本体・JavaScript版）
   設計思想：意志力を1ミリも要求しない。行動科学の12原則をUIの形に落とし込む。
   ※ もとはPython(PyScript)版。スマホでの初回読み込みを速くするため軽いJSに移植。
      見た目・機能・データ保存はすべて同じ。

   【行動科学の原則 → 実装箇所 対応表】（詳細はREADMEにも記載）
    1. 摩擦の最小化        : 起動直後ホーム最上部に「今やること」/ 大トリガーボタン / タップ中心
    2. 実行意図(if-then)  : 習慣は必ず「〜したら→〜する」。追加も穴埋めフォーム(buildAddHabit)
    3. 習慣スタッキング     : TRIGGER_PRESETS ＋ 自分で追加したきっかけを候補提供
    4. 2分ルール&最小モード : 全習慣に actionMin。ホームの最小モードで一括最小化。満額カウント
    5. 現在バイアス(誘惑束) : 達成即演出(fxCelebrate)＋褒め言葉＋任意のご褒美ルール(reward)
    6. 変動報酬            : completeHabit 内でランダムにボーナス点・レア褒め・称号
    7. 損失回避&保有効果    : ストリークを育つ植物で可視化(plantFor / ガーデン)
    8. 進捗の付与効果       : 初期ポイント20＝ゲージ20%開始 / スタンプ2個押済で開始
    9. フレッシュスタート    : 責めない文言。おやすみ券。週初/月初の再開提案(freshStartBanner)
   10. デフォルト効果       : PRESET_HABITS を有効化済みで同梱。設定を開かなくても完結
   11. アイデンティティ     : オンボで「なりたい自分」選択。達成時に「〜な人の行動を1つ積みました」
   12. ツァイガルニク       : ホームに「あと〇つで今日コンプリート」を控えめに表示
   ========================================================================= */

"use strict";

const STORAGE_KEY = "kurashi_state_v1";

/* ====================== マスターデータ ====================== */

const IDENTITIES = [
  { id: "morning",  label: "朝に余裕のある人", emoji: "🌅" },
  { id: "tidy",     label: "ちゃんとした部屋で暮らす人", emoji: "🧹" },
  { id: "learner",  label: "学び続ける人", emoji: "📚" },
  { id: "balanced", label: "心と体を整える人", emoji: "🧘" },
];

const TRIGGER_PRESETS = [
  "帰宅して靴を脱いだら", "歯を磨いたら", "起きたら", "寝る前に",
  "お風呂から出たら", "コーヒー/お茶を淹れたら",
  "電子レンジを回している間に", "コンビニに寄る前に",
];

const PRESET_HABITS = [
  { trigger: "帰宅して靴を脱いだら", action: "床の物を1つだけ定位置に戻す",
    actionMin: "床の物を1つ拾って置くだけ", category: "掃除・身支度", streak: 2 },
  { trigger: "歯を磨いたら", action: "参考書を開いて1行だけ読む",
    actionMin: "参考書を開くだけ", category: "勉強・自己投資", streak: 3 },
  { trigger: "寝る前に", action: "明日の服を椅子にかける",
    actionMin: "明日着る上着1枚だけ出す", category: "掃除・身支度", streak: 1 },
  { trigger: "起きたら", action: "カーテンを開けて水を1杯飲む",
    actionMin: "カーテンを開けるだけ", category: "掃除・身支度", streak: 2 },
  { trigger: "コーヒー/お茶を淹れたら", action: "今日やる小さなことを1つ声に出す",
    actionMin: "深呼吸を1回する", category: "勉強・自己投資", streak: 0 },
];

const CATEGORY_EMOJI = { "勉強・自己投資": "📚", "掃除・身支度": "🧹", "その他": "⭐" };

const TRIGGER_EMOJI = {
  "帰宅して靴を脱いだら": "🏠", "歯を磨いたら": "🪥", "起きたら": "🌅",
  "寝る前に": "🌙", "お風呂から出たら": "🛁", "コーヒー/お茶を淹れたら": "☕",
  "電子レンジを回している間に": "🍱", "コンビニに寄る前に": "🏪",
};

// 自分できっかけを作る時に選べる絵文字（選択で。原則1：入力の摩擦を減らす）
const EMOJI_CHOICES = ["⏰","🍽️","🚿","👕","🧴","🛏️","🚪","🪑",
                       "📱","🧺","🍵","🐟","💊","🚶","🧻","✏️","⭐"];

const PRAISE = ["ナイス！","いいね、積み上がった","その1つが効く","よくやった！",
                "今日のあなた、動けてる","小さな一歩、確かな一歩","えらい！","その調子"];
const PRAISE_RARE = ["✨レア✨ 完璧なリズム！","🎉神ってる！最高の流れ","💎今日のあなたは冴えてる",
                     "🌟今のは効いた、間違いなく"];
const RARE_BADGES = ["早起きの妖精","静けさの主","コツコツの化身","流れをつかむ者","小さな巨人"];

/* ====================== 日付ユーティリティ ====================== */

function isoDate(d) {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}
function todayISO() { return isoDate(new Date()); }
function addDays(d, n) { const x = new Date(d); x.setDate(x.getDate() + n); return x; }
// 月曜=0 … 日曜=6 に変換（原則3のヒートマップ・原則9の節目判定で使用）
function mondayIndex(d) { return (d.getDay() + 6) % 7; }

function choice(arr) { return arr[Math.floor(Math.random() * arr.length)]; }

/* ====================== 状態（localStorage） ====================== */

function defaultState() {
  const habits = PRESET_HABITS.map((h, i) => ({
    id: "p" + i,
    trigger: h.trigger,
    action: h.action,
    actionMin: h.actionMin,
    category: h.category,
    reward: "",
    enabled: true,
    streak: h.streak,        // 原則8：ゼロからでなく少し進んだ状態
    lastDone: "",
  }));
  return {
    version: 1,
    onboarded: false,
    identity: "",
    habits,
    customTriggers: [],       // 自分で追加したきっかけ [{name, emoji}]（原則3）
    points: 20,               // 原則8：レベルゲージ20%から開始
    stamps: 2,                // 原則8：スタンプカード2個押済で開始
    badges: [],
    minModeDate: "",          // この日付が今日なら最小モードON（原則4）
    restTicketsMonth: "",     // "YYYY-MM"：今月分を使ったか
    restDays: [],             // おやすみ券を使った日（ストリーク保護／原則9）
    goals: [],                // いつかリスト（機能4）
    doneLog: {},              // {"YYYY-MM-DD": 完了数}（原則3ヒートマップ・加点式）
    seenFreshDate: "",        // フレッシュスタート案内を出した日
  };
}

function loadState() {
  const raw = localStorage.getItem(STORAGE_KEY);
  if (!raw) return defaultState();
  try {
    const s = JSON.parse(raw);
    const d = defaultState();
    for (const k in d) { if (!(k in s)) s[k] = d[k]; }  // 後方互換：欠損キー補完
    return s;
  } catch (e) {
    return defaultState();
  }
}

function saveState() { localStorage.setItem(STORAGE_KEY, JSON.stringify(state)); }

let state = loadState();
let nav = { screen: "home", onbStep: 1 };
let flow = { active: false, trigger: "", queue: [], idx: 0 };

/* ====================== ロジック・ヘルパー ====================== */

function minModeOn() { return state.minModeDate === todayISO(); }
function habitDoneToday(h) { return h.lastDone === todayISO(); }
function enabledHabits() { return state.habits.filter(h => h.enabled); }
function habitsForTrigger(t) { return enabledHabits().filter(h => h.trigger === t); }
function findHabit(id) { return state.habits.find(h => h.id === id) || null; }

function openTriggers() {
  const seen = [];
  for (const h of enabledHabits()) {
    if (!habitDoneToday(h) && !seen.includes(h.trigger)) seen.push(h.trigger);
  }
  return seen;
}
function totalToday() { return enabledHabits().length; }
function doneTodayCount() { return enabledHabits().filter(habitDoneToday).length; }

function levelInfo() {
  const pts = state.points;
  return { level: Math.floor(pts / 100) + 1, inLevel: pts % 100 };
}

function globalStreak() {
  const log = state.doneLog, rest = new Set(state.restDays);
  const t = new Date(); const y = addDays(t, -1);
  const ti = isoDate(t), yi = isoDate(y);
  const hit = k => (k in log) || rest.has(k);
  if (!hit(ti) && !hit(yi)) return 0;
  let cur = hit(ti) ? t : y;
  let n = 0;
  while (hit(isoDate(cur))) { n++; cur = addDays(cur, -1); }
  return n;
}

function plantFor(streak) {
  if (streak <= 0) return ["🌱", "これから育てましょう"];
  if (streak <= 2) return ["🌱", "芽が出ました"];
  if (streak <= 5) return ["🌿", "すくすく育っています"];
  if (streak <= 10) return ["🪴", "しっかり根づいてきました"];
  if (streak <= 20) return ["🌳", "立派に育っています"];
  return ["🌳✨", "見事な大樹です"];
}

function triggerEmoji(t) {
  if (t in TRIGGER_EMOJI) return TRIGGER_EMOJI[t];
  const c = (state.customTriggers || []).find(c => c.name === t);
  return c ? (c.emoji || "•") : "•";
}
function allTriggers() {
  const r = TRIGGER_PRESETS.slice();
  for (const c of state.customTriggers || []) {
    if (c.name && !r.includes(c.name)) r.push(c.name);
  }
  return r;
}
function identityLabel() {
  const i = IDENTITIES.find(i => i.id === state.identity);
  return i ? i.label : "";
}

/* ====================== 達成処理（原則5・6・8・11） ====================== */

function completeHabit(h) {
  if (habitDoneToday(h)) return;   // 二重加算防止
  const t = todayISO();
  const y = isoDate(addDays(new Date(), -1));

  // ストリーク更新（責めない。途切れても1から積み直すだけ）
  h.streak = (h.lastDone === y) ? (h.streak || 0) + 1 : 1;
  h.lastDone = t;

  state.doneLog[t] = (state.doneLog[t] || 0) + 1;

  let gained = 10;             // 基本点（最小でも満額：原則4）
  const messages = [];
  let baseMsg = choice(PRAISE);

  // 変動報酬（原則6）
  const roll = Math.random();
  if (roll < 0.05) {
    const badge = choice(RARE_BADGES);
    if (!state.badges.includes(badge)) state.badges.push(badge);
    gained += 30;
    messages.push(`🏅 称号「${badge}」を獲得！ +30pt`);
    baseMsg = choice(PRAISE_RARE);
  } else if (roll < 0.20) {
    const bonus = choice([10, 15, 20]);
    gained += bonus;
    messages.push(`🎁 ボーナス +${bonus}pt！`);
    if (Math.random() < 0.5) baseMsg = choice(PRAISE_RARE);
  }

  state.points += gained;

  // スタンプカード（原則8：2個押済で開始、10でリセット＆ボーナス）
  state.stamps += 1;
  if (state.stamps >= 10) {
    state.stamps = 0;
    state.points += 50;
    messages.push("⭐ スタンプ10個コンプ！ +50pt");
  }

  // アイデンティティへの投票（原則11）
  const idl = identityLabel();
  if (idl) messages.unshift(`今日のあなたは『${idl}』の行動を1つ積みました`);

  // ご褒美ルール（原則5）
  if (h.reward) messages.push(`🎬 ご褒美OK：${h.reward}`);

  saveState();
  fxCelebrate(baseMsg, messages);
}

/* ====================== 達成演出（原則5） ====================== */

function fxCelebrate(headline, extraLines) {
  const fx = document.getElementById("fx");
  const lines = extraLines.map(m => `<div class="fx-line">${esc(m)}</div>`).join("");
  const colors = ["#5faf7d","#ffd166","#ef8354","#6aa6ff","#c58bff"];
  let confetti = "";
  for (let i = 0; i < 18; i++) {
    confetti += `<span class="confetti" style="left:${2 + Math.floor(Math.random()*94)}%;` +
                `animation-delay:${Math.floor(Math.random()*400)}ms;` +
                `background:${choice(colors)}"></span>`;
  }
  fx.innerHTML =
    `<div class="fx-overlay">` +
      `<div class="fx-confetti">${confetti}</div>` +
      `<div class="fx-card">` +
        `<div class="fx-emoji">🎉</div>` +
        `<div class="fx-headline">${esc(headline)}</div>` +
        lines +
      `</div>` +
    `</div>`;
  const clear = () => { fx.innerHTML = ""; render(); };
  fx.querySelector(".fx-overlay").addEventListener("click", clear);
  window.setTimeout(clear, 1600);
}

/* ====================== 描画ユーティリティ ====================== */

function esc(s) {
  return String(s)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
}

function render() {
  let html;
  if (!state.onboarded) html = buildOnboarding();
  else if (flow.active) html = buildFlow();
  else if (nav.screen === "home") html = buildHome();
  else if (nav.screen === "habits") html = buildHabits();
  else if (nav.screen === "add") html = buildAddHabit();
  else if (nav.screen === "goals") html = buildGoals();
  else if (nav.screen === "goal_add") html = buildGoalAdd();
  else if (nav.screen === "stats") html = buildStats();
  else if (nav.screen === "settings") html = buildSettings();
  else html = buildHome();
  document.getElementById("app").innerHTML = html;
}

function tabbar(active) {
  const tabs = [["home","🏠","ホーム"],["stats","📅","記録"],
                ["goals","🎯","目標"],["settings","⚙️","設定"]];
  const items = tabs.map(([key, icon, label]) => {
    const cls = key === active ? "tab active" : "tab";
    return `<button class="${cls}" data-act="go:${key}">` +
           `<div class="tab-ic">${icon}</div><div class="tab-lb">${label}</div></button>`;
  }).join("");
  return `<nav class="tabbar">${items}</nav>`;
}

/* ====================== 画面：オンボーディング（機能5 / 原則10・11） ====================== */

function buildOnboarding() {
  const step = nav.onbStep || 1;
  if (step === 1) {
    const cards = IDENTITIES.map(i => {
      const sel = state.identity === i.id ? "sel" : "";
      return `<button class="id-card ${sel}" data-act="onb_identity:${i.id}">` +
             `<div class="id-emoji">${i.emoji}</div>` +
             `<div class="id-label">${esc(i.label)}</div></button>`;
    }).join("");
    const nextbtn = state.identity
      ? `<button class="btn-primary big" data-act="onb_next">次へ</button>` : "";
    return `<div class="screen onb">` +
      `<div class="onb-step">1 / 3</div>` +
      `<h1 class="onb-h">どんな自分になりたい？</h1>` +
      `<p class="onb-sub">1つだけ選んでください。あとで変えられます。</p>` +
      `<div class="id-grid">${cards}</div>${nextbtn}</div>`;
  }
  if (step === 2) {
    const rows = state.habits.map(h =>
      `<div class="preset-row">` +
      `<span class="pill">${triggerEmoji(h.trigger)} ${esc(h.trigger)}</span>` +
      `<span class="arrow">→</span>` +
      `<span class="preset-action">${esc(h.action)}</span></div>`).join("");
    return `<div class="screen onb">` +
      `<div class="onb-step">2 / 3</div>` +
      `<h1 class="onb-h">この習慣で始めます</h1>` +
      `<p class="onb-sub">ぜんぶ2分以内で終わる小さなことだけ。<br>今は何も考えず、このままでOK。</p>` +
      `<div class="preset-list">${rows}</div>` +
      `<button class="btn-primary big" data-act="onb_next">このままでOK</button>` +
      `<button class="btn-ghost" data-act="go_home_from_onb">あとで習慣は調整する</button></div>`;
  }
  return `<div class="screen onb center">` +
    `<div class="onb-step">3 / 3</div>` +
    `<div class="big-emoji">🌱</div>` +
    `<h1 class="onb-h">準備できました</h1>` +
    `<p class="onb-sub">むずかしいことは何もありません。<br>アプリを開いて、出てきた1つをタップするだけ。</p>` +
    `<button class="btn-primary big" data-act="onb_finish">はじめる</button></div>`;
}

/* ====================== 画面：ホーム（コア / 原則1・4・7・11・12） ====================== */

function buildHome() {
  const triggers = openTriggers();
  const done = doneTodayCount();
  const total = totalToday();

  let nowCard;
  if (triggers.length) {
    const top = triggers[0];
    const nHere = habitsForTrigger(top).filter(h => !habitDoneToday(h)).length;
    nowCard = `<div class="now-card" data-act="trigger:${esc(top)}">` +
      `<div class="now-label">いま、これだけ</div>` +
      `<div class="now-trigger">${triggerEmoji(top)} ${esc(top)}</div>` +
      `<div class="now-hint">タップして始める（残り${nHere}）</div></div>`;
  } else {
    nowCard = `<div class="now-card done">` +
      `<div class="now-emoji">🎉</div>` +
      `<div class="now-trigger">今日のぶん、完了！</div>` +
      `<div class="now-hint">お疲れさまでした</div></div>`;
  }

  const mm = minModeOn();
  const minToggle = `<button class="min-toggle ${mm ? "on" : ""}" data-act="toggle_min">` +
    `${mm ? "🌙" : "🔋"} 最小モード ${mm ? "ON（今日は最小でOK）" : "OFF"}</button>`;

  let zeigarnik = "";
  const remaining = total - done;
  if (remaining > 0 && remaining <= 2 && total > 0) {
    zeigarnik = `<div class="zeigarnik">あと${remaining}つで今日コンプリート</div>`;
  }

  let otherBtns = "";
  for (const t of triggers.slice(1)) {
    const nHere = habitsForTrigger(t).filter(h => !habitDoneToday(h)).length;
    otherBtns += `<button class="trig-btn" data-act="trigger:${esc(t)}">` +
      `<span class="trig-emoji">${triggerEmoji(t)}</span>` +
      `<span class="trig-text">${esc(t)}</span>` +
      `<span class="trig-badge">${nHere}</span></button>`;
  }
  if (otherBtns) {
    otherBtns = `<div class="section-title">ほかのきっかけ</div>` +
                `<div class="trig-list">${otherBtns}</div>`;
  }

  const streak = globalStreak();
  const [plant, plantMsg] = plantFor(streak);
  const { level, inLevel } = levelInfo();
  const garden = `<div class="garden">` +
    `<div class="garden-plant">${plant}</div>` +
    `<div class="garden-info"><div class="garden-streak">連続 ${streak}日</div>` +
    `<div class="garden-msg">${esc(plantMsg)}</div></div></div>`;
  const levelbar = `<div class="levelbar">` +
    `<div class="level-top"><span>Lv.${level}</span><span>${state.points}pt</span></div>` +
    `<div class="bar"><div class="bar-fill" style="width:${inLevel}%"></div></div></div>`;

  return `<div class="screen home">` +
    `<div class="home-head"><div class="greeting">${greeting()}</div>${badgeChip()}</div>` +
    freshStartBanner() + nowCard + zeigarnik + minToggle + garden + levelbar + otherBtns +
    `</div>` + tabbar("home");
}

function greeting() {
  const idl = identityLabel();
  return idl ? `『${esc(idl)}』へ、一歩ずつ` : "おかえりなさい";
}
function badgeChip() {
  const n = state.badges.length;
  return n ? `<button class="badge-chip" data-act="go:settings">🏅 ${n}</button>` : "";
}

function freshStartBanner() {
  const streak = globalStreak();
  const hasLog = Object.keys(state.doneLog).length > 0;
  if (streak === 0 && hasLog) {
    if (state.seenFreshDate !== todayISO()) {
      return `<div class="fresh">` +
        `<div class="fresh-title">おかえりなさい 🌱</div>` +
        `<div class="fresh-body">少し休憩していましたね。責める必要はありません。` +
        `<b>今日が新しいスタート日</b>です。まずは最小の1つから。</div>` +
        `<button class="btn-ghost sm" data-act="dismiss_fresh">わかった</button></div>`;
    }
  }
  const t = new Date();
  if (t.getDay() === 1 || t.getDate() === 1) {   // 月曜 or 月初（原則9の節目）
    const label = t.getDay() === 1 ? "新しい週" : "新しい月";
    return `<div class="fresh soft"><div class="fresh-body">` +
      `今日は<b>${label}の始まり</b>。仕切り直しにちょうどいい日です。</div></div>`;
  }
  return "";
}

/* ====================== 画面：実行フロー（原則1・4） ====================== */

function startFlow(trigger) {
  const q = habitsForTrigger(trigger).filter(h => !habitDoneToday(h)).map(h => h.id);
  if (!q.length) return;
  flow = { active: true, trigger, queue: q, idx: 0 };
  render();
}

function currentFlowHabit() {
  while (flow.idx < flow.queue.length) {
    const h = findHabit(flow.queue[flow.idx]);
    if (h && !habitDoneToday(h)) return h;
    flow.idx++;
  }
  return null;
}

function buildFlow() {
  const h = currentFlowHabit();
  if (!h) { flow.active = false; return buildHome(); }

  const mm = minModeOn();
  const actionText = mm ? h.actionMin : h.action;
  const pos = flow.idx + 1, total = flow.queue.length;

  const memo = `<input id="memo" class="memo" type="text" ` +
    `placeholder="ひとことメモ（任意・書かなくてOK）" />`;

  let modeNote, altBtn;
  if (mm) {
    modeNote = `<div class="flow-mode">🌙 最小モード：これだけで満額です</div>`;
    altBtn = `<button class="btn-ghost sm" data-act="flow_normal_once">今日は通常版でやる</button>`;
  } else {
    modeNote = "";
    altBtn = `<button class="btn-ghost sm" data-act="flow_min_once">しんどい…最小版に切替（2分以内）</button>`;
  }
  const rewardHint = h.reward
    ? `<div class="flow-reward">🎁 できたらご褒美：${esc(h.reward)}</div>` : "";

  return `<div class="screen flow">` +
    `<button class="flow-close" data-act="flow_close">✕</button>` +
    `<div class="flow-progress">${pos} / ${total}</div>` +
    `<div class="flow-trigger">${triggerEmoji(flow.trigger)} ${esc(flow.trigger)}</div>` +
    `<div class="flow-arrow">↓</div>` +
    `<div class="flow-action">${esc(actionText)}</div>` +
    modeNote + rewardHint + memo +
    `<button class="btn-primary huge" data-act="flow_done">できた！</button>` +
    altBtn +
    `<button class="btn-ghost sm" data-act="flow_skip">今はしない（次へ）</button></div>`;
}

/* ====================== 画面：習慣の管理（機能1・2 / 原則2） ====================== */

function buildHabits() {
  const rows = state.habits.map(h => {
    const on = h.enabled ? "on" : "";
    const done = habitDoneToday(h) ? "✅" : "";
    return `<div class="habit-row"><div class="habit-main">` +
      `<div class="habit-if">${triggerEmoji(h.trigger)} ${esc(h.trigger)}</div>` +
      `<div class="habit-then">→ ${esc(h.action)}</div>` +
      `<div class="habit-min">最小：${esc(h.actionMin)}</div>` +
      `<div class="habit-meta">${esc(h.category || "その他")} ・ 連続${h.streak || 0}日 ${done}</div>` +
      `</div><div class="habit-actions">` +
      `<button class="sw ${on}" data-act="habit_toggle:${h.id}"></button>` +
      `<button class="del" data-act="habit_delete:${h.id}">削除</button></div></div>`;
  }).join("");
  return `<div class="screen list">` +
    `<div class="list-head"><button class="back" data-act="go:settings">‹ 戻る</button>` +
    `<h2>習慣の管理</h2></div>` +
    `<button class="btn-primary" data-act="go:add">＋ 習慣を追加</button>` +
    `<div class="hint">スイッチでON/OFF。全部そのままでも大丈夫です。</div>` +
    rows + `</div>` + tabbar("settings");
}

function buildAddHabit() {
  const trigOpts = allTriggers().map(t =>
    `<option value="${esc(t)}">${triggerEmoji(t)} ${esc(t)}</option>`).join("");
  const catOpts = Object.entries(CATEGORY_EMOJI).map(([c, e]) =>
    `<option value="${esc(c)}">${e} ${esc(c)}</option>`).join("");
  const emojiOpts = EMOJI_CHOICES.map(e => `<option value="${e}">${e}</option>`).join("");
  return `<div class="screen form">` +
    `<div class="list-head"><button class="back" data-act="go:habits">‹ 戻る</button>` +
    `<h2>習慣を追加</h2></div><div class="ff">` +
    `<label>① どの行動の“ついで”に？（〜したら）</label>` +
    `<select id="f_trigger" class="inp">${trigOpts}</select>` +
    `<div class="custom-trigger">` +
      `<label>リストにない時：自分できっかけを作る（任意）</label>` +
      `<div class="ct-row">` +
        `<select id="f_trigger_emoji" class="inp ct-emoji">${emojiOpts}</select>` +
        `<input id="f_trigger_custom" class="inp ct-text" type="text" placeholder="例：お皿を洗ったら" />` +
      `</div>` +
      `<div class="ct-hint">ここに書くと、上のリストより優先されます。次回から候補に出ます。</div>` +
    `</div>` +
    `<label>② 何をする？（通常版）</label>` +
    `<input id="f_action" class="inp" type="text" placeholder="例：参考書を1行読む" />` +
    `<label>③ 疲れた日の最小版（2分以内・必須）</label>` +
    `<input id="f_min" class="inp" type="text" placeholder="例：参考書を開くだけ" />` +
    `<label>④ カテゴリ</label>` +
    `<select id="f_cat" class="inp">${catOpts}</select>` +
    `<label>⑤ ご褒美ルール（任意）</label>` +
    `<input id="f_reward" class="inp" type="text" placeholder="例：できたら好きな動画1本OK" />` +
    `<button class="btn-primary big" data-act="add_habit_save">この習慣を追加</button>` +
    `</div></div>` + tabbar("settings");
}

/* ====================== 画面：目標・いつかリスト（機能4 / 原則4・11） ====================== */

function buildGoals() {
  let rows = "";
  if (!state.goals.length) {
    rows = `<div class="empty">まだ目標はありません。<br>「いつかやりたい」を1つ置いてみましょう。</div>`;
  }
  for (const g of state.goals) {
    const converted = g.converted ? "✅ 習慣化ずみ" : "";
    const convBtn = g.converted ? "" :
      `<button class="btn-primary sm" data-act="goal_to_habit:${g.id}">最初の2分を習慣にする</button>`;
    rows += `<div class="goal-row">` +
      `<div class="goal-when">${esc(g.when || "いつか")}</div>` +
      `<div class="goal-text">${esc(g.text)}</div>` +
      `<div class="goal-first">最初の2分：${esc(g.firstAction || "（未設定）")}</div>` +
      `<div class="goal-foot">${converted} ${convBtn}` +
      `<button class="del" data-act="goal_delete:${g.id}">削除</button></div></div>`;
  }
  return `<div class="screen list">` +
    `<div class="list-head"><h2>🎯 目標・いつかリスト</h2></div>` +
    `<button class="btn-primary" data-act="go:goal_add">＋ やりたいことを追加</button>` +
    `<div class="hint">大きな夢も、入口は「最初の2分」だけ。</div>` +
    rows + `</div>` + tabbar("goals");
}

function buildGoalAdd() {
  const whenOpts = ["今年中に","いつか","3か月以内に","この夏に"]
    .map(w => `<option value="${w}">${w}</option>`).join("");
  return `<div class="screen form">` +
    `<div class="list-head"><button class="back" data-act="go:goals">‹ 戻る</button>` +
    `<h2>やりたいことを追加</h2></div><div class="ff">` +
    `<label>① いつ？</label><select id="g_when" class="inp">${whenOpts}</select>` +
    `<label>② やりたいこと</label>` +
    `<input id="g_text" class="inp" type="text" placeholder="例：簿記の勉強を始める" />` +
    `<label>③ 最初の2分アクション（原則4）</label>` +
    `<input id="g_first" class="inp" type="text" placeholder="例：テキストを1ページ開く" />` +
    `<button class="btn-primary big" data-act="goal_save">追加する</button>` +
    `</div></div>` + tabbar("goals");
}

/* ====================== 画面：記録（機能3ヒートマップ / 原則3・7） ====================== */

function buildStats() {
  const log = state.doneLog;
  const t = new Date();
  const start = addDays(t, -(mondayIndex(t) + 7 * 4));  // 5週分さかのぼる
  const labels = ["月","火","水","木","金","土","日"];
  const header = labels.map(l => `<div class="hm-lbl">${l}</div>`).join("");
  let grid = "";
  let d = start;
  for (let i = 0; i < 35; i++) {
    const di = isoDate(d);
    const cnt = log[di] || 0;
    let cls, title;
    if (state.restDays.includes(di)) { cls = "hm-cell rest"; title = `${di} おやすみ`; }
    else if (cnt <= 0) { cls = "hm-cell"; title = di; }
    else if (cnt === 1) { cls = "hm-cell l1"; title = `${di} ・${cnt}件`; }
    else if (cnt === 2) { cls = "hm-cell l2"; title = `${di} ・${cnt}件`; }
    else { cls = "hm-cell l3"; title = `${di} ・${cnt}件`; }
    const future = d > t ? " future" : "";
    grid += `<div class="${cls}${future}" title="${esc(title)}"></div>`;
    d = addDays(d, 1);
  }

  const streak = globalStreak();
  const [plant, plantMsg] = plantFor(streak);
  const { level } = levelInfo();
  const totalDone = Object.values(log).reduce((a, b) => a + b, 0);

  let badgesHtml = "";
  if (state.badges.length) {
    const chips = state.badges.map(b => `<span class="bchip">🏅 ${esc(b)}</span>`).join("");
    badgesHtml = `<div class="section-title">称号</div><div class="badges">${chips}</div>`;
  }

  return `<div class="screen stats">` +
    `<div class="list-head"><h2>📅 記録</h2></div>` +
    `<div class="garden big"><div class="garden-plant xl">${plant}</div>` +
    `<div class="garden-info"><div class="garden-streak">連続 ${streak}日</div>` +
    `<div class="garden-msg">${esc(plantMsg)}</div></div></div>` +
    `<div class="stat-cards">` +
    `<div class="stat-card"><div class="stat-num">Lv.${level}</div><div class="stat-lb">レベル</div></div>` +
    `<div class="stat-card"><div class="stat-num">${state.points}</div><div class="stat-lb">ポイント</div></div>` +
    `<div class="stat-card"><div class="stat-num">${totalDone}</div><div class="stat-lb">のべ達成</div></div>` +
    `</div>` +
    `<div class="section-title">やった日だけ色づきます</div>` +
    `<div class="heatmap"><div class="hm-head">${header}</div><div class="hm-grid">${grid}</div></div>` +
    `<div class="hm-legend">少 <span class="hm-cell"></span><span class="hm-cell l1"></span>` +
    `<span class="hm-cell l2"></span><span class="hm-cell l3"></span> 多</div>` +
    badgesHtml + `</div>` + tabbar("stats");
}

/* ====================== 画面：設定（原則10：開かなくても完結） ====================== */

function buildSettings() {
  const idcards = IDENTITIES.map(i => {
    const sel = state.identity === i.id ? "sel" : "";
    return `<button class="id-mini ${sel}" data-act="identity_change:${i.id}">${i.emoji} ${esc(i.label)}</button>`;
  }).join("");

  const ym = todayISO().slice(0, 7);
  const ticketUsed = state.restTicketsMonth === ym;
  const ticket = ticketUsed
    ? `<div class="ticket used">🎫 今月のおやすみ券は使用ずみ</div>`
    : `<button class="ticket" data-act="use_rest_ticket">🎫 おやすみ券を使う（連続記録を守る・月1回）</button>`;

  const notif = `<button class="btn-outline" data-act="notif_request">🔔 通知を許可する</button>` +
    `<div class="hint">iPhoneは「ホーム画面に追加」した後だけ通知できます。` +
    `決まった時間の通知は送りません。開けば一番上に“今やること”が出ます。</div>`;

  return `<div class="screen settings">` +
    `<div class="list-head"><h2>⚙️ 設定</h2></div>` +
    `<div class="section-title">なりたい自分（原則11）</div>` +
    `<div class="id-minis">${idcards}</div>` +
    `<div class="section-title">習慣</div>` +
    `<button class="btn-outline" data-act="go:habits">習慣を管理する</button>` +
    `<div class="section-title">今日がしんどい時（原則9）</div>${ticket}` +
    `<div class="section-title">通知</div>${notif}` +
    `<div class="section-title">データ（端末内だけに保存）</div>` +
    `<button class="btn-outline" data-act="export">バックアップを書き出す</button>` +
    `<button class="btn-outline" data-act="import">バックアップを読み込む</button>` +
    `<button class="btn-danger" data-act="reset">すべて初期化する</button>` +
    `<div class="hint">アカウント不要。データはこの端末の中だけに保存されます。</div>` +
    `<div class="footer-note">くらしの仕組み化 v1 ・ 意志力ゼロ設計</div>` +
    `</div>` + tabbar("settings");
}

/* ====================== イベント処理（クリック委譲） ====================== */

function newId(prefix) { return prefix + Date.now() + Math.floor(Math.random() * 90 + 10); }
function getVal(id) { const el = document.getElementById(id); return el ? el.value : ""; }

function onClick(evt) {
  let node = evt.target, act = null;
  while (node && node !== document) {
    if (node.getAttribute) { act = node.getAttribute("data-act"); if (act) break; }
    node = node.parentElement;
  }
  if (!act) return;
  const idx = act.indexOf(":");
  const cmd = idx >= 0 ? act.slice(0, idx) : act;
  const arg = idx >= 0 ? act.slice(idx + 1) : "";

  switch (cmd) {
    case "go": nav.screen = arg; render(); return;
    case "go_home_from_onb": state.onboarded = true; saveState(); nav.screen = "home"; render(); return;

    case "onb_identity": state.identity = arg; saveState(); render(); return;
    case "onb_next": nav.onbStep = (nav.onbStep || 1) + 1; render(); return;
    case "onb_finish": state.onboarded = true; saveState(); nav.screen = "home"; render(); return;

    case "trigger": startFlow(arg); return;
    case "toggle_min":
      state.minModeDate = minModeOn() ? "" : todayISO(); saveState(); render(); return;
    case "dismiss_fresh": state.seenFreshDate = todayISO(); saveState(); render(); return;

    case "flow_done": case "flow_min_once": case "flow_normal_once": {
      const h = currentFlowHabit();
      if (h) {
        if (cmd === "flow_min_once") state.minModeDate = todayISO();  // 最小に切替
        completeHabit(h);            // 演出後に render される
        flow.idx++;
        if (!currentFlowHabit()) flow.active = false;
      }
      return;
    }
    case "flow_skip":
      flow.idx++; if (!currentFlowHabit()) flow.active = false; render(); return;
    case "flow_close": flow.active = false; render(); return;

    case "habit_toggle": { const h = findHabit(arg); if (h) { h.enabled = !h.enabled; saveState(); } render(); return; }
    case "habit_delete": state.habits = state.habits.filter(x => x.id !== arg); saveState(); render(); return;
    case "add_habit_save": addHabitFromForm(); return;

    case "goal_save": goalSaveFromForm(); return;
    case "goal_delete": state.goals = state.goals.filter(g => g.id !== arg); saveState(); render(); return;
    case "goal_to_habit": convertGoalToHabit(arg); return;

    case "identity_change": state.identity = arg; saveState(); render(); return;
    case "use_rest_ticket": useRestTicket(); return;
    case "notif_request": requestNotification(); return;
    case "export": doExport(); return;
    case "import": doImport(); return;
    case "reset": doReset(); return;
  }
}

function addHabitFromForm() {
  let trg = getVal("f_trigger");
  const action = getVal("f_action").trim();
  let amin = getVal("f_min").trim();
  const cat = getVal("f_cat");
  const reward = getVal("f_reward").trim();

  const custom = getVal("f_trigger_custom").trim();
  if (custom) {
    trg = custom;
    const emoji = getVal("f_trigger_emoji") || "⭐";
    const known = new Set((state.customTriggers || []).map(c => c.name));
    if (!(trg in TRIGGER_EMOJI) && !known.has(trg)) {
      (state.customTriggers = state.customTriggers || []).push({ name: trg, emoji });
    }
  }
  if (!action) { window.alert("「何をする？」を入れてください（短くてOK）"); return; }
  if (!amin) amin = action;
  state.habits.push({
    id: newId("h"), trigger: trg, action, actionMin: amin,
    category: cat, reward, enabled: true, streak: 0, lastDone: "",
  });
  saveState();
  nav.screen = "habits"; render();
}

function goalSaveFromForm() {
  const text = getVal("g_text").trim();
  if (!text) { window.alert("やりたいことを入れてください"); return; }
  state.goals.push({
    id: newId("g"), when: getVal("g_when"), text,
    firstAction: getVal("g_first").trim(), converted: false,
  });
  saveState();
  nav.screen = "goals"; render();
}

function convertGoalToHabit(gid) {
  const g = state.goals.find(x => x.id === gid);
  if (!g) return;
  const first = g.firstAction || g.text;
  state.habits.push({
    id: newId("h"), trigger: "起きたら", action: first, actionMin: first,
    category: "勉強・自己投資", reward: "", enabled: true, streak: 0, lastDone: "",
  });
  g.converted = true;
  saveState();
  window.alert(`「${first}」を習慣にしました。ホームの『起きたら』に入っています。`);
  nav.screen = "habits"; render();
}

function useRestTicket() {
  const ym = todayISO().slice(0, 7);
  if (state.restTicketsMonth === ym) {
    window.alert("今月のおやすみ券はもう使いました。来月また使えます。"); return;
  }
  const t = todayISO();
  if (!state.restDays.includes(t)) state.restDays.push(t);
  state.restTicketsMonth = ym;
  saveState();
  window.alert("🎫 今日はおやすみ。連続記録は守られます。ゆっくり休んでくださいね。");
  render();
}

function requestNotification() {
  try {
    if (!("Notification" in window)) {
      window.alert("この端末/ブラウザでは通知が使えません。開いて使う形でも十分機能します。");
      return;
    }
    Notification.requestPermission().then(perm => {
      if (perm === "granted") {
        try { new Notification("くらしの仕組み化", { body: "通知の準備ができました🌱" }); } catch (e) {}
        window.alert("通知を許可しました。");
      } else {
        window.alert("通知はオフのままです。開けば“今やること”が一番上に出るので大丈夫です。");
      }
    });
  } catch (e) {
    window.alert("この端末/ブラウザでは通知が使えません。開いて使う形でも十分機能します。");
  }
}

function doExport() {
  const data = JSON.stringify(state, null, 2);
  const blob = new Blob([data], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url; a.download = "kurashi-backup.json";
  document.body.appendChild(a); a.click(); document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

function doImport() {
  const inp = document.createElement("input");
  inp.type = "file"; inp.accept = "application/json,.json";
  inp.addEventListener("change", evt => {
    const f = evt.target.files[0];
    if (!f) return;
    const reader = new FileReader();
    reader.onload = () => {
      try {
        const s = JSON.parse(String(reader.result));
        state = s;
        const d = defaultState();
        for (const k in d) { if (!(k in state)) state[k] = d[k]; }
        saveState();
        window.alert("読み込みました。");
        nav.screen = "home"; render();
      } catch (e) { window.alert("ファイルを読み込めませんでした。"); }
    };
    reader.readAsText(f);
  });
  inp.click();
}

function doReset() {
  if (window.confirm("すべての記録を消して最初からにします。よろしいですか？")) {
    localStorage.removeItem(STORAGE_KEY);
    state = defaultState();
    saveState();
    nav = { screen: "home", onbStep: 1 };
    render();
  }
}

/* ====================== 起動 ====================== */

function boot() {
  document.getElementById("app").addEventListener("click", onClick);
  const ld = document.getElementById("loading");
  if (ld) ld.style.display = "none";
  render();
}

boot();
