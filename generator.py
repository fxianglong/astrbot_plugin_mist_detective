"""抽骨架 → 让大模型写真相档案 → 解析与整理。

程序决定题材、诡计、风格和规模（保证多样与可解），大模型负责把它写成有血有肉的故事。
"""

from __future__ import annotations

import json
import random
import re
from dataclasses import dataclass

from .library import DIFFICULTIES, STYLES, THEMES, TRICKS, Difficulty, Style, Theme, Trick


@dataclass
class Skeleton:
    theme: Theme
    trick: Trick
    style: Style
    diff: Difficulty
    seed: int


def pick_skeleton(
    rng: random.Random,
    theme: Theme | None = None,
    style: Style | None = None,
    diff: Difficulty | None = None,
    trick: Trick | None = None,
    avoid: tuple[str, ...] = (),
    disabled_themes: set[str] = frozenset(),
    disabled_tricks: set[str] = frozenset(),
) -> Skeleton:
    """随机抽骨架；avoid 是最近用过的“题材:诡计”组合，尽量不重复；disabled_* 是群管理关掉的题材和诡计（key）。"""
    if theme is None:
        themes = [t for t in THEMES.values() if t.key not in disabled_themes] or list(THEMES.values())
        theme = rng.choice(themes)
    style = style or STYLES["honkaku"]
    diff = diff or DIFFICULTIES["normal"]
    if trick is None:
        pool = [t for t in TRICKS.values() if (not t.themes or theme.key in t.themes) and t.key not in disabled_tricks] or list(TRICKS.values())
        fresh = [t for t in pool if f"{theme.key}:{t.key}" not in avoid] or pool
        trick = rng.choice(fresh)
    return Skeleton(theme, trick, style, diff, rng.randrange(1 << 30))


# ---------------------------------------------------------------- 生成提示词
GEN_SYSTEM = """你是一位顶尖的推理小说作家兼剧本杀编剧，正在为一个群聊推理游戏设计案件。
玩家通过审讯嫌疑人、搜查地点、出示证据来破案。你写的是一份只给游戏程序看的“真相档案”，玩家看不到。

硬性要求：
1. 案件必须可以被推理出来：所有破案需要的信息都放进线索或证词里，凶手不能靠巧合或超能力。
2. 线索的 text 只写玩家看到、听到的事实，不写结论（写“门槛缝里卡着一截细麻绳”，不写“这证明是机关密室”）。
3. 每个无辜的嫌疑人也要有一个不想让人知道、与案件无关的秘密，使他们在审讯时显得可疑。
4. 人物要有鲜明的性格和说话方式，让人一听就知道是谁在说话。
5. 内容是虚构的推理游戏：不写血腥细节，不写现实中可操作的作案细节（毒物不写名称、剂量、获取方式），不涉及未成年人受害、性犯罪、真实人物或真实政治事件。
6. 只输出一个 JSON 对象，不要任何解释、不要 Markdown 代码块。"""

SCHEMA = """{
  "title": "案件名，有文学感，如《风雪客栈的最后一壶酒》",
  "intro": "开场旁白，150~250 字，交代场景、受害人和为什么谁也走不了；不能透露凶手和手法",
  "victim": {"name": "受害人名字", "identity": "身份", "fate": "大家看到的现场情况，一两句"},
  "locations": ["可以搜查的地点，5~6 个"],
  "suspects": [
    {
      "id": "s1",
      "name": "名字",
      "identity": "身份",
      "public": "公开介绍，一句话，带点性格",
      "relation": "与受害人的表面关系",
      "personality": "性格",
      "speech": "说话风格与口癖，具体到可以模仿",
      "alibi": "他自己对案发时段行踪的说法（凶手的这条是谎言）",
      "motive": "可能的动机（隐藏，无辜者也可以有）",
      "secret": "不想让人知道的秘密；凶手的写真实身份或真正动机",
      "knows": "他知道的、关于别人的一件事，被问到时可能说出来",
      "lies": [
        {"id": "l1", "topic": "谎言涉及的话题", "lie": "他会怎么说", "truth": "真实情况", "broken_by": "能识破它的线索编号，如 c3"}
      ]
    }
  ],
  "truth": {"culprit": "凶手的 id，如 s4", "motive": "真实动机", "method": "作案手法", "summary": "完整真相，200 字以内"},
  "timeline": [
    {"time": "21:40", "who": "s4 或 victim", "where": "地点", "what": "做了什么"}
  ],
  "clues": [
    {"id": "c1", "name": "线索名，四到八个字", "text": "玩家拿到时看到的描述", "source": "search", "location": "所在地点（必须是 locations 之一）", "points_to": "指向的嫌疑人 id，不指向任何人留空", "key": true},
    {"id": "c2", "name": "...", "text": "这个人会说出的话或透露的信息", "source": "testimony", "holder": "掌握它的嫌疑人 id", "topic": "问到什么话题时会说", "points_to": "", "key": false},
    {"id": "c9", "name": "...", "text": "彩蛋内容", "source": "testimony", "holder": "s2", "topic": "非常具体的触发话题", "points_to": "", "key": false, "hidden": true}
  ],
  "event": {"text": "第二幕的突发事件，80~150 字，推翻大家的第一印象，并带出新线索", "clues": ["事件带出的线索编号，这些线索 source 写 event"]},
  "climax": {"text": "第三幕开场的事件，50~100 字，制造紧迫感或新的冲突（如有人试图销毁证据、暴风雪切断灯火、某人突然翻供），不带新的关键线索"},
  "flaws": [{"text": "诡计留下的破绽", "clues": ["能发现它的线索编号"]}],
  "red_herrings": [{"clue": "误导线索编号", "explain": "它的真实解释"}],
  "solution": "推理链：从哪几条线索、经过哪几步推出凶手和手法，3~5 步"
}"""


def gen_prompt(sk: Skeleton, feedback: str = "") -> str:
    d = sk.diff
    lines = [
        "请设计一个案件。",
        f"【题材】{sk.theme.name}：{sk.theme.setting}",
        f"【气氛】{sk.theme.mood}",
        f"【地点参考】{'、'.join(sk.theme.locations) or '按题材自拟'}（可以改名或替换，保持 5~6 个）",
        f"【人物原型参考】{'、'.join(sk.theme.archetypes) or '按题材自拟'}（挑选或改编，不必全用）",
        f"【起名】{sk.theme.naming}",
        f"【时间】{sk.theme.time_note}",
        f"【风格】{sk.style.guide}",
        f"【核心诡计】{sk.trick.name}：{sk.trick.idea}",
        "【诡计必须留下的破绽】" + "；".join(sk.trick.flaws) + "。每条破绽都要对应至少一张关键线索。",
        f"【规模】嫌疑人正好 {d.suspects} 个（受害人不算），其中 1 个是凶手；线索 {8 + d.suspects}~{10 + d.suspects * 2} 张；"
        f"至少 {d.key_clues} 张 key=true 且 points_to 为凶手的关键线索；红鲱鱼（指向无辜者的误导线索）{d.red_herrings} 张。",
        "【结构】三层：表层有一个“看起来最像凶手”的无辜者；中层是各人的秘密与红鲱鱼；深层才是真正的诡计。第二幕事件要推翻表层印象，第三幕事件把紧张感推到顶点。",
        "【线索分布】既要有 search（搜查地点得到）也要有 testimony（审讯时嫌疑人说出），event 线索 1~2 张。凶手至少有 1 条能被线索识破的谎言（lies.broken_by）；其他人可以各有 0~2 条谎言。",
        "【彩蛋】另设 1 张隐藏线索（hidden=true，source=testimony，key=false）：只有侦探问到一个非常具体、意想不到的话题时才会说出，内容有趣或带出一段旧事，不影响破案。",
        "【时间线】按时间顺序列出 10~16 条，包含凶手作案的真实过程和每个嫌疑人在关键时段的真实位置；同一个人同一时刻只能在一个地方。",
        "",
        "请严格按下面的 JSON 结构输出（字段名不要改，id 按 s1、s2…、c1、c2…、l1、l2… 编号）：",
        SCHEMA,
    ]
    if feedback:
        lines += ["", "上一次生成的档案没有通过检查，请修正这些问题后重新完整输出：", feedback]
    return "\n".join(lines)


# ---------------------------------------------------------------- 解析
def parse_json(text: str) -> dict:
    """从模型输出中取出第一个 JSON 对象，兼容代码块、前后多余文字和行尾逗号。"""
    t = (text or "").strip()
    t = re.sub(r"^```(?:json)?\s*|\s*```$", "", t, flags=re.M)
    start = t.find("{")
    if start < 0:
        raise ValueError("模型没有输出 JSON")
    depth = 0
    in_str = esc = False
    end = -1
    for i in range(start, len(t)):
        ch = t[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                end = i
                break
    if end < 0:
        raise ValueError("JSON 不完整（可能被截断）")
    body = t[start : end + 1]
    try:
        return json.loads(body)
    except json.JSONDecodeError:
        body = re.sub(r",\s*([}\]])", r"\1", body)
        return json.loads(body)


def _s(v) -> str:
    return "" if v is None else str(v).strip()


def normalize(case: dict) -> dict:
    """把模型输出整理成程序要用的形状：补默认值、统一类型、去掉明显的格式问题。"""
    c = dict(case)
    c["title"] = _s(c.get("title")).strip("《》") or "无名之案"
    c["intro"] = _s(c.get("intro"))
    v = c.get("victim") or {}
    c["victim"] = {"name": _s(v.get("name")) or "受害人", "identity": _s(v.get("identity")), "fate": _s(v.get("fate"))}
    c["locations"] = [_s(x) for x in (c.get("locations") or []) if _s(x)]

    sus = []
    for i, s in enumerate(c.get("suspects") or []):
        if not isinstance(s, dict):
            continue
        lies = []
        for j, l in enumerate(s.get("lies") or []):
            if isinstance(l, dict) and _s(l.get("lie")):
                lies.append(
                    {
                        "id": _s(l.get("id")) or f"l{i + 1}_{j + 1}",
                        "topic": _s(l.get("topic")),
                        "lie": _s(l.get("lie")),
                        "truth": _s(l.get("truth")),
                        "broken_by": _s(l.get("broken_by")),
                    }
                )
        sus.append(
            {
                "id": _s(s.get("id")) or f"s{i + 1}",
                "name": _s(s.get("name")) or f"嫌疑人{i + 1}",
                **{k: _s(s.get(k)) for k in ("identity", "public", "relation", "personality", "speech", "alibi", "motive", "secret", "knows")},
                "lies": lies,
            }
        )
    # 谎言 id 在全案内唯一
    seen = set()
    for s in sus:
        for l in s["lies"]:
            if l["id"] in seen:
                l["id"] = f"{s['id']}_{l['id']}"
            seen.add(l["id"])
    c["suspects"] = sus

    t = c.get("truth") or {}
    c["truth"] = {k: _s(t.get(k)) for k in ("culprit", "motive", "method", "summary")}
    # 有的模型把凶手写成名字而不是 id
    if c["truth"]["culprit"] and not any(s["id"] == c["truth"]["culprit"] for s in sus):
        for s in sus:
            if s["name"] == c["truth"]["culprit"]:
                c["truth"]["culprit"] = s["id"]

    tl = []
    for e in c.get("timeline") or []:
        if isinstance(e, dict):
            tm = _s(e.get("time"))
            m = re.match(r"^(\d{1,2})[:：](\d{2})", tm)
            if m:
                tm = f"{int(m.group(1)):02d}:{m.group(2)}"
            tl.append({"time": tm, "who": _s(e.get("who")), "where": _s(e.get("where")), "what": _s(e.get("what"))})
    c["timeline"] = sorted(tl, key=lambda e: e["time"])

    clues = []
    for i, cl in enumerate(c.get("clues") or []):
        if not isinstance(cl, dict):
            continue
        src = _s(cl.get("source")).lower() or "search"
        if src not in ("search", "testimony", "event"):
            src = "search"
        key = cl.get("key")
        clues.append(
            {
                "id": _s(cl.get("id")) or f"c{i + 1}",
                "name": _s(cl.get("name")) or f"线索{i + 1}",
                "text": _s(cl.get("text")),
                "source": src,
                "location": _s(cl.get("location")),
                "holder": _s(cl.get("holder")),
                "topic": _s(cl.get("topic")),
                "points_to": _s(cl.get("points_to")),
                "key": key is True or _s(key).lower() in ("true", "1", "是", "yes"),
                "hidden": cl.get("hidden") is True or _s(cl.get("hidden")).lower() in ("true", "1", "是", "yes"),
            }
        )
    c["clues"] = clues

    ev = c.get("event") or {}
    c["event"] = {"text": _s(ev.get("text")), "clues": [_s(x) for x in (ev.get("clues") or []) if _s(x)]}
    # 事件线索：两边写法不一致时以并集为准
    for cl in clues:
        if cl["id"] in c["event"]["clues"]:
            cl["source"] = "event"
        elif cl["source"] == "event":
            c["event"]["clues"].append(cl["id"])

    cm = c.get("climax") or {}
    c["climax"] = {"text": _s(cm.get("text")) if isinstance(cm, dict) else _s(cm)}
    c["flaws"] = [
        {"text": _s(f.get("text")), "clues": [_s(x) for x in (f.get("clues") or []) if _s(x)]}
        for f in (c.get("flaws") or [])
        if isinstance(f, dict)
    ]
    c["red_herrings"] = [
        {"clue": _s(r.get("clue")), "explain": _s(r.get("explain"))} for r in (c.get("red_herrings") or []) if isinstance(r, dict)
    ]
    c["solution"] = _s(c.get("solution"))
    return c


# ---------------------------------------------------------------- 唯一解检查
SOLVE_SYSTEM = "你是一位冷静的侦探。只根据给出的材料推理，不做额外假设。只输出 JSON。"


def blind_view(case: dict) -> str:
    """去掉真相后，玩家理论上能拿到的全部信息。"""
    lines = [f"案件：{case['title']}", case["intro"], f"受害人：{case['victim']['name']}，{case['victim']['identity']}。{case['victim']['fate']}", "", "嫌疑人："]
    for s in case["suspects"]:
        lines.append(f"- {s['name']}（{s['identity']}）：{s['public']}；与受害人：{s['relation']}；自述行踪：{s['alibi']}")
        for l in s["lies"]:
            if l["broken_by"]:
                lines.append(f"  · 被证据识破后承认：关于{l['topic']}，原说法“{l['lie']}”，实际“{l['truth']}”")
    lines += ["", "全部线索："]
    for cl in case["clues"]:
        if cl.get("hidden"):
            continue
        where = cl["location"] if cl["source"] == "search" else ("事件" if cl["source"] == "event" else f"{_name(case, cl['holder'])}的证词")
        lines.append(f"- [{where}] {cl['name']}：{cl['text']}")
    if case["event"]["text"]:
        lines += ["", f"突发事件：{case['event']['text']}"]
    return "\n".join(lines)


def solve_prompt(case: dict) -> str:
    names = "、".join(s["name"] for s in case["suspects"])
    return (
        blind_view(case)
        + f"\n\n请判断凶手是谁（只能从 {names} 中选一人），以 JSON 输出："
        + '{"culprit": "名字", "reason": "一句话理由"}'
    )


def _name(case: dict, sid: str) -> str:
    for s in case["suspects"]:
        if s["id"] == sid:
            return s["name"]
    return sid or "某人"
