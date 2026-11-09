"""图片卷宗：开场卷宗、线索墙、结案时间线。Jinja2 模板，由 AstrBot 的 html_render 渲染成图片。

每个题材一套配色与字体；渲染失败时 main.py 自动退回文字。
"""

from __future__ import annotations

from . import engine

SERIF = '"Noto Serif CJK SC", "Source Han Serif SC", "Songti SC", "SimSun", serif'
SANS = '"PingFang SC", "Microsoft YaHei", "Noto Sans CJK SC", "Source Han Sans SC", sans-serif'
MONO = '"JetBrains Mono", "Sarasa Mono SC", "Noto Sans Mono CJK SC", "Microsoft YaHei", monospace'

# bg 页面底色、paper 卡片、ink 正文、sub 次要文字、accent 强调色、line 分隔线、font 字体、stamp 印章文字
PALETTES = {
    "inn": dict(bg="#2b2622", paper="#f3ead8", ink="#2a211a", sub="#7a6a58", accent="#a4372a", line="#d9cbb0", font=SERIF, stamp="江湖卷宗"),
    "changan": dict(bg="#2a1f24", paper="#f5ebd9", ink="#2c1d1d", sub="#80695c", accent="#b0302a", line="#e0cfb3", font=SERIF, stamp="长安卷宗"),
    "opera": dict(bg="#22262b", paper="#efe8dc", ink="#23201c", sub="#756c60", accent="#9c2b2b", line="#d8cdbb", font=SERIF, stamp="戏班卷宗"),
    "shanghai": dict(bg="#1d1a17", paper="#efe2c6", ink="#2b2016", sub="#7b6650", accent="#8a5a1c", line="#d6c29c", font=SERIF, stamp="申报 · 号外"),
    "manor": dict(bg="#1b2420", paper="#f1ece0", ink="#1f2420", sub="#6c7268", accent="#4b6b4f", line="#d6d0c0", font=SERIF, stamp="SCOTLAND YARD"),
    "train": dict(bg="#24302a", paper="#eee8d6", ink="#25291f", sub="#6f725e", accent="#2f6b4f", line="#d4cdb5", font=SANS, stamp="K 字头 · 卧铺"),
    "homestay": dict(bg="#0f172a", paper="#ffffff", ink="#0f172a", sub="#64748b", accent="#e11d48", line="#e2e8f0", font=SANS, stamp="LIVE · 已中断"),
    "campus": dict(bg="#1e293b", paper="#ffffff", ink="#1e293b", sub="#64748b", accent="#2563eb", line="#e2e8f0", font=SANS, stamp="社团档案"),
    "station": dict(bg="#0b1220", paper="#e8eef5", ink="#0f1b2d", sub="#5a6b80", accent="#0e7490", line="#c9d6e3", font=SANS, stamp="STATION LOG"),
    "cyber": dict(bg="#0a0a12", paper="#141428", ink="#e6e6f0", sub="#8b8ba7", accent="#ff2bd6", line="#2a2a48", font=MONO, stamp="NEURAL CASE FILE"),
    "custom": dict(bg="#1f2328", paper="#f6f3ee", ink="#1f2328", sub="#6e7781", accent="#8250df", line="#e1dcd3", font=SANS, stamp="特别卷宗"),
}
AVATAR = ["#a4372a", "#2f6b4f", "#8a5a1c", "#2563eb", "#7c3aed", "#0e7490"]

BASE_CSS = """
* { box-sizing: border-box; margin: 0; padding: 0; }
html, body { background: {{ p.bg }}; }
body { font-family: {{ p.font }}; color: {{ p.ink }}; width: 800px; margin: 0 auto; padding: 28px; line-height: 1.6; }
.card { background: {{ p.paper }}; border-radius: 6px; padding: 26px 28px; margin-bottom: 18px; box-shadow: 0 6px 20px rgba(0,0,0,.25); position: relative; }
.stamp { position: absolute; top: 22px; right: 24px; border: 2px solid {{ p.accent }}; color: {{ p.accent }}; padding: 2px 10px;
         font-size: 13px; letter-spacing: 2px; transform: rotate(6deg); opacity: .85; font-weight: 700; }
.kicker { font-size: 13px; color: {{ p.sub }}; letter-spacing: 3px; }
h1 { font-size: 34px; line-height: 1.3; margin: 6px 0 10px; letter-spacing: 1px; }
h2 { font-size: 18px; margin-bottom: 12px; color: {{ p.accent }}; letter-spacing: 2px; }
.tags span { display: inline-block; font-size: 12px; border: 1px solid {{ p.line }}; color: {{ p.sub }}; padding: 1px 8px; border-radius: 10px; margin-right: 6px; }
.intro { font-size: 16px; margin-top: 14px; text-indent: 2em; }
.victim { margin-top: 16px; padding: 12px 14px; border-left: 4px solid {{ p.accent }}; background: rgba(0,0,0,.04); font-size: 15px; }
.victim b { font-size: 16px; }
.sus { display: flex; flex-wrap: wrap; gap: 12px; }
.su { width: calc(50% - 6px); border: 1px solid {{ p.line }}; border-radius: 6px; padding: 12px; display: flex; gap: 12px; }
.av { width: 46px; height: 46px; border-radius: 50%; color: #fff; font-size: 20px; font-weight: 700; display: flex; align-items: center; justify-content: center; flex: none; }
.su .n { font-size: 17px; font-weight: 700; }
.su .i { font-size: 12px; color: {{ p.sub }}; }
.su .d { font-size: 13px; margin-top: 4px; }
.chips span { display: inline-block; font-size: 14px; padding: 3px 12px; margin: 0 8px 8px 0; border-radius: 4px; background: rgba(0,0,0,.05); border: 1px dashed {{ p.line }}; }
.foot { font-size: 12px; color: {{ p.sub }}; line-height: 1.8; }
.foot code { font-family: {{ p.font }}; color: {{ p.accent }}; }
"""

OPENING_TMPL = (
    "<html><head><meta charset='utf-8'><style>"
    + BASE_CSS
    + """</style></head><body>
<div class="card">
  <div class="stamp">{{ p.stamp }}</div>
  <div class="kicker">雾夜侦探社 · 新案件</div>
  <h1>《{{ title }}》</h1>
  <div class="tags">{% for t in tags %}<span>{{ t }}</span>{% endfor %}</div>
  <div class="intro">{{ intro }}</div>
  <div class="victim"><b>受害人：{{ victim.name }}</b>（{{ victim.identity }}）<br>{{ victim.fate }}</div>
</div>
<div class="card">
  <h2>嫌 疑 人</h2>
  <div class="sus">
  {% for s in suspects %}
    <div class="su"><div class="av" style="background: {{ s.color }}">{{ s.initial }}</div>
      <div><div class="n">{{ s.no }}. {{ s.name }}</div><div class="i">{{ s.identity }}</div><div class="d">{{ s.public }}</div></div></div>
  {% endfor %}
  </div>
</div>
<div class="card">
  <h2>可 搜 查</h2>
  <div class="chips">{% for l in locations %}<span>{{ l }}</span>{% endfor %}</div>
  <div class="foot" style="margin-top:10px">
    <code>/审讯 名字 问题</code>　<code>/搜查 地点</code>　<code>/出示 线索编号 名字</code>　<code>/对质 名字 名字 话题</code>　<code>/指认 名字 动机和手法</code><br>
    {{ status }}。每次审讯、搜查、出示、对质消耗 1 点，全群共用。<code>/案件 卷宗</code> 随时查看线索墙。
  </div>
</div>
</body></html>"""
)

BOARD_CSS = """
.board { background: #8b6a45; background-image: radial-gradient(rgba(0,0,0,.12) 1px, transparent 1px); background-size: 6px 6px;
         border-radius: 6px; padding: 22px 18px 10px; margin-bottom: 18px; box-shadow: inset 0 0 30px rgba(0,0,0,.35); }
.status { color: #fff; font-size: 15px; margin-bottom: 14px; display: flex; justify-content: space-between; }
.status b { font-size: 20px; }
.row { display: flex; flex-wrap: wrap; gap: 12px; }
.note { background: #fdf6d8; color: #2a2418; width: calc(33.33% - 8px); padding: 14px 12px 12px; position: relative; font-family: {{ p.font }};
        box-shadow: 2px 3px 8px rgba(0,0,0,.35); font-size: 13px; line-height: 1.55; margin-bottom: 6px; }
.note:nth-child(3n+1) { transform: rotate(-1.2deg); } .note:nth-child(3n+2) { transform: rotate(.8deg); } .note:nth-child(3n) { transform: rotate(-.4deg); }
.note.t { background: #e4f0fb; } .note.e { background: #fbe4e4; } .note.h { background: #e9f8e1; }
.note .pin { position: absolute; top: -6px; left: 50%; width: 14px; height: 14px; border-radius: 50%; background: #c0392b; box-shadow: 0 2px 2px rgba(0,0,0,.4); }
.note .id { font-size: 11px; color: #8a7a5a; } .note .nm { font-size: 15px; font-weight: 700; margin-bottom: 4px; }
.people { display: flex; flex-wrap: wrap; gap: 10px; margin-bottom: 16px; }
.pp { background: {{ p.paper }}; color: {{ p.ink }}; border-radius: 6px; padding: 10px 12px; width: calc(50% - 5px); font-size: 13px; }
.pp .n { font-size: 16px; font-weight: 700; } .pp .i { color: {{ p.sub }}; font-size: 12px; margin-left: 6px; }
.bar { height: 6px; background: rgba(0,0,0,.1); border-radius: 3px; margin: 6px 0; overflow: hidden; }
.bar i { display: block; height: 100%; background: {{ p.accent }}; }
.pp .cl { color: {{ p.sub }}; }
.boom { color: #c0392b; font-weight: 700; margin-left: 6px; }
.lies li { margin-left: 18px; font-size: 14px; margin-bottom: 4px; }
"""

BOARD_TMPL = (
    "<html><head><meta charset='utf-8'><style>"
    + BASE_CSS
    + BOARD_CSS
    + """</style></head><body>
<div class="card" style="padding:18px 24px"><div class="kicker">线索墙</div><h1 style="font-size:26px;margin:2px 0 0">《{{ title }}》</h1></div>
<div class="board">
  <div class="status"><span><b>{{ act }}</b></span><span>{{ ap }}</span></div>
  <div class="people">
  {% for s in suspects %}
    <div class="pp"><span class="n">{{ s.no }}. {{ s.name }}</span><span class="i">{{ s.identity }}</span>{% if s.broke %}<span class="boom">💥已崩溃</span>{% endif %}
      <div class="bar"><i style="width: {{ s.pressure }}%"></i></div>
      {% for c in s.claims %}<div class="cl">· {{ c }}</div>{% endfor %}</div>
  {% endfor %}
  </div>
  {% if clues %}<div class="row">
  {% for c in clues %}
    <div class="note {{ c.kind }}"><div class="pin"></div><div class="id">{{ c.id }} · {{ c.src }}</div><div class="nm">{{ c.name }}</div>{{ c.text }}</div>
  {% endfor %}</div>
  {% else %}<div class="status">还没有任何线索。</div>{% endif %}
</div>
{% if lies or notes %}<div class="card">
  {% if lies %}<h2>已 识 破 的 谎 言</h2><ul class="lies">{% for l in lies %}<li><b>{{ l.name }}</b>：{{ l.truth }}</li>{% endfor %}</ul>{% endif %}
  {% if notes %}<h2 style="margin-top:12px">笔 记</h2><ul class="lies">{% for n in notes %}<li><b>{{ n.who }}</b>：{{ n.text }}</li>{% endfor %}</ul>{% endif %}
</div>{% endif %}
<div class="card" style="padding:14px 24px"><div class="foot">可搜查：{{ locations }}</div></div>
</body></html>"""
)

CLOSING_CSS = """
.verdict { display: flex; gap: 16px; align-items: center; margin-top: 10px; }
.verdict .av { width: 64px; height: 64px; font-size: 28px; }
.verdict .n { font-size: 24px; font-weight: 700; }
.kv { margin-top: 14px; font-size: 15px; } .kv b { color: {{ p.accent }}; }
.tl { position: relative; margin-left: 66px; border-left: 2px solid {{ p.line }}; }
.ev { position: relative; padding: 0 0 14px 18px; font-size: 14px; }
.ev .t { position: absolute; left: -70px; width: 56px; text-align: right; color: {{ p.sub }}; font-variant-numeric: tabular-nums; }
.ev:before { content: ""; position: absolute; left: -7px; top: 6px; width: 12px; height: 12px; border-radius: 50%; background: {{ p.paper }}; border: 2px solid {{ p.line }}; }
.ev.hot:before { background: {{ p.accent }}; border-color: {{ p.accent }}; }
.ev.hot .w { color: {{ p.accent }}; font-weight: 700; }
.ev .w { font-weight: 600; } .ev .l { color: {{ p.sub }}; font-size: 12px; margin-left: 6px; }
.clues { display: flex; flex-wrap: wrap; gap: 8px; }
.clues span { font-size: 13px; padding: 3px 10px; border-radius: 4px; border: 1px solid {{ p.line }}; }
.clues .miss { opacity: .55; text-decoration: line-through; }
.clues .key { border-color: {{ p.accent }}; }
.score { font-size: 44px; font-weight: 800; color: {{ p.accent }}; }
.players li { margin-left: 18px; font-size: 14px; }
.confess { font-size: 15px; margin-top: 12px; padding: 12px 14px; background: rgba(0,0,0,.04); border-radius: 4px; }
"""

CLOSING_TMPL = (
    "<html><head><meta charset='utf-8'><style>"
    + BASE_CSS
    + CLOSING_CSS
    + """</style></head><body>
<div class="card">
  <div class="stamp">{{ result }}</div>
  <div class="kicker">真相 · 结案报告</div>
  <h1>《{{ title }}》</h1>
  <div class="verdict"><div class="av" style="background: {{ culprit.color }}">{{ culprit.initial }}</div>
    <div><div class="kicker">凶手</div><div class="n">{{ culprit.name }}</div><div class="kicker" style="letter-spacing:0">{{ culprit.identity }}</div></div></div>
  <div class="kv"><b>动机</b>　{{ motive }}</div>
  <div class="kv"><b>手法</b>　{{ method }}</div>
  <div class="intro" style="margin-top:12px">{{ summary }}</div>
  {% if confess %}<div class="confess">“{{ confess }}”</div>{% endif %}
</div>
<div class="card">
  <h2>当 晚 时 间 线</h2>
  <div class="tl">
  {% for e in timeline %}
    <div class="ev {% if e.hot %}hot{% endif %}"><span class="t">{{ e.time }}</span><span class="w">{{ e.who }}</span><span class="l">{{ e.where }}</span><div>{{ e.what }}</div></div>
  {% endfor %}
  </div>
</div>
<div class="card">
  <h2>线 索 回 顾</h2>
  <div class="clues">{% for c in clues %}<span class="{{ 'key' if c.key }} {{ 'miss' if not c.found }}">{{ '★' if c.key }}{{ c.name }}</span>{% endfor %}</div>
  <div class="foot" style="margin-top:8px">★ 指向真凶的关键线索；划线的是你们错过的。{% if egg_missed %}还有一个隐藏彩蛋没被发现。{% endif %}</div>
  {% if solution %}<div class="kv"><b>推理链</b>　{{ solution }}</div>{% endif %}
</div>
<div class="card" style="display:flex;gap:28px;align-items:center">
  <div style="text-align:center"><div class="kicker">本案得分</div><div class="score">{{ score }}</div></div>
  <ul class="players">{% for pl in players %}<li><b>{{ pl.name }}</b>　贡献 {{ pl.pts }} · 行动 {{ pl.actions }} 次</li>{% endfor %}</ul>
</div>
</body></html>"""
)


def palette(game: dict) -> dict:
    return PALETTES.get(game["meta"]["theme"], PALETTES["custom"])


def _player(game: dict, sid: str) -> str:
    for uid, x in (game.get("roles") or {}).items():
        if x == sid:
            return game["players"].get(uid, {}).get("name", uid)
    return ""


def _avatar(i: int) -> str:
    return AVATAR[i % len(AVATAR)]


def opening_data(game: dict) -> dict:
    case, m = game["case"], game["meta"]
    return {
        "p": palette(game),
        "title": case["title"],
        "tags": [m["theme_name"], m["style_name"], m["diff_name"]],
        "intro": case["intro"],
        "victim": case["victim"],
        "suspects": [
            {"no": i, "name": s["name"], "identity": s["identity"] + (f" · 扮演：{_player(game, s['id'])}" if game.get("mode") == "rp" else ""),
             "public": s["public"], "initial": s["name"][:1], "color": _avatar(i - 1)}
            for i, s in enumerate(engine.suspects(game), 1)
        ],
        "locations": case["locations"],
        "status": engine.status_line(game),
    }


SRC_NAME = {"search": "搜查", "testimony": "证词", "event": "事件"}


def board_data(game: dict) -> dict:
    case = game["case"]
    clues = []
    for cid in game["found"]:
        c = engine.clue(game, cid)
        if not c:
            continue
        kind = "h" if c.get("hidden") else {"search": "", "testimony": "t", "event": "e"}[c["source"]]
        src = "彩蛋" if c.get("hidden") else (c["location"] if c["source"] == "search" else SRC_NAME[c["source"]])
        clues.append({"id": c["id"], "name": c["name"], "text": c["text"], "kind": kind, "src": src})
    return {
        "p": palette(game),
        "title": case["title"],
        "act": engine.act_name(game["act"]),
        "ap": "行动点已用完，等待指认" if game["final"] else f"剩余行动点 {game['ap']}",
        "suspects": [
            {"no": i, "name": s["name"], "identity": s["identity"], "pressure": game["pressure"].get(s["id"], 0),
             "broke": s["id"] in game["broke_down"], "claims": game["claims"].get(s["id"], [])[-3:]}
            for i, s in enumerate(engine.suspects(game), 1)
        ],
        "clues": clues,
        "lies": [{"name": s["name"], "truth": l["truth"]} for s in engine.suspects(game) for l in s["lies"] if l["id"] in game["broken"]],
        "notes": game["notes"][-6:],
        "locations": "、".join(case["locations"]),
    }


def closing_data(game: dict, score: int, result: str, confess: str = "") -> dict:
    case = game["case"]
    culprit_id = case["truth"]["culprit"]
    ss = engine.suspects(game)
    idx = next((i for i, s in enumerate(ss) if s["id"] == culprit_id), 0)
    cul = ss[idx] if ss else {"name": "?", "identity": ""}
    names = {s["id"]: s["name"] for s in ss}
    names["victim"] = case["victim"]["name"]
    return {
        "p": palette(game),
        "title": case["title"],
        "result": {"solved": "已结案", "failed": "错案", "abandoned": "悬案"}.get(result, "结案"),
        "culprit": {"name": cul["name"], "identity": cul["identity"], "initial": cul["name"][:1], "color": _avatar(idx)},
        "motive": case["truth"]["motive"],
        "method": case["truth"]["method"],
        "summary": case["truth"]["summary"],
        "confess": confess,
        "timeline": [
            {"time": e["time"], "who": names.get(e["who"], e["who"]), "where": e["where"], "what": e["what"], "hot": e["who"] == culprit_id}
            for e in case["timeline"]
        ],
        "clues": [
            {"name": c["name"], "found": c["id"] in game["found"], "key": c["key"] and c["points_to"] == culprit_id}
            for c in case["clues"] if not c.get("hidden") or c["id"] in game["found"]
        ],
        "egg_missed": any(c.get("hidden") and c["id"] not in game["found"] for c in case["clues"]),
        "solution": case["solution"],
        "score": score,
        "players": sorted(game["players"].values(), key=lambda p: -p["pts"])[:8],
    }
