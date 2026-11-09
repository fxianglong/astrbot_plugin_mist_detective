"""用桩模块和模拟大模型跑通一整局：开局（含一次重写）→ 审讯 → 搜查 → 出示 → 换幕 → 提示 → 指认。"""
import asyncio
import copy
import json
import random
import sys

import _path  # noqa: F401

from astrbot.api import AstrBotConfig  # noqa: E402
from astrbot.api.event import AstrMessageEvent as Ev  # noqa: E402

from astrbot_plugin_mist_detective import engine, generator, npc, validator  # noqa: E402
from astrbot_plugin_mist_detective.library import DIFFICULTIES, STYLES, THEMES, TRICKS  # noqa: E402
from astrbot_plugin_mist_detective.main import MistDetective  # noqa: E402
from fixture_case import CASE  # noqa: E402


class Resp:
    def __init__(self, t): self.completion_text = t


class Ctx:
    """按 system prompt 区分调用类型的假模型。"""
    def __init__(self):
        self.calls = []
        self.gen_n = 0
        self.solve_answer = "沈先生"

    async def get_current_chat_provider_id(self, umo): return "default"

    async def llm_generate(self, chat_provider_id, prompt, system_prompt=None, **kw):
        self.calls.append((system_prompt[:8] if system_prompt else "", prompt))
        if system_prompt == generator.GEN_SYSTEM:
            self.gen_n += 1
            if self.gen_n == 1:  # 第一次：缺了凶手的可识破谎言，应被打回
                bad = copy.deepcopy(CASE)
                bad["suspects"][3]["lies"][0]["broken_by"] = ""
                return Resp("好的，档案如下：\n```json\n" + json.dumps(bad, ensure_ascii=False) + "\n```")
            return Resp(json.dumps(CASE, ensure_ascii=False))
        if system_prompt == generator.SOLVE_SYSTEM:
            assert "金老九是山贼" not in prompt and "真实动机" not in prompt, "盲解材料不能含真相"
            return Resp(json.dumps({"culprit": self.solve_answer, "reason": "细绳与送酒"}, ensure_ascii=False))
        if system_prompt == npc.NPC_SYSTEM:
            reveal = []
            if "c2（" in prompt and "酒" in prompt.split("问你】")[-1]:
                reveal = ["c2", "c9"]  # c9 不归小六，应被拒
            if "向你出示了证据" in prompt and "你必须改口承认" in prompt:
                return Resp(json.dumps({"reply": "（脸色煞白）这……在下只是顺手……", "pressure": 12, "reveal": [], "claim": ""}, ensure_ascii=False))
            return Resp(json.dumps({"reply": "俺、俺不知道……", "pressure": 15, "reveal": reveal, "claim": "说自己一直在下棋"}, ensure_ascii=False))
        if system_prompt == npc.JUDGE_SYSTEM:
            return Resp('{"motive": true, "method": true, "comment": "推理漂亮"}')
        if system_prompt == npc.CONFESS_SYSTEM:
            return Resp("二十年了，在下终于等到这一天。")
        if system_prompt == npc.BREAKDOWN_SYSTEM:
            return Resp("别、别逼俺了！俺攒了钱想逃……")
        if system_prompt == npc.WRONG_SYSTEM:
            return Resp("雪停了，真凶悄悄收起了一截麻绳。")
        return Resp("……")


async def run(gen):
    return [x async for x in gen]


def ev(text, sender="1", name="阿福"):
    e = Ev(text, private=False, sender=sender)
    e.unified_msg_origin = "qq:GroupMessage:888"
    e.name = name
    return e


async def main():
    # ---------------- 纯函数
    c = generator.normalize(CASE)
    assert c["title"] == "风雪客栈的最后一壶酒"
    assert validator.validate(c, DIFFICULTIES["normal"]) == [], validator.validate(c, DIFFICULTIES["normal"])
    bad = copy.deepcopy(c)
    bad["timeline"].append({"time": "20:55", "who": "s4", "where": "大堂", "what": "x"})
    bad["clues"][0]["location"] = "地窖"
    bad["clues"][2]["key"] = bad["clues"][8]["key"] = False
    errs = validator.validate(bad, DIFFICULTIES["normal"])
    assert any("时间线矛盾" in e for e in errs) and any("地窖" in e for e in errs) and any("关键线索只有 2 张" in e for e in errs), errs
    assert validator.solve_matches(c, "凶手是沈先生") and not validator.solve_matches(c, "小六")
    assert generator.parse_json('xx {"a": [1,2,], "b": "}"} yy') == {"a": [1, 2], "b": "}"}
    rng = random.Random(1)
    combos = {(sk.theme.key, sk.trick.key) for sk in (generator.pick_skeleton(rng) for _ in range(60))}
    assert len(combos) > 12
    for t in THEMES.values():
        for tr in TRICKS.values():
            p = generator.gen_prompt(generator.Skeleton(t, tr, STYLES["comedy"], DIFFICULTIES["hard"], 0))
            assert "5 个" in p and tr.name in p and "没有人真的死去" in p
    print("pure ok; prompt length", len(p))

    # ---------------- 对局
    ctx = Ctx()
    plug = MistDetective(ctx, AstrBotConfig({"image_mode": False, "vote_accuse": False}))
    out = await run(plug.start(ev("案件 开局 客栈 本格")))
    print("\n".join(out))
    assert ctx.gen_n == 2 and "嫌疑人：" in out[-1]
    gp = [p for s_, p in ctx.calls if s_ == generator.GEN_SYSTEM[:8]]
    assert "上一次生成的档案没有通过检查" in gp[1] and "凶手至少要有一条" in gp[1]
    assert "已有进行中" in (await run(plug.start(ev("案件 开局"))))[0]

    out = await run(plug.interrogate(ev("审讯 小六 那壶酒是谁端走的")))
    print(out[0])
    g = plug.storage.load("qq:GroupMessage:888")
    assert g["found"] == ["c2"], g["found"]  # c9 被拒
    assert g["ap"] == 7

    out = await run(plug.interrogate(ev("审讯 3号 嗯")))
    assert "要审讯谁" in out[0]
    out = await run(plug.interrogate(ev("审讯 小六")))
    assert "要问小六什么" in out[0]

    out = await run(plug.search(ev("搜查 掌柜", sender="2", name="小美")))
    print(out[0])
    out = await run(plug.search(ev("搜查 地窖")))
    assert "要搜查哪里" in out[0]

    out = await run(plug.present(ev("出示 c2 沈先生 你怎么解释")))
    print(out[0])
    g = plug.storage.load("qq:GroupMessage:888")
    assert "l4" in g["broken"] and g["pressure"]["s4"] >= 42

    # 提示：此时应指向未搜的关键线索（客房走廊的麻绳）
    out = await run(plug.hint(ev("提示")))
    print(out[0])
    assert "客房走廊" in out[0]
    await run(plug.note(ev("笔记 细绳和书箱的绳子可能一样")))

    # 把行动点耗到第二幕：反复审讯小六直到崩溃
    for _ in range(6):
        out = await run(plug.interrogate(ev("审讯 小六 你那晚在干嘛", sender="3", name="老王")))
    print(out[0])
    g = plug.storage.load("qq:GroupMessage:888")
    assert g["act"] == 2 and "c9" in g["found"] and "c7" in g["found"], (g["act"], g["found"])
    assert "s3" in g["broke_down"]
    assert "c4" in g["found"]  # 崩溃时说出所有证词

    out = await run(plug.dossier(ev("案件 卷宗")))
    print(out[0])
    assert "已识破的谎言" in out[0] and "细绳" in out[0]

    # 错一次
    out = await run(plug.accuse(ev("指认 柳三娘")))
    print(out[0])
    assert "还剩 1 次" in out[0]
    # 指认正确
    out = await run(plug.accuse(ev("指认 沈先生 为父报仇，酒里下毒再用细绳拉门闩伪造密室", sender="2", name="小美")))
    print("\n".join(out))
    assert "正确" in out[0] and "动机✅" in out[0]
    assert plug.storage.load("qq:GroupMessage:888") is None
    rk = await run(plug.ranking(ev("案件 排行")))
    print(rk[0])
    assert "小美" in rk[0] and "破案 1/1" in rk[0]
    assert ("qq:GroupMessage:888".startswith("qq"))

    # ---------------- 生成失败 & 盲解不一致 & 错案
    ctx2 = Ctx()
    ctx2.gen_n = 1  # 直接给好档案
    ctx2.solve_answer = "柳三娘"
    plug2 = MistDetective(ctx2, AstrBotConfig({"image_mode": False, "gen_attempts": 2}))
    out = await run(plug2.start(ev("案件 开局")))
    assert "没能写出" in out[-1] and "歧义" in out[-1], out
    gen_prompts = [p for s, p in ctx2.calls if s == generator.GEN_SYSTEM[:8]]
    assert "只看线索的侦探推出的凶手是“柳三娘”" in gen_prompts[-1]

    ctx3 = Ctx(); ctx3.gen_n = 1
    plug3 = MistDetective(ctx3, AstrBotConfig({"image_mode": False, "vote_accuse": False}))
    await run(plug3.start(ev("案件 开局 喜剧")))
    g = plug3.storage.load("qq:GroupMessage:888")
    assert g["meta"]["style"] == "comedy"
    await run(plug3.accuse(ev("指认 小六")))
    out = await run(plug3.accuse(ev("指认 赵铁")))
    print("\n".join(out)[:300])
    assert "错案" in out[0] and "真相" in out[1]
    out = await run(plug3.abandon(ev("案件 结束")))
    assert "没有进行中" in out[0]

    # 放弃需确认
    ctx4 = Ctx(); ctx4.gen_n = 1
    plug4 = MistDetective(ctx4, AstrBotConfig({"image_mode": False}))
    await run(plug4.start(ev("案件 开局 地狱")))
    assert plug4.storage.load("qq:GroupMessage:888")["meta"]["diff"] == "hard"
    assert "确认" in (await run(plug4.abandon(ev("案件 结束"))))[0]
    out = await run(plug4.abandon(ev("案件 结束 确认")))
    assert "放弃" in out[0] and "真相" in out[1]
    out = await run(plug4.start(ev("案件 开局 火星")))
    assert "没认出" in out[0]
    print("ALL OK")


def test_main():
    asyncio.run(main())


if __name__ == "__main__":
    test_main()
    print("OK")
