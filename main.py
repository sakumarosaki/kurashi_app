# -*- coding: utf-8 -*-
"""
くらしの仕組み化アプリ（本体）
================================
設計思想：意志力を1ミリも要求しない。行動科学の12原則をUIの形に落とし込む。

【行動科学の原則 → 実装箇所 対応表】（詳細はREADMEにも記載）
 1. 摩擦の最小化        : 起動直後ホーム最上部に「今やること」/ 大トリガーボタン / 操作はタップ中心
 2. 実行意図(if-then)  : 習慣は必ず「〜したら→〜する」。追加も穴埋めフォーム（build_add_habit）
 3. 習慣スタッキング     : TRIGGER_PRESETS（歯を磨いたら 等）を候補で提供
 4. 2分ルール&最小モード : 全習慣に action_min。ホームの「最小モード」トグルで一括最小化。満額カウント
 5. 現在バイアス(誘惑束) : 達成即演出（fx_celebrate）＋褒め言葉＋任意のご褒美ルール(reward)
 6. 変動報酬            : complete_habit 内でランダムにボーナス点・レア褒め・称号
 7. 損失回避&保有効果    : ストリークを「育つ植物」で可視化（plant_for / build_home のガーデン）
 8. 進捗の付与効果       : 初期ポイント20＝レベルゲージ20%開始 / スタンプ2個押済で開始
 9. フレッシュスタート    : 途切れても責めない文言。おやすみ券。週初/月初の再開提案（fresh_start_banner）
10. デフォルト効果       : PRESET_HABITS を有効化済みで同梱。設定を開かなくても完結
11. アイデンティティ     : オンボで「なりたい自分」選択。達成時に「〜な人の行動を1つ積みました」
12. ツァイガルニク       : ホームに「あと〇つで今日コンプリート」を控えめに表示
"""

import json
import random
from datetime import date, timedelta

from js import document, window, localStorage, Notification, Object
from pyodide.ffi import create_proxy, to_js


def js_obj(d):
    """Python dict → JS オブジェクト（{key: value} 形式）に変換"""
    return to_js(d, dict_converter=Object.fromEntries)

STORAGE_KEY = "kurashi_state_v1"

# ============================================================
# マスターデータ（デフォルト／プリセット）
# ============================================================

# なりたい自分（原則11）
IDENTITIES = [
    {"id": "morning",  "label": "朝に余裕のある人", "emoji": "🌅"},
    {"id": "tidy",     "label": "ちゃんとした部屋で暮らす人", "emoji": "🧹"},
    {"id": "learner",  "label": "学び続ける人", "emoji": "📚"},
    {"id": "balanced", "label": "心と体を整える人", "emoji": "🧘"},
]

# if-then の「〜したら」トリガー候補（原則3：習慣スタッキング）
TRIGGER_PRESETS = [
    "帰宅して靴を脱いだら",
    "歯を磨いたら",
    "起きたら",
    "寝る前に",
    "お風呂から出たら",
    "コーヒー/お茶を淹れたら",
    "電子レンジを回している間に",
    "コンビニに寄る前に",
]

# プリセット習慣（原則10：デフォルトで有効。原則4：最小版必須。原則8：streakを少し進めて開始）
PRESET_HABITS = [
    {"trigger": "帰宅して靴を脱いだら", "action": "床の物を1つだけ定位置に戻す",
     "action_min": "床の物を1つ拾って置くだけ", "category": "掃除・身支度", "streak": 2},
    {"trigger": "歯を磨いたら", "action": "参考書を開いて1行だけ読む",
     "action_min": "参考書を開くだけ", "category": "勉強・自己投資", "streak": 3},
    {"trigger": "寝る前に", "action": "明日の服を椅子にかける",
     "action_min": "明日着る上着1枚だけ出す", "category": "掃除・身支度", "streak": 1},
    {"trigger": "起きたら", "action": "カーテンを開けて水を1杯飲む",
     "action_min": "カーテンを開けるだけ", "category": "掃除・身支度", "streak": 2},
    {"trigger": "コーヒー/お茶を淹れたら", "action": "今日やる小さなことを1つ声に出す",
     "action_min": "深呼吸を1回する", "category": "勉強・自己投資", "streak": 0},
]

CATEGORY_EMOJI = {"勉強・自己投資": "📚", "掃除・身支度": "🧹", "その他": "⭐"}

TRIGGER_EMOJI = {
    "帰宅して靴を脱いだら": "🏠", "歯を磨いたら": "🪥", "起きたら": "🌅",
    "寝る前に": "🌙", "お風呂から出たら": "🛁", "コーヒー/お茶を淹れたら": "☕",
    "電子レンジを回している間に": "🍱", "コンビニに寄る前に": "🏪",
}

# 自分できっかけを作る時に選べる絵文字（タップ／選択で。原則1：入力の摩擦を減らす）
EMOJI_CHOICES = ["⏰", "🍽️", "🚿", "👕", "🧴", "🛏️", "🚪", "🪑",
                 "📱", "🧺", "🍵", "🐟", "💊", "🚶", "🧻", "✏️", "⭐"]


def trigger_emoji(trg):
    """きっかけの絵文字を返す。プリセット → 自分で追加したもの → 既定(•) の順に探す。"""
    if trg in TRIGGER_EMOJI:
        return TRIGGER_EMOJI[trg]
    for c in state.get("custom_triggers", []):
        if c.get("name") == trg:
            return c.get("emoji", "•")
    return "•"


def all_triggers():
    """選択肢に出すきっかけ一覧：プリセット＋自分で追加したもの（重複なし）"""
    result = list(TRIGGER_PRESETS)
    for c in state.get("custom_triggers", []):
        if c.get("name") and c["name"] not in result:
            result.append(c["name"])
    return result

# 褒め言葉（原則5）。rare は変動報酬（原則6）
PRAISE = ["ナイス！", "いいね、積み上がった", "その1つが効く", "よくやった！",
          "今日のあなた、動けてる", "小さな一歩、確かな一歩", "えらい！", "その調子"]
PRAISE_RARE = ["✨レア✨ 完璧なリズム！", "🎉神ってる！最高の流れ", "💎今日のあなたは冴えてる",
               "🌟今のは効いた、間違いなく"]

# レアな称号（原則6：変動報酬で低確率ドロップ）
RARE_BADGES = ["早起きの妖精", "静けさの主", "コツコツの化身", "流れをつかむ者", "小さな巨人"]


# ============================================================
# 状態（localStorage）
# ============================================================

def today_iso():
    return date.today().isoformat()


def default_state():
    habits = []
    for i, h in enumerate(PRESET_HABITS):
        habits.append({
            "id": "p%d" % i,
            "trigger": h["trigger"],
            "action": h["action"],
            "action_min": h["action_min"],
            "category": h["category"],
            "reward": "",
            "enabled": True,
            "streak": h["streak"],           # 原則8：ゼロからでなく少し進んだ状態
            "last_done": "",
        })
    return {
        "version": 1,
        "onboarded": False,
        "identity": "",
        "habits": habits,
        "custom_triggers": [],  # 自分で追加したきっかけ [{"name":..,"emoji":..}]（原則3）
        "points": 20,          # 原則8：レベルゲージ20%から開始
        "stamps": 2,           # 原則8：スタンプカード2個押済で開始
        "badges": [],
        "min_mode_date": "",   # この日付が今日なら最小モードON（原則4）
        "rest_tickets_month": "",   # "YYYY-MM"：今月分を使ったか記録
        "rest_days": [],       # おやすみ券を使った日（ストリーク保護／原則9）
        "goals": [],           # いつかリスト（機能4）
        "done_log": {},        # {"YYYY-MM-DD": 完了数}（原則3のヒートマップ・加点式）
        "seen_fresh_date": "", # フレッシュスタート案内を出した日
    }


def load_state():
    raw = localStorage.getItem(STORAGE_KEY)
    if not raw:
        return default_state()
    try:
        s = json.loads(raw)
        # 後方互換：足りないキーを補完
        d = default_state()
        for k, v in d.items():
            if k not in s:
                s[k] = v
        return s
    except Exception:
        return default_state()


def save_state():
    localStorage.setItem(STORAGE_KEY, json.dumps(state))


state = load_state()

# 画面遷移用（保存しない一時状態）
nav = {"screen": "home"}
flow = {"active": False, "trigger": "", "queue": [], "idx": 0}


# ============================================================
# ロジック・ヘルパー
# ============================================================

def min_mode_on():
    return state.get("min_mode_date") == today_iso()


def habit_done_today(h):
    return h.get("last_done") == today_iso()


def enabled_habits():
    return [h for h in state["habits"] if h.get("enabled")]


def habits_for_trigger(trg):
    return [h for h in enabled_habits() if h["trigger"] == trg]


def open_triggers():
    """今日まだ未完了の習慣が残っているトリガーを、順序を保って返す"""
    seen = []
    for h in enabled_habits():
        if not habit_done_today(h) and h["trigger"] not in seen:
            seen.append(h["trigger"])
    return seen


def total_today():
    return len(enabled_habits())


def done_today_count():
    return len([h for h in enabled_habits() if habit_done_today(h)])


def level_info():
    pts = state["points"]
    level = pts // 100 + 1
    in_level = pts % 100
    return level, in_level  # in_level は 0..99（=ゲージ%）


def global_streak():
    """1日1つ以上やった日 or おやすみ券の日を、今日/昨日から遡って連続カウント（原則7）"""
    log = state["done_log"]
    rest = set(state["rest_days"])
    t = date.today()
    y = t - timedelta(days=1)
    ti, yi = t.isoformat(), y.isoformat()
    if ti not in log and ti not in rest and yi not in log and yi not in rest:
        return 0
    cur = t if (ti in log or ti in rest) else y
    n = 0
    while True:
        ci = cur.isoformat()
        if ci in log or ci in rest:
            n += 1
            cur -= timedelta(days=1)
        else:
            break
    return n


def plant_for(streak):
    """ストリークを育つ植物で表現（原則7）。枯れ演出はしない。"""
    if streak <= 0:
        return "🌱", "これから育てましょう"
    if streak <= 2:
        return "🌱", "芽が出ました"
    if streak <= 5:
        return "🌿", "すくすく育っています"
    if streak <= 10:
        return "🪴", "しっかり根づいてきました"
    if streak <= 20:
        return "🌳", "立派に育っています"
    return "🌳✨", "見事な大樹です"


# ============================================================
# 達成処理（原則5・6・8・11）
# ============================================================

def complete_habit(h, minimal):
    if habit_done_today(h):
        return  # 二重加算防止
    t = today_iso()
    y = (date.today() - timedelta(days=1)).isoformat()

    # ストリーク更新（責めない。途切れても1から積み直すだけ）
    if h.get("last_done") == y:
        h["streak"] = h.get("streak", 0) + 1
    else:
        h["streak"] = 1
    h["last_done"] = t

    # 完了ログ（ヒートマップ用・加点式）
    state["done_log"][t] = state["done_log"].get(t, 0) + 1

    # 基本ポイント（最小でも満額：原則4）
    gained = 10
    messages = []
    base_msg = random.choice(PRAISE)

    # 変動報酬（原則6）
    roll = random.random()
    if roll < 0.05:
        badge = random.choice(RARE_BADGES)
        if badge not in state["badges"]:
            state["badges"].append(badge)
        bonus = 30
        gained += bonus
        messages.append("🏅 称号「%s」を獲得！ +%dpt" % (badge, bonus))
        base_msg = random.choice(PRAISE_RARE)
    elif roll < 0.20:
        bonus = random.choice([10, 15, 20])
        gained += bonus
        messages.append("🎁 ボーナス +%dpt！" % bonus)
        if random.random() < 0.5:
            base_msg = random.choice(PRAISE_RARE)

    state["points"] += gained

    # スタンプカード（原則8：2個押済で開始、10個でリセット＆ボーナス）
    state["stamps"] += 1
    if state["stamps"] >= 10:
        state["stamps"] = 0
        state["points"] += 50
        messages.append("⭐ スタンプ10個コンプ！ +50pt")

    # アイデンティティへの投票（原則11）
    idlabel = identity_label()
    if idlabel:
        messages.insert(0, "今日のあなたは『%s』の行動を1つ積みました" % idlabel)

    # ご褒美ルール（原則5：誘惑バンドル）
    if h.get("reward"):
        messages.append("🎬 ご褒美OK：%s" % h["reward"])

    save_state()
    fx_celebrate(base_msg, messages)


def identity_label():
    for i in IDENTITIES:
        if i["id"] == state.get("identity"):
            return i["label"]
    return ""


# ============================================================
# 達成演出（原則5：即時の快）
# ============================================================

def fx_celebrate(headline, extra_lines):
    fx = document.getElementById("fx")
    lines_html = "".join("<div class='fx-line'>%s</div>" % esc(m) for m in extra_lines)
    confetti = "".join(
        "<span class='confetti' style='left:%d%%;animation-delay:%dms;background:%s'></span>"
        % (random.randint(2, 96), random.randint(0, 400),
           random.choice(["#5faf7d", "#ffd166", "#ef8354", "#6aa6ff", "#c58bff"]))
        for _ in range(18)
    )
    fx.innerHTML = (
        "<div class='fx-overlay'>"
        "<div class='fx-confetti'>%s</div>"
        "<div class='fx-card'>"
        "<div class='fx-emoji'>🎉</div>"
        "<div class='fx-headline'>%s</div>"
        "%s"
        "</div></div>"
    ) % (confetti, esc(headline), lines_html)

    def clear(evt=None):
        fx.innerHTML = ""
        render()
    # タップでもタイマーでも閉じる
    fx.querySelector(".fx-overlay").addEventListener("click", create_proxy(clear))
    window.setTimeout(create_proxy(lambda *a: clear()), 1600)


# ============================================================
# 描画ユーティリティ
# ============================================================

def esc(s):
    s = str(s)
    return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
             .replace('"', "&quot;").replace("'", "&#39;"))


def render():
    scr = nav["screen"]
    if not state.get("onboarded"):
        html = build_onboarding()
    elif flow["active"]:
        html = build_flow()
    elif scr == "home":
        html = build_home()
    elif scr == "habits":
        html = build_habits()
    elif scr == "add":
        html = build_add_habit()
    elif scr == "goals":
        html = build_goals()
    elif scr == "goal_add":
        html = build_goal_add()
    elif scr == "stats":
        html = build_stats()
    elif scr == "settings":
        html = build_settings()
    else:
        html = build_home()
    document.getElementById("app").innerHTML = html


def tabbar(active):
    tabs = [("home", "🏠", "ホーム"), ("stats", "📅", "記録"),
            ("goals", "🎯", "目標"), ("settings", "⚙️", "設定")]
    items = ""
    for key, icon, label in tabs:
        cls = "tab active" if key == active else "tab"
        items += ("<button class='%s' data-act='go:%s'>"
                  "<div class='tab-ic'>%s</div><div class='tab-lb'>%s</div></button>"
                  ) % (cls, key, icon, label)
    return "<nav class='tabbar'>%s</nav>" % items


# ============================================================
# 画面：オンボーディング（機能5 / 原則10・11）
# ============================================================

def build_onboarding():
    step = nav.get("onb_step", 1)
    if step == 1:
        cards = ""
        for i in IDENTITIES:
            sel = "sel" if state.get("identity") == i["id"] else ""
            cards += ("<button class='id-card %s' data-act='onb_identity:%s'>"
                      "<div class='id-emoji'>%s</div><div class='id-label'>%s</div></button>"
                      ) % (sel, i["id"], i["emoji"], esc(i["label"]))
        nextbtn = ""
        if state.get("identity"):
            nextbtn = "<button class='btn-primary big' data-act='onb_next'>次へ</button>"
        return (
            "<div class='screen onb'>"
            "<div class='onb-step'>1 / 3</div>"
            "<h1 class='onb-h'>どんな自分になりたい？</h1>"
            "<p class='onb-sub'>1つだけ選んでください。あとで変えられます。</p>"
            "<div class='id-grid'>%s</div>"
            "%s</div>"
        ) % (cards, nextbtn)

    if step == 2:
        rows = ""
        for h in state["habits"]:
            rows += ("<div class='preset-row'>"
                     "<span class='pill'>%s %s</span>"
                     "<span class='arrow'>→</span>"
                     "<span class='preset-action'>%s</span></div>"
                     ) % (trigger_emoji(h["trigger"]), esc(h["trigger"]), esc(h["action"]))
        return (
            "<div class='screen onb'>"
            "<div class='onb-step'>2 / 3</div>"
            "<h1 class='onb-h'>この習慣で始めます</h1>"
            "<p class='onb-sub'>ぜんぶ2分以内で終わる小さなことだけ。<br>今は何も考えず、このままでOK。</p>"
            "<div class='preset-list'>%s</div>"
            "<button class='btn-primary big' data-act='onb_next'>このままでOK</button>"
            "<button class='btn-ghost' data-act='go_home_from_onb'>あとで習慣は調整する</button>"
            "</div>"
        ) % rows

    # step 3
    return (
        "<div class='screen onb center'>"
        "<div class='onb-step'>3 / 3</div>"
        "<div class='big-emoji'>🌱</div>"
        "<h1 class='onb-h'>準備できました</h1>"
        "<p class='onb-sub'>むずかしいことは何もありません。<br>アプリを開いて、出てきた1つをタップするだけ。</p>"
        "<button class='btn-primary big' data-act='onb_finish'>はじめる</button>"
        "</div>"
    )


# ============================================================
# 画面：ホーム（コア / 原則1・4・7・11・12）
# ============================================================

def build_home():
    triggers = open_triggers()
    done = done_today_count()
    total = total_today()

    # 最上部：今やること（原則1：起動直後に迷いゼロ）
    if triggers:
        top_trg = triggers[0]
        n_here = len([h for h in habits_for_trigger(top_trg) if not habit_done_today(h)])
        now_card = (
            "<div class='now-card' data-act='trigger:%s'>"
            "<div class='now-label'>いま、これだけ</div>"
            "<div class='now-trigger'>%s %s</div>"
            "<div class='now-hint'>タップして始める（残り%d）</div>"
            "</div>"
        ) % (esc(top_trg), trigger_emoji(top_trg), esc(top_trg), n_here)
    else:
        now_card = (
            "<div class='now-card done'>"
            "<div class='now-emoji'>🎉</div>"
            "<div class='now-trigger'>今日のぶん、完了！</div>"
            "<div class='now-hint'>お疲れさまでした</div>"
            "</div>"
        )

    # 最小モードトグル（原則4）
    mm = min_mode_on()
    min_toggle = (
        "<button class='min-toggle %s' data-act='toggle_min'>"
        "%s 最小モード %s</button>"
    ) % ("on" if mm else "", "🌙" if mm else "🔋", "ON（今日は最小でOK）" if mm else "OFF")

    # ツァイガルニク（原則12）：あと〇つで今日コンプリート（控えめに）
    zeigarnik = ""
    remaining = total - done
    if 0 < remaining <= 2 and total > 0:
        zeigarnik = "<div class='zeigarnik'>あと%dつで今日コンプリート</div>" % remaining

    # 他のトリガーボタン（原則1・3：大ボタン）
    other_btns = ""
    for trg in triggers[1:]:
        n_here = len([h for h in habits_for_trigger(trg) if not habit_done_today(h)])
        other_btns += (
            "<button class='trig-btn' data-act='trigger:%s'>"
            "<span class='trig-emoji'>%s</span>"
            "<span class='trig-text'>%s</span>"
            "<span class='trig-badge'>%d</span></button>"
        ) % (esc(trg), trigger_emoji(trg), esc(trg), n_here)
    if other_btns:
        other_btns = "<div class='section-title'>ほかのきっかけ</div><div class='trig-list'>%s</div>" % other_btns

    # 育つガーデン（原則7）＋レベル（原則8）
    streak = global_streak()
    plant, plant_msg = plant_for(streak)
    level, in_level = level_info()
    garden = (
        "<div class='garden'>"
        "<div class='garden-plant'>%s</div>"
        "<div class='garden-info'>"
        "<div class='garden-streak'>連続 %d日</div>"
        "<div class='garden-msg'>%s</div>"
        "</div></div>"
    ) % (plant, streak, esc(plant_msg))
    levelbar = (
        "<div class='levelbar'>"
        "<div class='level-top'><span>Lv.%d</span><span>%dpt</span></div>"
        "<div class='bar'><div class='bar-fill' style='width:%d%%'></div></div>"
        "</div>"
    ) % (level, state["points"], in_level)

    fresh = fresh_start_banner()

    return (
        "<div class='screen home'>"
        "<div class='home-head'>"
        "<div class='greeting'>%s</div>"
        "%s</div>"
        "%s"     # fresh start
        "%s"     # now card
        "%s"     # zeigarnik
        "%s"     # min toggle
        "%s"     # garden
        "%s"     # levelbar
        "%s"     # other triggers
        "</div>%s"
    ) % (greeting(), badge_chip(), fresh, now_card, zeigarnik,
         min_toggle, garden, levelbar, other_btns, tabbar("home"))


def greeting():
    idl = identity_label()
    if idl:
        return "『%s』へ、一歩ずつ" % esc(idl)
    return "おかえりなさい"


def badge_chip():
    n = len(state["badges"])
    if n == 0:
        return ""
    return "<button class='badge-chip' data-act='go:settings'>🏅 %d</button>" % n


def fresh_start_banner():
    """原則9：責めない＋節目での再開提案。'サボり'という語は一切使わない。"""
    streak = global_streak()
    log = state["done_log"]
    t = date.today()
    # 途切れているが履歴はある → セルフコンパッション
    if streak == 0 and log:
        if state.get("seen_fresh_date") != today_iso():
            return (
                "<div class='fresh'>"
                "<div class='fresh-title'>おかえりなさい 🌱</div>"
                "<div class='fresh-body'>少し休憩していましたね。責める必要はありません。"
                "<b>今日が新しいスタート日</b>です。まずは最小の1つから。</div>"
                "<button class='btn-ghost sm' data-act='dismiss_fresh'>わかった</button>"
                "</div>"
            )
    # 節目（週初＝月曜 / 月初＝1日）→ 再開のきっかけ提案
    weekday = t.weekday()  # 月=0
    if weekday == 0 or t.day == 1:
        label = "新しい週" if weekday == 0 else "新しい月"
        return (
            "<div class='fresh soft'>"
            "<div class='fresh-body'>今日は<b>%sの始まり</b>。仕切り直しにちょうどいい日です。</div>"
            "</div>"
        ) % label
    return ""


# ============================================================
# 画面：実行フロー（原則1・4：1つずつ・ワンタップ）
# ============================================================

def start_flow(trigger):
    q = [h["id"] for h in habits_for_trigger(trigger) if not habit_done_today(h)]
    if not q:
        return
    flow["active"] = True
    flow["trigger"] = trigger
    flow["queue"] = q
    flow["idx"] = 0
    render()


def current_flow_habit():
    while flow["idx"] < len(flow["queue"]):
        hid = flow["queue"][flow["idx"]]
        h = find_habit(hid)
        if h and not habit_done_today(h):
            return h
        flow["idx"] += 1
    return None


def build_flow():
    h = current_flow_habit()
    if h is None:
        flow["active"] = False
        return build_home()

    mm = min_mode_on()
    action_text = h["action_min"] if mm else h["action"]
    pos = flow["idx"] + 1
    total = len(flow["queue"])

    # メモ欄（任意・1行 / 原則1：任意なので迷わせない）
    memo = ("<input id='memo' class='memo' type='text' inputmode='text' "
            "placeholder='ひとことメモ（任意・書かなくてOK）' />")

    # 最小/通常の切替（原則4）
    if mm:
        mode_note = "<div class='flow-mode'>🌙 最小モード：これだけで満額です</div>"
        alt_btn = ("<button class='btn-ghost sm' data-act='flow_normal_once'>"
                   "今日は通常版でやる</button>")
    else:
        mode_note = ""
        alt_btn = ("<button class='btn-ghost sm' data-act='flow_min_once'>"
                   "しんどい…最小版に切替（2分以内）</button>")

    reward_hint = ""
    if h.get("reward"):
        reward_hint = "<div class='flow-reward'>🎁 できたらご褒美：%s</div>" % esc(h["reward"])

    return (
        "<div class='screen flow'>"
        "<button class='flow-close' data-act='flow_close'>✕</button>"
        "<div class='flow-progress'>%d / %d</div>"
        "<div class='flow-trigger'>%s %s</div>"
        "<div class='flow-arrow'>↓</div>"
        "<div class='flow-action'>%s</div>"
        "%s%s"
        "%s"
        "<button class='btn-primary huge' data-act='flow_done'>できた！</button>"
        "%s"
        "<button class='btn-ghost sm' data-act='flow_skip'>今はしない（次へ）</button>"
        "</div>"
    ) % (pos, total, trigger_emoji(flow["trigger"]), esc(flow["trigger"]),
         esc(action_text), mode_note, reward_hint, memo, alt_btn)


# ============================================================
# 画面：習慣の管理（機能1・2 / 原則2）
# ============================================================

def build_habits():
    rows = ""
    for h in state["habits"]:
        on = "on" if h.get("enabled") else ""
        done = "✅" if habit_done_today(h) else ""
        rows += (
            "<div class='habit-row'>"
            "<div class='habit-main'>"
            "<div class='habit-if'>%s %s</div>"
            "<div class='habit-then'>→ %s</div>"
            "<div class='habit-min'>最小：%s</div>"
            "<div class='habit-meta'>%s ・ 連続%d日 %s</div>"
            "</div>"
            "<div class='habit-actions'>"
            "<button class='sw %s' data-act='habit_toggle:%s'></button>"
            "<button class='del' data-act='habit_delete:%s'>削除</button>"
            "</div></div>"
        ) % (trigger_emoji(h["trigger"]), esc(h["trigger"]), esc(h["action"]),
             esc(h["action_min"]), esc(h.get("category", "その他")),
             h.get("streak", 0), done, on, h["id"], h["id"])

    return (
        "<div class='screen list'>"
        "<div class='list-head'><button class='back' data-act='go:settings'>‹ 戻る</button>"
        "<h2>習慣の管理</h2></div>"
        "<button class='btn-primary' data-act='go:add'>＋ 習慣を追加</button>"
        "<div class='hint'>スイッチでON/OFF。全部そのままでも大丈夫です。</div>"
        "%s</div>%s"
    ) % (rows, tabbar("settings"))


def build_add_habit():
    # 原則2：if-then 穴埋め。トリガーはタップ選択（原則1・3）
    trig_opts = "".join("<option value='%s'>%s %s</option>" %
                        (esc(t), trigger_emoji(t), esc(t)) for t in all_triggers())
    cat_opts = "".join("<option value='%s'>%s %s</option>" %
                       (esc(c), e, esc(c)) for c, e in CATEGORY_EMOJI.items())
    emoji_opts = "".join("<option value='%s'>%s</option>" % (e, e) for e in EMOJI_CHOICES)
    return (
        "<div class='screen form'>"
        "<div class='list-head'><button class='back' data-act='go:habits'>‹ 戻る</button>"
        "<h2>習慣を追加</h2></div>"
        "<div class='ff'>"
        "<label>① どの行動の“ついで”に？（〜したら）</label>"
        "<select id='f_trigger' class='inp'>%s</select>"

        "<div class='custom-trigger'>"
        "<label>リストにない時：自分できっかけを作る（任意）</label>"
        "<div class='ct-row'>"
        "<select id='f_trigger_emoji' class='inp ct-emoji'>%s</select>"
        "<input id='f_trigger_custom' class='inp ct-text' type='text' "
        "placeholder='例：お皿を洗ったら' />"
        "</div>"
        "<div class='ct-hint'>ここに書くと、上のリストより優先されます。次回から候補に出ます。</div>"
        "</div>"

        "<label>② 何をする？（通常版）</label>"
        "<input id='f_action' class='inp' type='text' placeholder='例：参考書を1行読む' />"
        "<label>③ 疲れた日の最小版（2分以内・必須）</label>"
        "<input id='f_min' class='inp' type='text' placeholder='例：参考書を開くだけ' />"
        "<label>④ カテゴリ</label>"
        "<select id='f_cat' class='inp'>%s</select>"
        "<label>⑤ ご褒美ルール（任意）</label>"
        "<input id='f_reward' class='inp' type='text' placeholder='例：できたら好きな動画1本OK' />"
        "<button class='btn-primary big' data-act='add_habit_save'>この習慣を追加</button>"
        "</div></div>%s"
    ) % (trig_opts, emoji_opts, cat_opts, tabbar("settings"))


# ============================================================
# 画面：目標・いつかリスト（機能4 / 原則4・11）
# ============================================================

def build_goals():
    rows = ""
    if not state["goals"]:
        rows = "<div class='empty'>まだ目標はありません。<br>「いつかやりたい」を1つ置いてみましょう。</div>"
    for g in state["goals"]:
        converted = "✅ 習慣化ずみ" if g.get("converted") else ""
        conv_btn = ""
        if not g.get("converted"):
            conv_btn = ("<button class='btn-primary sm' data-act='goal_to_habit:%s'>"
                        "最初の2分を習慣にする</button>") % g["id"]
        rows += (
            "<div class='goal-row'>"
            "<div class='goal-when'>%s</div>"
            "<div class='goal-text'>%s</div>"
            "<div class='goal-first'>最初の2分：%s</div>"
            "<div class='goal-foot'>%s %s"
            "<button class='del' data-act='goal_delete:%s'>削除</button></div>"
            "</div>"
        ) % (esc(g.get("when", "いつか")), esc(g["text"]),
             esc(g.get("first_action", "（未設定）")), converted, conv_btn, g["id"])

    return (
        "<div class='screen list'>"
        "<div class='list-head'><h2>🎯 目標・いつかリスト</h2></div>"
        "<button class='btn-primary' data-act='go:goal_add'>＋ やりたいことを追加</button>"
        "<div class='hint'>大きな夢も、入口は「最初の2分」だけ。</div>"
        "%s</div>%s"
    ) % (rows, tabbar("goals"))


def build_goal_add():
    when_opts = "".join("<option value='%s'>%s</option>" % (w, w)
                        for w in ["今年中に", "いつか", "3か月以内に", "この夏に"])
    return (
        "<div class='screen form'>"
        "<div class='list-head'><button class='back' data-act='go:goals'>‹ 戻る</button>"
        "<h2>やりたいことを追加</h2></div>"
        "<div class='ff'>"
        "<label>① いつ？</label>"
        "<select id='g_when' class='inp'>%s</select>"
        "<label>② やりたいこと</label>"
        "<input id='g_text' class='inp' type='text' placeholder='例：簿記の勉強を始める' />"
        "<label>③ 最初の2分アクション（原則4）</label>"
        "<input id='g_first' class='inp' type='text' placeholder='例：テキストを1ページ開く' />"
        "<button class='btn-primary big' data-act='goal_save'>追加する</button>"
        "</div></div>%s"
    ) % (when_opts, tabbar("goals"))


# ============================================================
# 画面：記録（機能3：ヒートマップ / 原則3・7）
# ============================================================

def build_stats():
    # 直近5週間の加点式ヒートマップ（空白は色なし。赤や✕は出さない）
    log = state["done_log"]
    t = date.today()
    # 今週の月曜まで戻る
    start = t - timedelta(days=t.weekday() + 7 * 4)  # 5週分
    weeks = ""
    labels = ["月", "火", "水", "木", "金", "土", "日"]
    header = "".join("<div class='hm-lbl'>%s</div>" % l for l in labels)
    grid = ""
    d = start
    for _ in range(5 * 7):
        di = d.isoformat()
        cnt = log.get(di, 0)
        if di in state["rest_days"]:
            cls, title = "hm-cell rest", "%s おやすみ" % di
        elif cnt <= 0:
            cls, title = "hm-cell", di
        elif cnt == 1:
            cls, title = "hm-cell l1", "%s ・%d件" % (di, cnt)
        elif cnt == 2:
            cls, title = "hm-cell l2", "%s ・%d件" % (di, cnt)
        else:
            cls, title = "hm-cell l3", "%s ・%d件" % (di, cnt)
        future = " future" if d > t else ""
        grid += "<div class='%s%s' title='%s'></div>" % (cls, future, esc(title))
        d += timedelta(days=1)

    streak = global_streak()
    plant, plant_msg = plant_for(streak)
    level, in_level = level_info()
    total_done = sum(log.values())

    badges_html = ""
    if state["badges"]:
        chips = "".join("<span class='bchip'>🏅 %s</span>" % esc(b) for b in state["badges"])
        badges_html = "<div class='section-title'>称号</div><div class='badges'>%s</div>" % chips

    return (
        "<div class='screen stats'>"
        "<div class='list-head'><h2>📅 記録</h2></div>"
        "<div class='garden big'>"
        "<div class='garden-plant xl'>%s</div>"
        "<div class='garden-info'><div class='garden-streak'>連続 %d日</div>"
        "<div class='garden-msg'>%s</div></div></div>"
        "<div class='stat-cards'>"
        "<div class='stat-card'><div class='stat-num'>Lv.%d</div><div class='stat-lb'>レベル</div></div>"
        "<div class='stat-card'><div class='stat-num'>%d</div><div class='stat-lb'>ポイント</div></div>"
        "<div class='stat-card'><div class='stat-num'>%d</div><div class='stat-lb'>のべ達成</div></div>"
        "</div>"
        "<div class='section-title'>やった日だけ色づきます</div>"
        "<div class='heatmap'><div class='hm-head'>%s</div><div class='hm-grid'>%s</div></div>"
        "<div class='hm-legend'>少 <span class='hm-cell'></span><span class='hm-cell l1'></span>"
        "<span class='hm-cell l2'></span><span class='hm-cell l3'></span> 多</div>"
        "%s"
        "</div>%s"
    ) % (plant, streak, esc(plant_msg), level, state["points"], total_done,
         header, grid, badges_html, tabbar("stats"))


# ============================================================
# 画面：設定（原則10：開かなくても完結。ここは保険）
# ============================================================

def build_settings():
    idcards = ""
    for i in IDENTITIES:
        sel = "sel" if state.get("identity") == i["id"] else ""
        idcards += ("<button class='id-mini %s' data-act='identity_change:%s'>%s %s</button>"
                    ) % (sel, i["id"], i["emoji"], esc(i["label"]))

    # おやすみ券（原則9）
    ym = date.today().strftime("%Y-%m")
    ticket_used = state.get("rest_tickets_month") == ym
    if ticket_used:
        ticket = "<div class='ticket used'>🎫 今月のおやすみ券は使用ずみ</div>"
    else:
        ticket = ("<button class='ticket' data-act='use_rest_ticket'>"
                  "🎫 おやすみ券を使う（連続記録を守る・月1回）</button>")

    # 通知（ベストエフォート）
    notif = ("<button class='btn-outline' data-act='notif_request'>🔔 通知を許可する</button>"
             "<div class='hint'>iPhoneは「ホーム画面に追加」した後だけ通知できます。"
             "通知に頼らなくても、開けば一番上に“今やること”が出ます。</div>")

    return (
        "<div class='screen settings'>"
        "<div class='list-head'><h2>⚙️ 設定</h2></div>"

        "<div class='section-title'>なりたい自分（原則11）</div>"
        "<div class='id-minis'>%s</div>"

        "<div class='section-title'>習慣</div>"
        "<button class='btn-outline' data-act='go:habits'>習慣を管理する</button>"

        "<div class='section-title'>今日がしんどい時（原則9）</div>"
        "%s"

        "<div class='section-title'>通知</div>"
        "%s"

        "<div class='section-title'>データ（端末内だけに保存）</div>"
        "<button class='btn-outline' data-act='export'>バックアップを書き出す</button>"
        "<button class='btn-outline' data-act='import'>バックアップを読み込む</button>"
        "<button class='btn-danger' data-act='reset'>すべて初期化する</button>"
        "<div class='hint'>アカウント不要。データはこの端末の中だけに保存されます。</div>"

        "<div class='footer-note'>くらしの仕組み化 v1 ・ 意志力ゼロ設計</div>"
        "</div>%s"
    ) % (idcards, ticket, notif, tabbar("settings"))


# ============================================================
# イベント処理（クリック委譲：原則1＝タップ中心）
# ============================================================

def find_habit(hid):
    for h in state["habits"]:
        if h["id"] == hid:
            return h
    return None


def new_id(prefix):
    return prefix + str(int(window.Date.now())) + str(random.randint(10, 99))


def on_click(evt):
    target = evt.target
    node = target
    act = None
    while node and node != document:
        try:
            act = node.getAttribute("data-act")
        except Exception:
            act = None
        if act:
            break
        node = node.parentElement
    if not act:
        return

    if ":" in act:
        cmd, arg = act.split(":", 1)
    else:
        cmd, arg = act, ""

    # --- ナビゲーション ---
    if cmd == "go":
        nav["screen"] = arg
        render(); return
    if cmd == "go_home_from_onb":
        state["onboarded"] = True; save_state(); nav["screen"] = "home"; render(); return

    # --- オンボーディング ---
    if cmd == "onb_identity":
        state["identity"] = arg; save_state(); render(); return
    if cmd == "onb_next":
        nav["onb_step"] = nav.get("onb_step", 1) + 1; render(); return
    if cmd == "onb_finish":
        state["onboarded"] = True; save_state(); nav["screen"] = "home"; render(); return

    # --- ホーム ---
    if cmd == "trigger":
        start_flow(arg); return
    if cmd == "toggle_min":
        if min_mode_on():
            state["min_mode_date"] = ""
        else:
            state["min_mode_date"] = today_iso()
        save_state(); render(); return
    if cmd == "dismiss_fresh":
        state["seen_fresh_date"] = today_iso(); save_state(); render(); return

    # --- フロー（実行） ---
    if cmd == "flow_done":
        h = current_flow_habit()
        if h:
            complete_habit(h, minimal=min_mode_on())
            flow["idx"] += 1
            if current_flow_habit() is None:
                flow["active"] = False
        return  # complete_habit が演出後に render する
    if cmd == "flow_min_once":
        h = current_flow_habit()
        if h:
            complete_habit(h, minimal=True)
            flow["idx"] += 1
            if current_flow_habit() is None:
                flow["active"] = False
        return
    if cmd == "flow_normal_once":
        h = current_flow_habit()
        if h:
            complete_habit(h, minimal=False)
            flow["idx"] += 1
            if current_flow_habit() is None:
                flow["active"] = False
        return
    if cmd == "flow_skip":
        flow["idx"] += 1
        if current_flow_habit() is None:
            flow["active"] = False
        render(); return
    if cmd == "flow_close":
        flow["active"] = False; render(); return

    # --- 習慣管理 ---
    if cmd == "habit_toggle":
        h = find_habit(arg)
        if h:
            h["enabled"] = not h.get("enabled"); save_state()
        render(); return
    if cmd == "habit_delete":
        state["habits"] = [x for x in state["habits"] if x["id"] != arg]
        save_state(); render(); return
    if cmd == "add_habit_save":
        add_habit_from_form(); return

    # --- 目標 ---
    if cmd == "goal_save":
        goal_save_from_form(); return
    if cmd == "goal_delete":
        state["goals"] = [g for g in state["goals"] if g["id"] != arg]
        save_state(); render(); return
    if cmd == "goal_to_habit":
        convert_goal_to_habit(arg); return

    # --- 設定 ---
    if cmd == "identity_change":
        state["identity"] = arg; save_state(); render(); return
    if cmd == "use_rest_ticket":
        use_rest_ticket(); return
    if cmd == "notif_request":
        request_notification(); return
    if cmd == "export":
        do_export(); return
    if cmd == "import":
        do_import(); return
    if cmd == "reset":
        do_reset(); return


def add_habit_from_form():
    trg = get_val("f_trigger")
    action = get_val("f_action").strip()
    amin = get_val("f_min").strip()
    cat = get_val("f_cat")
    reward = get_val("f_reward").strip()

    # 自分で書いたきっかけがあれば、そちらを優先して使い、次回用に記憶する（原則3）
    custom = get_val("f_trigger_custom").strip()
    if custom:
        trg = custom
        emoji = get_val("f_trigger_emoji") or "⭐"
        known = {c.get("name") for c in state.get("custom_triggers", [])}
        if trg not in TRIGGER_EMOJI and trg not in known:
            state.setdefault("custom_triggers", []).append({"name": trg, "emoji": emoji})

    if not action:
        window.alert("「何をする？」を入れてください（短くてOK）")
        return
    if not amin:
        amin = action  # 最小版未入力なら通常版を最小版にも流用
    state["habits"].append({
        "id": new_id("h"), "trigger": trg, "action": action, "action_min": amin,
        "category": cat, "reward": reward, "enabled": True, "streak": 0, "last_done": "",
    })
    save_state()
    nav["screen"] = "habits"; render()


def goal_save_from_form():
    text = get_val("g_text").strip()
    if not text:
        window.alert("やりたいことを入れてください")
        return
    state["goals"].append({
        "id": new_id("g"), "when": get_val("g_when"), "text": text,
        "first_action": get_val("g_first").strip(), "converted": False,
    })
    save_state()
    nav["screen"] = "goals"; render()


def convert_goal_to_habit(gid):
    g = None
    for x in state["goals"]:
        if x["id"] == gid:
            g = x; break
    if not g:
        return
    first = g.get("first_action") or g["text"]
    state["habits"].append({
        "id": new_id("h"), "trigger": "起きたら",
        "action": first, "action_min": first,
        "category": "勉強・自己投資", "reward": "", "enabled": True,
        "streak": 0, "last_done": "",
    })
    g["converted"] = True
    save_state()
    window.alert("「%s」を習慣にしました。ホームの『起きたら』に入っています。" % first)
    nav["screen"] = "habits"; render()


def use_rest_ticket():
    ym = date.today().strftime("%Y-%m")
    if state.get("rest_tickets_month") == ym:
        window.alert("今月のおやすみ券はもう使いました。来月また使えます。")
        return
    t = today_iso()
    if t not in state["rest_days"]:
        state["rest_days"].append(t)
    state["rest_tickets_month"] = ym
    save_state()
    window.alert("🎫 今日はおやすみ。連続記録は守られます。ゆっくり休んでくださいね。")
    render()


def request_notification():
    try:
        def cb(perm):
            if str(perm) == "granted":
                try:
                    Notification.new("くらしの仕組み化",
                                     js_obj({"body": "通知の準備ができました🌱"}))
                except Exception:
                    pass
                window.alert("通知を許可しました。")
            else:
                window.alert("通知はオフのままです。開けば“今やること”が一番上に出るので大丈夫です。")
        p = Notification.requestPermission()
        p.then(create_proxy(cb))
    except Exception:
        window.alert("この端末/ブラウザでは通知が使えません。開いて使う形でも十分機能します。")


def do_export():
    data = json.dumps(state, ensure_ascii=False, indent=2)
    blob = window.Blob.new(to_js([data]), js_obj({"type": "application/json"}))
    url = window.URL.createObjectURL(blob)
    a = document.createElement("a")
    a.href = url
    a.download = "kurashi-backup.json"
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    window.URL.revokeObjectURL(url)


def do_import():
    inp = document.createElement("input")
    inp.type = "file"
    inp.accept = "application/json,.json"

    def on_file(evt):
        files = evt.target.files
        if files.length == 0:
            return
        f = files.item(0)
        reader = window.FileReader.new()

        def on_load(e):
            global state
            try:
                s = json.loads(str(reader.result))
                state = s
                # 欠損キー補完
                d = default_state()
                for k, v in d.items():
                    if k not in state:
                        state[k] = v
                save_state()
                window.alert("読み込みました。")
                nav["screen"] = "home"; render()
            except Exception:
                window.alert("ファイルを読み込めませんでした。")
        reader.onload = create_proxy(on_load)
        reader.readAsText(f)
    inp.addEventListener("change", create_proxy(on_file))
    inp.click()


def do_reset():
    if window.confirm("すべての記録を消して最初からにします。よろしいですか？"):
        global state
        localStorage.removeItem(STORAGE_KEY)
        state = default_state()
        save_state()
        nav["screen"] = "home"
        nav["onb_step"] = 1
        render()


def get_val(elid):
    el = document.getElementById(elid)
    if el is None:
        return ""
    return el.value


# ============================================================
# 起動
# ============================================================

def boot():
    # 起動時：日付が変わっていたら最小モードは自動解除（min_mode_date で自然に判定）
    document.getElementById("app").addEventListener("click", create_proxy(on_click))
    # ローディング画面を消す
    ld = document.getElementById("loading")
    if ld:
        ld.style.display = "none"
    render()


boot()
