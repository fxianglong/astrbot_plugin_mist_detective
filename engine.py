"""对局状态机：幕次、行动点、线索发放、谎言识破、紧张度、提示与计分。

游戏状态是一个可以直接 JSON 序列化的 dict，所有判定都在这里由程序完成；
大模型只负责“怎么说”，不决定“说了什么算数”。
"""

from __future__ import annotations

import re
import time

from .generator import Skeleton

BREAK_AT = 100  # 紧张度到这个值情绪崩溃
MAX_WRONG = 2  # 指认错几次结案

# 个人贡献分
PTS_KEY_CLUE = 5
PTS_CLUE = 1
PTS_BREAK_LIE = 8
PTS_BREAKDOWN = 5
PTS_ACCUSE = 10
PTS_EGG = 10

TITLES = [(25, "神探"), (10, "名侦探"), (3, "侦探"), (0, "见习侦探")]


def title_of(solved: int) -> str:
    for n, t in TITLES:
        if solved >= n:
            return t
    return "见习侦探"


def new_game(case: dict, sk: Skeleton, now: float | None = None, host: str = "", replay_of: int | None = None) -> dict:
    now = now or time.time()
    plan = list(sk.diff.ap)
    return {
        "case": case,
        "meta": {"theme": sk.theme.key, "theme_name": sk.theme.name, "trick": sk.trick.key, "style": sk.style.key,
                 "style_name": sk.style.name, "diff": sk.diff.key, "diff_name": sk.diff.name, "seed": sk.seed,
                 "replay_of": replay_of},
        "host": host,
        "private": {},
        "eggs": 0,
        "act": 1,
        "ap": plan[0],
        "ap_plan": plan,
        "final": False,  # 第三幕行动点用完：只能指认
        "found": [],
        "found_by": {},
        "broken": [],
        "pressure": {s["id"]: 0 for s in case["suspects"]},
        "broke_down": [],
        "claims": {s["id"]: [] for s in case["suspects"]},
        "history": {s["id"]: [] for s in case["suspects"]},
        "notes": [],
        "hints": 0,
        "wrong": [],
        "players": {},
        "status": "active",
        "created": now,
        "updated": now,
    }


# ---------------------------------------------------------------- 查找
def suspects(game: dict) -> list[dict]:
    return game["case"]["suspects"]


def suspect(game: dict, sid: str) -> dict | None:
    return next((s for s in suspects(game) if s["id"] == sid), None)


def clue(game: dict, cid: str) -> dict | None:
    return next((c for c in game["case"]["clues"] if c["id"] == cid), None)


def find_suspect(game: dict, text: str) -> dict | None:
    """按序号、全名、名字包含关系查找嫌疑人；有歧义时返回 None。"""
    t = (text or "").strip().lstrip("@")
    if not t:
        return None
    ss = suspects(game)
    if t.isdigit() and 1 <= int(t) <= len(ss):
        return ss[int(t) - 1]
    for s in ss:
        if t == s["name"] or t == s["id"]:
            return s
    hits = [s for s in ss if t in s["name"] or s["name"] in t]
    if len(hits) == 1:
        return hits[0]
    hits = [s for s in ss if s["identity"] and (t in s["identity"] or s["identity"] in t)]
    return hits[0] if len(hits) == 1 else None


def split_target(game: dict, text: str) -> tuple[dict | None, str]:
    """从“沈先生 你昨晚去了哪”这样的文字里切出嫌疑人和剩余部分。名字后可以不加空格。"""
    t = (text or "").strip()
    if not t:
        return None, ""
    first, _, rest = t.partition(" ")
    s = find_suspect(game, first)
    if s:
        return s, rest.strip()
    # 名字后面没有空格：按名字长度从长到短匹配前缀
    for s in sorted(suspects(game), key=lambda x: -len(x["name"])):
        if t.startswith(s["name"]):
            return s, t[len(s["name"]):].lstrip(" ，,:：").strip()
    return None, t


def find_found_clue(game: dict, text: str) -> dict | None:
    """在已获得的线索里按编号（c3 或 3）或名字查找。"""
    t = (text or "").strip().lower()
    if not t:
        return None
    found = [clue(game, cid) for cid in game["found"]]
    found = [c for c in found if c]
    m = re.fullmatch(r"c?(\d+)", t)
    if m:
        for c in found:
            if c["id"].lower() in (t, f"c{m.group(1)}"):
                return c
        return None
    hits = [c for c in found if t in c["name"].lower()]
    return hits[0] if len(hits) == 1 else None


def find_location(game: dict, text: str) -> str | None:
    t = (text or "").strip()
    locs = game["case"]["locations"]
    if not t:
        return None
    if t.isdigit() and 1 <= int(t) <= len(locs):
        return locs[int(t) - 1]
    if t in locs:
        return t
    hits = [l for l in locs if t in l or l in t]
    return hits[0] if len(hits) == 1 else None


# ---------------------------------------------------------------- 行动
def touch(game: dict, uid: str, name: str, now: float | None = None) -> None:
    p = game["players"].setdefault(uid, {"name": name, "pts": 0, "actions": 0})
    p["name"] = name or p["name"]
    p["actions"] += 1
    game["updated"] = now or time.time()


def credit(game: dict, uid: str, pts: int) -> None:
    if uid in game["players"]:
        game["players"][uid]["pts"] += pts


def bump(game: dict, uid: str, stat: str) -> None:
    """个人趣味统计：breaks（问崩几人）、wrongs（指错几次）、quick（第一幕就破案）。"""
    if uid in game["players"]:
        p = game["players"][uid]
        p[stat] = p.get(stat, 0) + 1


def badges(rows: list[tuple]) -> dict[str, list[str]]:
    """排行榜趣味称号。rows: (name, pts, solved, games, breaks, wrongs, quick)"""
    out: dict[str, list[str]] = {r[0]: [] for r in rows}
    mb = max((r[4] for r in rows), default=0)
    mw = max((r[5] for r in rows), default=0)
    for r in rows:
        if mb and r[4] == mb:
            out[r[0]].append("问哭人")
        if mw and r[5] == mw:
            out[r[0]].append("冤案制造机")
        if r[6]:
            out[r[0]].append("一眼看穿")
    return out


def give_clues(game: dict, ids: list[str], uid: str = "") -> list[dict]:
    """发放线索（去重），返回本次新得到的线索。"""
    out = []
    for cid in ids:
        c = clue(game, cid)
        if c and cid not in game["found"]:
            game["found"].append(cid)
            if c.get("hidden"):
                game["eggs"] = game.get("eggs", 0) + 1
            if uid:
                game["found_by"][cid] = uid
                credit(game, uid, PTS_EGG if c.get("hidden") else PTS_KEY_CLUE if c["key"] else PTS_CLUE)
            out.append(c)
    return out


def search(game: dict, loc: str, uid: str) -> list[dict]:
    ids = [c["id"] for c in game["case"]["clues"] if c["source"] == "search" and c["location"] == loc]
    return give_clues(game, ids, uid)


def testimony_pool(game: dict, sid: str, with_hidden: bool = True) -> list[dict]:
    """这个人掌握、还没说出来的证词线索。"""
    return [
        c for c in game["case"]["clues"]
        if c["source"] == "testimony" and c["holder"] == sid and c["id"] not in game["found"] and (with_hidden or not c.get("hidden"))
    ]


def accept_reveal(game: dict, sid: str, ids: list[str], uid: str) -> list[dict]:
    """模型提议吐露的线索，只有确实由此人掌握的才发放。"""
    pool = {c["id"] for c in testimony_pool(game, sid)}
    return give_clues(game, [i for i in ids if i in pool], uid)


def lies_broken_by(game: dict, sid: str, cid: str) -> list[dict]:
    s = suspect(game, sid)
    if not s:
        return []
    return [l for l in s["lies"] if l["broken_by"] == cid and l["id"] not in game["broken"]]


def mark_broken(game: dict, lies: list[dict], uid: str) -> None:
    for l in lies:
        if l["id"] not in game["broken"]:
            game["broken"].append(l["id"])
            credit(game, uid, PTS_BREAK_LIE)


def add_pressure(game: dict, sid: str, delta: int) -> bool:
    """加紧张度；本次刚好崩溃时返回 True。"""
    before = game["pressure"].get(sid, 0)
    after = max(0, min(BREAK_AT, before + int(delta)))
    game["pressure"][sid] = after
    if after >= BREAK_AT and sid not in game["broke_down"]:
        game["broke_down"].append(sid)
        return True
    return False


def record(game: dict, sid: str, who: str, question: str, reply: str, claim: str) -> None:
    h = game["history"].setdefault(sid, [])
    h.append([who, question, reply])
    del h[:-8]
    if claim:
        cl = game["claims"].setdefault(sid, [])
        if claim not in cl:
            cl.append(claim)
            del cl[:-12]


def spend(game: dict) -> list[str]:
    """消耗一个行动点；换幕时返回需要播报的文字。"""
    msgs: list[str] = []
    game["ap"] -= 1
    if game["ap"] > 0:
        return msgs
    if game["act"] == 1:
        game["act"] = 2
        game["ap"] = game["ap_plan"][1]
        ev = game["case"]["event"]
        new = give_clues(game, ev["clues"])
        txt = f"━━ 第二幕 · 疑点 ━━\n{ev['text'] or '夜更深了，事情起了变化。'}"
        if new:
            txt += "\n新线索：\n" + "\n".join(clue_line(c) for c in new)
        txt += f"\n（本幕行动点 {game['ap']}）"
        msgs.append(txt)
    elif game["act"] == 2:
        game["act"] = 3
        game["ap"] = game["ap_plan"][2]
        for sid in game["pressure"]:
            add_pressure(game, sid, 15)
        climax = (game["case"].get("climax") or {}).get("text") or "真相近在咫尺，每个人都察觉到了你们的目光，神色越发紧张。"
        msgs.append(f"━━ 第三幕 · 交锋 ━━\n{climax}\n（所有人紧张度 +15。这是最后一幕，行动点 {game['ap']}，可以 /对质 让两人当面对口供。想好了就 /指认。）")
    else:
        game["final"] = True
        game["ap"] = 0
        msgs.append("━━ 最后时刻 ━━\n行动点已经用完，再没有时间调查了。请用 /指认 名字 说出凶手（可以附上动机和手法）。")
    return msgs


def confront_breaks(game: dict, a: str, b: str) -> list[tuple[dict, dict]]:
    """对质时当场戳穿的谎言：两人中任何一人、尚未识破、且识破它的线索已经到手。"""
    out = []
    for sid in (a, b):
        s = suspect(game, sid)
        for l in s["lies"] if s else []:
            if l["id"] not in game["broken"] and l["broken_by"] and l["broken_by"] in game["found"]:
                out.append((s, l))
    return out


# ---------------------------------------------------------------- 投票
def start_vote(game: dict, target: str, uid: str, name: str, reasoning: str, secs: int, now: float | None = None) -> dict:
    now = now or time.time()
    v = {"id": f"{int(now * 1000)}", "target": target, "by": uid, "by_name": name, "reasoning": reasoning,
         "yes": [uid], "no": [], "deadline": now + secs}
    game["vote"] = v
    return v


def cast_vote(game: dict, uid: str, name: str, agree: bool) -> None:
    v = game["vote"]
    game["players"].setdefault(uid, {"name": name, "pts": 0, "actions": 0})
    for k in ("yes", "no"):
        if uid in v[k]:
            v[k].remove(uid)
    v["yes" if agree else "no"].append(uid)


def vote_verdict(game: dict) -> bool | None:
    """票数已经决定结果时返回 True/False，否则 None。以参与本案的人数为基数，过半通过。"""
    v = game["vote"]
    n = max(len(game["players"]), 1)
    if len(v["yes"]) * 2 > n:
        return True
    if len(v["no"]) * 2 >= n:
        return False
    return None


# ---------------------------------------------------------------- 提示
def hint(game: dict) -> str:
    game["hints"] += 1
    case = game["case"]
    culprit = case["truth"]["culprit"]
    keys = [c for c in case["clues"] if c["key"] and c["points_to"] == culprit and c["id"] not in game["found"]]
    keys.sort(key=lambda c: {"search": 0, "testimony": 1, "event": 2}[c["source"]])
    for c in keys:
        if c["source"] == "search":
            return f"🔎 {c['location']}还有东西没被发现，值得再仔细看看。"
        if c["source"] == "testimony":
            s = suspect(game, c["holder"])
            topic = c["topic"] or "当晚的事"
            return f"🗣 {s['name'] if s else '某人'}似乎还有话没说，问问他关于“{topic}”的事。"
    # 关键线索都到手了：提示可以识破的谎言
    order = sorted(suspects(game), key=lambda s: s["id"] != culprit)  # 先提示凶手的谎言
    for s in order:
        for l in s["lies"]:
            if l["id"] not in game["broken"] and l["broken_by"] in game["found"]:
                return f"🧩 {s['name']}关于“{l['topic']}”的说法有问题，试试把 {l['broken_by']} 出示给他。"
    if case["event"]["clues"] and game["act"] == 1:
        return "⏳ 有些事要到第二幕才会浮出水面，先把能问的都问一遍。"
    return "🧠 该拿到的线索你们都拿到了。把时间线按顺序排一排，看看谁的说法对不上。"


# ---------------------------------------------------------------- 计分
def case_score(game: dict, culprit_ok: bool, motive_ok: bool, method_ok: bool) -> int:
    if not culprit_ok:
        return 0
    s = 50 + (20 if motive_ok else 0) + (30 if method_ok else 0)
    s -= 5 * game["hints"] + 5 * len(game["wrong"])
    s += 5 * game.get("eggs", 0)  # 彩蛋加成，总分不超过 100
    return max(0, min(100, s))


# ---------------------------------------------------------------- 文字
def clue_line(c: dict) -> str:
    egg = "🥚彩蛋 " if c.get("hidden") else ""
    return f"【{c['id']}】{egg}{c['name']}：{c['text']}"


def pressure_bar(v: int) -> str:
    n = round(v / 20)
    return "▮" * n + "▯" * (5 - n)


def act_name(act: int) -> str:
    return {1: "第一幕 · 现场", 2: "第二幕 · 疑点", 3: "第三幕 · 交锋"}.get(act, "")


def status_line(game: dict) -> str:
    if game["final"]:
        return f"{act_name(game['act'])}｜行动点已用完，等待指认"
    return f"{act_name(game['act'])}｜剩余行动点 {game['ap']}"


def opening(game: dict) -> str:
    case = game["case"]
    m = game["meta"]
    lines = [
        "🕯 雾夜侦探社 · 新案件",
        f"《{case['title']}》",
        f"{m['theme_name']}｜{m['style_name']}｜{m['diff_name']}",
        "",
        case["intro"],
        "",
        f"受害人：{case['victim']['name']}（{case['victim']['identity']}）",
        case["victim"]["fate"],
        "",
        "嫌疑人：",
    ]
    for i, s in enumerate(suspects(game), 1):
        lines.append(f"{i}. {s['name']}｜{s['identity']}：{s['public']}")
    lines += [
        "",
        "可搜查：" + "、".join(case["locations"]),
        "",
        "玩法：/审讯 名字 问题｜/搜查 地点｜/出示 线索编号 名字｜/对质 名字 名字 话题｜/指认 名字 动机和手法",
        "其他：/案件 卷宗（随时查看进度）｜/提示（扣 5 分）｜/笔记 内容｜私聊我 /推理 内容 提交个人推理",
        status_line(game) + "。每次审讯、搜查、出示、对质消耗 1 点，全群共用。",
    ]
    return "\n".join(lines)


def dossier(game: dict) -> str:
    case = game["case"]
    lines = [f"📁 《{case['title']}》卷宗", status_line(game), "", "嫌疑人（紧张度）："]
    for i, s in enumerate(suspects(game), 1):
        mark = " 💥已崩溃" if s["id"] in game["broke_down"] else ""
        lines.append(f"{i}. {s['name']}｜{s['identity']}  {pressure_bar(game['pressure'].get(s['id'], 0))}{mark}")
        for cl in game["claims"].get(s["id"], [])[-3:]:
            lines.append(f"   · {cl}")
    lines.append("")
    if game["found"]:
        lines.append(f"已获得线索（{len(game['found'])}）：")
        for cid in game["found"]:
            c = clue(game, cid)
            if c:
                lines.append(clue_line(c))
    else:
        lines.append("还没有任何线索。")
    broken = [(s, l) for s in suspects(game) for l in s["lies"] if l["id"] in game["broken"]]
    if broken:
        lines += ["", "已识破的谎言："]
        for s, l in broken:
            lines.append(f"· {s['name']}：{l['truth']}")
    if game["notes"]:
        lines += ["", "笔记："]
        lines += [f"· {n['who']}：{n['text']}" for n in game["notes"][-8:]]
    lines += ["", "可搜查：" + "、".join(case["locations"])]
    return "\n".join(lines)


def truth_text(game: dict) -> str:
    """结案真相：直接从档案渲染，保证与过程一致。"""
    case = game["case"]
    cul = suspect(game, case["truth"]["culprit"])
    names = {s["id"]: s["name"] for s in suspects(game)}
    names["victim"] = case["victim"]["name"]
    lines = [
        f"🔍 真相 · 《{case['title']}》",
        f"凶手：{cul['name'] if cul else '?'}（{cul['identity'] if cul else ''}）",
        f"动机：{case['truth']['motive']}",
        f"手法：{case['truth']['method']}",
        "",
        case["truth"]["summary"],
        "",
        "当晚时间线：",
    ]
    for e in case["timeline"]:
        who = names.get(e["who"], e["who"])
        lines.append(f"{e['time']}  {who}｜{e['where']}｜{e['what']}")
    lines += ["", "线索回顾："]
    for c in case["clues"]:
        if c.get("hidden") and c["id"] not in game["found"]:
            lines.append("🥚 一个隐藏彩蛋没被发现")
            continue
        mark = "✅" if c["id"] in game["found"] else "❌"
        star = "★" if c["key"] and c["points_to"] == case["truth"]["culprit"] else ""
        lines.append(f"{mark}{star} {c['name']}")
    if case["red_herrings"]:
        lines += ["", "误导线索的真相："]
        for r in case["red_herrings"]:
            c = clue(game, r["clue"])
            if c:
                lines.append(f"· {c['name']}：{r['explain']}")
    secrets = [s for s in suspects(game) if s["id"] != case["truth"]["culprit"] and s["secret"]]
    if secrets:
        lines += ["", "其他人的秘密："]
        lines += [f"· {s['name']}：{s['secret']}" for s in secrets]
    if case["solution"]:
        lines += ["", f"推理链：{case['solution']}"]
    return "\n".join(lines)


def scoreboard(game: dict, score: int) -> str:
    lines = [f"🏅 本案得分 {score}" + (f"（提示 {game['hints']} 次）" if game["hints"] else "")]
    ps = sorted(game["players"].items(), key=lambda kv: -kv[1]["pts"])
    for _, p in ps[:8]:
        lines.append(f"· {p['name']}：贡献 {p['pts']}，行动 {p['actions']} 次")
    return "\n".join(lines)
