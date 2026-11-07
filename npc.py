"""审讯、出示、指认判定与结案独白的提示词，以及模型输出的解析。

模型只拿到“这个人该知道的东西”，并以 JSON 返回回答和建议的状态变化，由 engine 判定是否采纳。
"""

from __future__ import annotations

from . import engine
from .generator import parse_json
from .library import STYLES

NPC_SYSTEM = """你在一个群聊推理游戏里扮演一名嫌疑人，正在接受侦探们的审讯。
规则：
1. 始终以角色的身份、性格和说话方式回答，用第一人称，可以带神态动作（放在括号里）。不要跳出角色，不要提到游戏、AI、档案。
2. 回答简短，不超过 100 字。
3. 你只知道“你知道的事”里写的内容。不知道的就说不知道或含糊其辞，不要编造新的重大事实。
4. 对“你的谎言”里列出的话题，按谎言回答，除非提示里明确说谎言已被识破。
5. 不能和“你已经说过的话”矛盾（谎言被识破后改口除外）。
6. 如果玩家的问题碰到了“你可以透露的信息”里的话题，或者你的紧张度已经很高，就自然地说出来，并在 reveal 里填上编号；问题没碰到就不要主动说。
7. 遇到与案件无关、低俗或越界的问题，以角色口吻拒绝回答。
只输出 JSON：{"reply": "角色的回答", "pressure": 0到15之间的整数（这个问题让你多紧张）, "reveal": ["透露的线索编号"], "claim": "本轮你给出的一条关键说法，十五字以内，没有就留空"}"""


def _own_timeline(game: dict, sid: str) -> list[str]:
    names = {s["id"]: s["name"] for s in engine.suspects(game)}
    names["victim"] = game["case"]["victim"]["name"]
    return [f"{e['time']} 在{e['where']}：{e['what']}" for e in game["case"]["timeline"] if e["who"] == sid]


def npc_prompt(game: dict, s: dict, asker: str, question: str, presented: dict | None = None, broken: list[dict] | None = None) -> str:
    case = game["case"]
    is_culprit = s["id"] == case["truth"]["culprit"]
    style = STYLES.get(game["meta"]["style"])
    lines = [
        f"【案件】{case['title']}。{case['intro']}",
        f"【受害人】{case['victim']['name']}，{case['victim']['identity']}。{case['victim']['fate']}",
        f"【故事风格】{style.guide if style else ''}",
        "",
        f"【你是】{s['name']}，{s['identity']}。{s['public']}",
        f"【性格】{s['personality']}",
        f"【说话方式】{s['speech']}",
        f"【与受害人的关系】{s['relation']}",
        f"【你对外的行踪说法】{s['alibi']}",
        f"【你的秘密】{s['secret']}（不愿意说，被逼急了才会吐露）",
        f"【你的动机】{s['motive'] or '无'}（不会主动承认）",
        f"【你知道的关于别人的事】{s['knows'] or '无'}",
    ]
    own = _own_timeline(game, s["id"])
    if own:
        lines.append("【你当晚真实做过的事】" + "；".join(own))
    if is_culprit:
        lines.append(
            f"【重要】你就是凶手。真实手法：{case['truth']['method'].rstrip('。')}。你绝不主动承认，会撒谎、回避、转移话题、把嫌疑引向别人，"
            "但说法要前后一致。即使被识破某个谎言，也只承认那一件事，不承认作案。"
        )
    else:
        lines.append("【重要】你不是凶手，也不知道凶手是谁。除了谎言和秘密之外，你说的都是实话。")
    lies = [l for l in s["lies"] if l["id"] not in game["broken"]]
    if lies:
        lines.append("【你的谎言】" + "；".join(f"关于{l['topic']}，你会说：{l['lie']}" for l in lies))
    done = [l for l in s["lies"] if l["id"] in game["broken"]]
    if done:
        lines.append("【已经被识破、你已经承认的事】" + "；".join(l["truth"] for l in done))
    pool = engine.testimony_pool(game, s["id"])
    if pool:
        lines.append("【你可以透露的信息】" + "；".join(f"{c['id']}（话题：{c['topic'] or c['name']}）：{c['text']}" for c in pool))
    claims = game["claims"].get(s["id"], [])
    if claims:
        lines.append("【你已经说过的话】" + "；".join(claims))
    p = game["pressure"].get(s["id"], 0)
    lines.append(f"【你现在的紧张度】{p}/100" + ("，已经快撑不住了" if p >= 70 else ""))
    hist = game["history"].get(s["id"], [])[-4:]
    if hist:
        lines.append("【最近的问答】")
        lines += [f"{w}问：{q}\n你答：{a}" for w, q, a in hist]
    lines.append("")
    if presented:
        lines.append(f"【侦探{asker}向你出示了证据】{presented['name']}：{presented['text']}")
        if broken:
            for l in broken:
                lines.append(f"这条证据戳穿了你关于“{l['topic']}”的谎言（你原来说：{l['lie']}）。你必须改口承认：{l['truth']}。可以辩解、可以慌乱，但要承认这件事。")
        else:
            lines.append("这条证据没有戳穿你的谎言。根据你知道的情况回应：解释、否认与你有关，或说出你对它的看法。")
        if question:
            lines.append(f"侦探同时问：{question}")
    else:
        lines.append(f"【侦探{asker}问你】{question}")
    return "\n".join(lines)


BREAKDOWN_SYSTEM = "你在推理游戏中扮演一名嫌疑人。用第一人称、角色的说话方式写一段 80 字以内的情绪崩溃独白，说出你的秘密。不要承认没做过的事。只输出独白。"


def breakdown_prompt(game: dict, s: dict) -> str:
    is_culprit = s["id"] == game["case"]["truth"]["culprit"]
    extra = "你是凶手，但崩溃时也只说出秘密，不承认作案。" if is_culprit else "你不是凶手。"
    return f"你是{s['name']}（{s['identity']}），说话方式：{s['speech']}。你的秘密：{s['secret']}。{extra}"


def parse_npc(text: str) -> dict:
    """解析审讯输出；模型没按 JSON 输出时把整段当作回答。"""
    try:
        d = parse_json(text)
    except Exception:
        return {"reply": (text or "").strip()[:300] or "……", "pressure": 3, "reveal": [], "claim": ""}
    try:
        pr = int(float(d.get("pressure", 3)))
    except (TypeError, ValueError):
        pr = 3
    rv = d.get("reveal") or []
    if isinstance(rv, str):
        rv = [rv]
    return {
        "reply": str(d.get("reply") or "……").strip(),
        "pressure": max(0, min(15, pr)),
        "reveal": [str(x).strip() for x in rv if str(x).strip()],
        "claim": str(d.get("claim") or "").strip()[:30],
    }


# ---------------------------------------------------------------- 指认与结案
JUDGE_SYSTEM = "你是推理游戏的裁判。对照真相判断玩家的推理是否说中了动机和手法，大致正确即可，不苛求细节。只输出 JSON。"


def judge_prompt(game: dict, reasoning: str) -> str:
    t = game["case"]["truth"]
    return (
        f"真实动机：{t['motive']}\n真实手法：{t['method']}\n\n玩家的推理：{reasoning}\n\n"
        '输出：{"motive": true或false, "method": true或false, "comment": "一句话点评，不超过30字"}'
    )


def parse_judge(text: str) -> tuple[bool, bool, str]:
    try:
        d = parse_json(text)
    except Exception:
        return False, False, ""
    def b(v):
        return v is True or str(v).strip().lower() in ("true", "1", "是", "yes")
    return b(d.get("motive")), b(d.get("method")), str(d.get("comment") or "").strip()


CONFESS_SYSTEM = "你在推理游戏中扮演被揭穿的凶手。用第一人称、角色的说话方式写一段 150 字以内的认罪独白：为什么这么做、怎么做到的、此刻的心情。不写血腥细节。只输出独白。"


def confess_prompt(game: dict) -> str:
    case = game["case"]
    s = engine.suspect(game, case["truth"]["culprit"])
    return (
        f"你是{s['name']}（{s['identity']}），说话方式：{s['speech']}，性格：{s['personality']}。\n"
        f"受害人：{case['victim']['name']}。动机：{case['truth']['motive']}。手法：{case['truth']['method']}。\n"
        f"真相：{case['truth']['summary']}"
    )


WRONG_SYSTEM = "你是推理游戏的旁白。侦探们指认错了人，真凶逃脱。写一段 100 字以内的“错案后续”：被冤枉的人的结局，以及真凶在暗处的一个小动作（不点名真凶，只用暗示）。只输出旁白。"


def wrong_prompt(game: dict, accused: dict) -> str:
    case = game["case"]
    return f"案件：{case['title']}。被错误指认的人：{accused['name']}（{accused['identity']}），他的秘密：{accused['secret']}。真凶的手法：{case['truth']['method']}。"


# ---------------------------------------------------------------- 对质
CONFRONT_SYSTEM = """你在群聊推理游戏里同时扮演两名嫌疑人，让他们当着侦探的面对质。
规则：
1. 写 4~6 句两人你来我往的对话，每句不超过 50 字，保持各自的性格与说话方式，可以带神态动作（放在括号里）。
2. 每个人只说自己知道的事，按各自的谎言说话，除非提示里写明谎言当场被戳穿——那样他必须改口承认。
3. 不能与他们已经说过的话矛盾（被戳穿后改口除外）。凶手绝不承认作案。
4. 对质时如果话题碰到了某人“可以透露的信息”，他可以说出来，并把编号写进 reveal。
只输出 JSON：{"lines": [{"who": "名字", "say": "台词"}], "reveal": ["线索编号"], "claim_a": "第一个人的关键说法，十五字以内", "claim_b": "第二个人的关键说法，十五字以内"}"""


def _card(game: dict, s: dict) -> str:
    is_culprit = s["id"] == game["case"]["truth"]["culprit"]
    lines = [
        f"【{s['name']}】{s['identity']}。性格：{s['personality']}。说话方式：{s['speech']}。",
        f"对外行踪说法：{s['alibi']}",
        f"秘密（不愿说）：{s['secret']}",
        f"知道的关于别人的事：{s['knows'] or '无'}",
    ]
    own = _own_timeline(game, s["id"])
    if own:
        lines.append("当晚真实做过的事：" + "；".join(own))
    lines.append("他是凶手，绝不承认作案。" if is_culprit else "他不是凶手。")
    lies = [l for l in s["lies"] if l["id"] not in game["broken"]]
    if lies:
        lines.append("谎言：" + "；".join(f"关于{l['topic']}，他会说：{l['lie']}" for l in lies))
    pool = engine.testimony_pool(game, s["id"])
    if pool:
        lines.append("可以透露的信息：" + "；".join(f"{c['id']}（话题：{c['topic'] or c['name']}）：{c['text']}" for c in pool))
    claims = game["claims"].get(s["id"], [])
    if claims:
        lines.append("已经说过的话：" + "；".join(claims))
    return "\n".join(lines)


def confront_prompt(game: dict, a: dict, b: dict, topic: str, broken: list[tuple[dict, dict]]) -> str:
    case = game["case"]
    lines = [
        f"【案件】{case['title']}。受害人{case['victim']['name']}，{case['victim']['fate']}",
        "",
        _card(game, a),
        "",
        _card(game, b),
        "",
        f"【对质话题】{topic or '案发当晚各自的行踪和说法'}",
    ]
    for s, l in broken:
        c = engine.clue(game, l["broken_by"])
        lines.append(f"【当场戳穿】对方拿出了侦探已掌握的证据“{c['name'] if c else ''}”，{s['name']}关于“{l['topic']}”的谎言（原来说：{l['lie']}）被戳穿，必须改口承认：{l['truth']}")
    lines.append(f"对话由{a['name']}先开口。")
    return "\n".join(lines)


def parse_confront(text: str, a: dict, b: dict) -> dict:
    try:
        d = parse_json(text)
    except Exception:
        body = (text or "").strip()[:300] or "……"
        return {"lines": [(a["name"], body)], "reveal": [], "claim_a": "", "claim_b": ""}
    lines = []
    for it in d.get("lines") or []:
        if isinstance(it, dict) and str(it.get("say") or "").strip():
            lines.append((str(it.get("who") or "").strip() or "？", str(it["say"]).strip()))
    rv = d.get("reveal") or []
    if isinstance(rv, str):
        rv = [rv]
    return {
        "lines": lines[:8] or [(a["name"], "……")],
        "reveal": [str(x).strip() for x in rv if str(x).strip()],
        "claim_a": str(d.get("claim_a") or "").strip()[:30],
        "claim_b": str(d.get("claim_b") or "").strip()[:30],
    }
