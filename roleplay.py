"""角色扮演模式：群友各自扮演一名嫌疑人，其中一人是凶手。AI 负责写剧本、发角色卡、主持节奏和公布真相。

规则：
- 报名 3~6 人（可配置），开车后按人数生成案件，随机分配角色，私聊发角色卡。
- 共三轮：每轮每人可 /搜查 一次（结果全群可见），也可以 /公开 自己掌握的线索；其余时间自由讨论、互相盘问。
- 局长 /案件 推进 进入下一轮；第二轮开场有突发事件，第三轮开场有高潮事件。
- 第三轮结束进入投票，每人 /投票 角色名；全员投完或局长再推进即揭晓。
- 真凶得票最多（并列不算）→ 侦探胜：投中真凶的人 +20，所有无辜者 +10；否则凶手胜：凶手 +40。
"""

from __future__ import annotations

import random

from . import engine
from .library import Difficulty

ROUNDS = 3


def rp_difficulty(n: int) -> Difficulty:
    return Difficulty("rp", "角色扮演", n, 1 if n <= 4 else 2, (99, 99, 99), 3)


def assign(game: dict, players: dict[str, str], rng: random.Random) -> None:
    """随机把玩家分配到嫌疑人；players: {uid: 名字}"""
    uids = list(players)
    rng.shuffle(uids)
    sus = engine.suspects(game)
    game["mode"] = "rp"
    game["roles"] = {uid: sus[i]["id"] for i, uid in enumerate(uids[: len(sus)])}
    game["players"] = {uid: {"name": players[uid], "pts": 0, "actions": 0} for uid in uids}
    game["rp"] = {"searched": {}, "votes": {}, "dm_failed": []}


def is_rp(game: dict | None) -> bool:
    return bool(game) and game.get("mode") == "rp"


def role_of(game: dict, uid: str) -> dict | None:
    sid = game.get("roles", {}).get(uid)
    return engine.suspect(game, sid) if sid else None


def player_of(game: dict, sid: str) -> str:
    for uid, s in game.get("roles", {}).items():
        if s == sid:
            return game["players"].get(uid, {}).get("name", uid)
    return "AI"


def card_text(game: dict, uid: str) -> str:
    case = game["case"]
    s = role_of(game, uid)
    if not s:
        return "你没有参与这一局。"
    culprit = s["id"] == case["truth"]["culprit"]
    lines = [
        f"🎭 角色卡 ·《{case['title']}》",
        "（只给你一个人看，别发到群里）",
        "",
        f"你扮演：{s['name']}｜{s['identity']}",
        f"性格：{s['personality']}；说话方式：{s['speech']}",
        f"与受害人 {case['victim']['name']} 的关系：{s['relation']}",
        "",
        "【你的剧本】",
        s.get("script") or "（见下方行动与说法）",
    ]
    own = [f"{e['time']} {e['where']}：{e['what']}" for e in case["timeline"] if e["who"] == s["id"]]
    if own:
        lines += ["", "【你当晚真实的行动】"] + [f"· {x}" for x in own]
    lines += ["", f"【你对外的说法】{s['alibi']}"]
    if s["lies"]:
        lines.append("【你要守住的说法】")
        lines += [f"· 关于{l['topic']}：你会说“{l['lie']}”（真相：{l['truth']}）" for l in s["lies"]]
    lines.append(f"【你的秘密】{s['secret']}")
    if s["knows"]:
        lines.append(f"【你知道的别人的事】{s['knows']}")
    held = [c for c in case["clues"] if c["source"] == "testimony" and c["holder"] == s["id"] and not c.get("hidden")]
    if held:
        lines += ["", "【你掌握的线索】什么时候说、说不说由你决定；想正式公开就在群里发 /公开 编号"]
        lines += [f"· {c['id']} {c['name']}：{c['text']}" for c in held]
    lines.append("")
    if culprit:
        lines += [
            "🔪 你就是凶手。",
            f"动机：{case['truth']['motive']}",
            f"手法：{case['truth']['method']}",
            "目标：撑过三轮，不被大家投出来。可以撒谎、甩锅、带节奏，但说法要前后一致。",
        ]
    else:
        lines += ["🕵 你不是凶手。", "目标：找出真凶并投票指认；同时尽量守住自己的秘密。"]
    lines += ["", "每轮可以 /搜查 地点 一次；最后用 /投票 角色名 指认。私聊我 /我的角色 可以再看这张卡。"]
    return "\n".join(lines)


def opening(game: dict) -> str:
    case = game["case"]
    lines = [
        "🎭 雾夜侦探社 · 角色扮演",
        f"《{case['title']}》",
        "",
        case["intro"],
        "",
        f"受害人：{case['victim']['name']}（{case['victim']['identity']}）",
        case["victim"]["fate"],
        "",
        "角色：",
    ]
    for s in engine.suspects(game):
        lines.append(f"· {s['name']}｜{s['identity']} —— 由 {player_of(game, s['id'])} 扮演")
    lines += [
        "",
        "可搜查：" + "、".join(case["locations"]),
        "",
        "角色卡已私聊发给每位玩家，其中一人是凶手。",
        "玩法：自由讨论、互相盘问；每轮每人可 /搜查 地点 一次，也可以 /公开 自己的线索。",
        "局长发 /案件 推进 进入下一轮，共三轮，之后 /投票 角色名。",
        "现在是第 1 轮。",
    ]
    return "\n".join(lines)


def round_name(game: dict) -> str:
    if game["final"]:
        return "投票阶段"
    return f"第 {game['act']} 轮"


def can_search(game: dict, uid: str) -> bool:
    return game["rp"]["searched"].get(uid) != game["act"]


def mark_search(game: dict, uid: str) -> None:
    game["rp"]["searched"][uid] = game["act"]


def held_clue(game: dict, uid: str, text: str) -> dict | None:
    s = role_of(game, uid)
    if not s:
        return None
    t = text.strip().lower()
    for c in game["case"]["clues"]:
        if c["source"] == "testimony" and c["holder"] == s["id"] and (c["id"].lower() == t or t == c["id"].lower().lstrip("c") or t in c["name"]):
            return c
    return None


def vote(game: dict, uid: str, sid: str) -> None:
    game["rp"]["votes"][uid] = sid


def all_voted(game: dict) -> bool:
    return set(game["rp"]["votes"]) >= set(game["roles"])


def tally(game: dict) -> tuple[bool, dict[str, int]]:
    """返回 (侦探是否获胜, {角色id: 票数})。真凶得票严格最多才算侦探胜。"""
    counts: dict[str, int] = {}
    for sid in game["rp"]["votes"].values():
        counts[sid] = counts.get(sid, 0) + 1
    culprit = game["case"]["truth"]["culprit"]
    top = max(counts.values(), default=0)
    leaders = [k for k, v in counts.items() if v == top]
    return (top > 0 and leaders == [culprit]), counts


def settle(game: dict) -> tuple[bool, list[str]]:
    """结算积分，返回 (侦探是否获胜, 播报文字)。"""
    win, counts = tally(game)
    culprit = game["case"]["truth"]["culprit"]
    cul_uid = next((u for u, s in game["roles"].items() if s == culprit), None)
    lines = ["🗳 投票结果："]
    for s in engine.suspects(game):
        lines.append(f"· {s['name']}（{player_of(game, s['id'])}）：{counts.get(s['id'], 0)} 票")
    cul = engine.suspect(game, culprit)
    lines.append("")
    if win:
        lines.append(f"🕵 侦探获胜！真凶正是 {cul['name']}（{player_of(game, culprit)} 扮演）。")
        for uid, sid in game["roles"].items():
            if uid == cul_uid:
                continue
            pts = 10 + (20 if game["rp"]["votes"].get(uid) == culprit else 0)
            engine.credit(game, uid, pts)
    else:
        lines.append(f"🔪 凶手胜！真凶是 {cul['name']}（{player_of(game, culprit)} 扮演），TA 骗过了所有人。")
        if cul_uid:
            engine.credit(game, cul_uid, 40)
    return win, lines


def advance(game: dict) -> str:
    """局长推进：第 1 轮 → 第 2 轮（突发事件）→ 第 3 轮（高潮事件）→ 投票。"""
    case = game["case"]
    if game["act"] == 1:
        game["act"] = 2
        new = engine.give_clues(game, case["event"]["clues"])
        txt = f"━━ 第 2 轮 ━━\n{case['event']['text'] or '夜更深了，事情起了变化。'}"
        if new:
            txt += "\n新线索：\n" + "\n".join(engine.clue_line(c) for c in new)
        return txt + "\n每人本轮可以再 /搜查 一次。"
    if game["act"] == 2:
        game["act"] = 3
        climax = (case.get("climax") or {}).get("text") or "真相近在咫尺，每个人都察觉到了别人的目光。"
        return f"━━ 第 3 轮 · 最后一轮 ━━\n{climax}\n每人本轮可以再 /搜查 一次。想好了等局长推进进入投票。"
    game["final"] = True
    names = "、".join(s["name"] for s in engine.suspects(game))
    return f"━━ 投票 ━━\n讨论结束。请每位玩家发 /投票 角色名（{names}），可以改票。全员投完或局长再次 /案件 推进 即揭晓。"
