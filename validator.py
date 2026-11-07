"""真相档案自检：结构完整、可解、时间线自洽、开场无剧透。

返回问题列表；空列表表示通过。问题文字会原样反馈给模型重写，所以要写得具体。
"""

from __future__ import annotations

import re

from .library import Difficulty

TIME_RE = re.compile(r"^\d{2}:\d{2}$")


def validate(case: dict, diff: Difficulty) -> list[str]:
    errs: list[str] = []
    sus = case.get("suspects") or []
    sids = {s["id"] for s in sus}
    names = [s["name"] for s in sus]
    clues = case.get("clues") or []
    cids = [c["id"] for c in clues]
    cset = set(cids)
    locs = set(case.get("locations") or [])
    culprit = case["truth"]["culprit"]

    # ---- 基本结构
    if not case.get("intro"):
        errs.append("缺少开场旁白 intro。")
    if not (3 <= len(sus) <= 6):
        errs.append(f"嫌疑人应为 {diff.suspects} 个，现在是 {len(sus)} 个。")
    if len(set(names)) != len(names):
        errs.append("嫌疑人有重名，每个人的名字必须不同。")
    if len(sids) != len(sus):
        errs.append("嫌疑人 id 重复。")
    if case["victim"]["name"] in names:
        errs.append("受害人不能同时是嫌疑人。")
    if culprit not in sids:
        errs.append(f"truth.culprit 必须是某个嫌疑人的 id，现在是“{culprit}”。")
    if not case["truth"]["method"] or not case["truth"]["summary"]:
        errs.append("truth 缺少 method 或 summary。")
    if not (4 <= len(locs) <= 8):
        errs.append("locations 应有 5~6 个地点。")
    if len(cset) != len(cids):
        errs.append("线索 id 重复。")
    if len(clues) < 6:
        errs.append(f"线索太少（{len(clues)} 张），至少需要 {8 + diff.suspects} 张。")

    # ---- 线索可获得
    for c in clues:
        if not c["text"]:
            errs.append(f"线索 {c['id']} 没有 text。")
        if c["source"] == "search" and c["location"] not in locs:
            errs.append(f"线索 {c['id']} 的地点“{c['location']}”不在 locations 里，玩家搜不到。")
        if c["source"] == "testimony" and c["holder"] not in sids:
            errs.append(f"证词线索 {c['id']} 的 holder“{c['holder']}”不是嫌疑人 id。")
        if c["points_to"] and c["points_to"] not in sids:
            errs.append(f"线索 {c['id']} 的 points_to“{c['points_to']}”不是嫌疑人 id。")
    for c in clues:
        if c.get("hidden") and c["key"]:
            errs.append(f"隐藏彩蛋线索 {c['id']} 不能是关键线索（key 应为 false）。")
        if c.get("hidden") and c["source"] != "testimony":
            errs.append(f"隐藏彩蛋线索 {c['id']} 的 source 应为 testimony。")
    if not any(c["source"] == "search" for c in clues):
        errs.append("没有任何搜查线索。")
    if not any(c["source"] == "testimony" for c in clues):
        errs.append("没有任何证词线索。")
    for x in case["event"]["clues"]:
        if x not in cset:
            errs.append(f"event.clues 里的 {x} 不存在。")

    # ---- 可解性
    if culprit in sids:
        keys = [c for c in clues if c["key"] and c["points_to"] == culprit]
        if len(keys) < diff.key_clues:
            errs.append(f"指向凶手（{culprit}）的关键线索只有 {len(keys)} 张，至少需要 {diff.key_clues} 张（key=true 且 points_to={culprit}）。")
        if all(c["source"] == "testimony" and c["holder"] == culprit for c in keys) and keys:
            errs.append("指向凶手的关键线索不能全都只由凶手本人说出。")
        cul = next(s for s in sus if s["id"] == culprit)
        if not any(l["broken_by"] for l in cul["lies"]):
            errs.append("凶手至少要有一条能被线索识破的谎言（lies 里填 broken_by）。")
    for s in sus:
        for l in s["lies"]:
            if l["broken_by"] and l["broken_by"] not in cset:
                errs.append(f"{s['name']} 的谎言 {l['id']} 的 broken_by“{l['broken_by']}”不是已有线索。")
            if l["broken_by"] and not l["truth"]:
                errs.append(f"{s['name']} 的谎言 {l['id']} 缺少 truth。")
    if not case["flaws"]:
        errs.append("缺少 flaws（诡计的破绽）。")
    for i, f in enumerate(case["flaws"], 1):
        if not f["clues"]:
            errs.append(f"第 {i} 条破绽没有对应线索。")
        for x in f["clues"]:
            if x not in cset:
                errs.append(f"第 {i} 条破绽引用的线索 {x} 不存在。")
    for r in case["red_herrings"]:
        if r["clue"] not in cset:
            errs.append(f"红鲱鱼引用的线索 {r['clue']} 不存在。")
        else:
            c = next(c for c in clues if c["id"] == r["clue"])
            if c["points_to"] == culprit:
                errs.append(f"红鲱鱼 {r['clue']} 不能指向真凶。")

    # ---- 时间线
    tl = case["timeline"]
    if len(tl) < 6:
        errs.append("时间线太短，至少 10 条。")
    at: dict[tuple[str, str], str] = {}
    for e in tl:
        if not TIME_RE.match(e["time"]):
            errs.append(f"时间线的 time“{e['time']}”不是 HH:MM 格式。")
            continue
        if e["who"] in sids and e["where"]:
            k = (e["who"], e["time"])
            if k in at and at[k] != e["where"]:
                n = next(s["name"] for s in sus if s["id"] == e["who"])
                errs.append(f"时间线矛盾：{n} 在 {e['time']} 同时出现在“{at[k]}”和“{e['where']}”。")
            at[k] = e["where"]
    if culprit in sids and not any(e["who"] == culprit for e in tl):
        errs.append("时间线里没有凶手的行动。")

    # ---- 剧透
    if culprit in sids:
        cname = next(s["name"] for s in sus if s["id"] == culprit)
        public = case["intro"] + case["victim"]["fate"] + "".join(s["public"] + s["relation"] for s in sus)
        if re.search(rf"{re.escape(cname)}[^，。]{{0,6}}(是凶手|杀了|下的毒|动的手)", public):
            errs.append("开场旁白或公开人物介绍里直接透露了凶手。")
        method = case["truth"]["method"]
        if len(method) >= 8 and method in public:
            errs.append("开场旁白里写出了作案手法。")
    return errs


def solve_matches(case: dict, answer: str) -> bool:
    """盲解得到的名字是否就是凶手。"""
    culprit = case["truth"]["culprit"]
    name = next((s["name"] for s in case["suspects"] if s["id"] == culprit), "")
    a = (answer or "").strip()
    if not a or not name:
        return False
    hits = [s for s in case["suspects"] if s["name"] in a or (a and a in s["name"])]
    return len(hits) == 1 and hits[0]["id"] == culprit
