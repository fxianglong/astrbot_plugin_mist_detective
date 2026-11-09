"""角色扮演模式：报名 → 发车 → 私聊角色卡 → 搜查/公开 → 推进三轮 → 投票揭晓。"""
import asyncio

import _path  # noqa: F401
from astrbot.api import AstrBotConfig
from astrbot.api.event import AstrMessageEvent as Ev

from astrbot_plugin_mist_detective import generator, roleplay
from astrbot_plugin_mist_detective.main import MistDetective
from test_flow import ev, run
from test_v04 import Ctx as Ctx4

UMO = "qq:GroupMessage:888"


class Ctx(Ctx4):
    def __init__(self):
        super().__init__()
        self.dm = {}
        self.fail_dm = set()

    async def send_message(self, umo, chain):
        if ":FriendMessage:" in umo:
            uid = umo.rsplit(":", 1)[1]
            if uid in self.fail_dm:
                raise RuntimeError("not friend")
            self.dm[uid] = chain.text
        else:
            self.sent.append(chain.text)


def pev(text, sender, name):
    e = Ev(text, private=True, sender=sender)
    e.name = name
    return e


PLAYERS = [("1", "阿福"), ("2", "小美"), ("3", "老王"), ("4", "阿珍")]


async def main():
    p_rp = generator.gen_prompt(generator.pick_skeleton(__import__("random").Random(1), diff=roleplay.rp_difficulty(5)), rp=True)
    assert "script" in p_rp and "真人玩家" in p_rp and "正好 5 个" in p_rp

    ctx = Ctx()
    ctx.fail_dm = {"4"}
    p = MistDetective(ctx, AstrBotConfig({"image_mode": False}))
    out = await run(p.rp_open(ev("案件 角色扮演 客栈")))
    print(out[0]); assert "发起了一局角色扮演" in out[0]
    assert "还差" in (await run(p.rp_start(ev("案件 发车"))))[0]
    for uid, name in PLAYERS[1:]:
        await run(p.rp_join(ev("加入", sender=uid, name=name)))
    assert "已经在名单" in (await run(p.rp_join(ev("加入", sender="2", name="小美"))))[0]
    assert "只有发起人" in (await run(p.rp_start(ev("案件 发车", sender="3", name="老王"))))[0]
    out = await run(p.rp_start(ev("案件 发车")))
    print("\n".join(out))
    g = p.storage.load(UMO)
    assert g["mode"] == "rp" and len(g["roles"]) == 4 and set(g["roles"].values()) == {"s1", "s2", "s3", "s4"}
    assert set(ctx.dm) == {"1", "2", "3"} and "阿珍" in out[-1]
    gen_p = [x for k, x in ctx.calls if k == generator.GEN_SYSTEM[:8]][-1]
    assert "真人玩家" in gen_p
    culprit_uid = next(u for u, s in g["roles"].items() if s == "s4")
    assert "你就是凶手" in ctx.dm.get(culprit_uid, "你就是凶手")
    innocent = next(u for u, s in g["roles"].items() if s != "s4" and u in ctx.dm)
    assert "你不是凶手" in ctx.dm[innocent]
    # 私聊补领角色卡
    out = await run(p.rp_card(pev("我的角色", "4", "阿珍")))
    assert "角色卡" in out[0]
    assert "私聊" in (await run(p.rp_card(ev("我的角色", sender="4"))))[0]
    # 审讯等被拦住
    assert "角色扮演局" in (await run(p.interrogate(ev("审讯 沈先生 你在哪"))))[0]
    # 搜查：每轮一次
    out = await run(p.search(ev("搜查 掌柜房间")))
    print(out[0]); assert "细绳" in out[0]
    assert "本轮已经搜查过" in (await run(p.search(ev("搜查 厨房"))))[0]
    # 公开自己掌握的线索
    xiaoliu = next(u for u, s in g["roles"].items() if s == "s3")
    out = await run(p.rp_reveal(ev("公开 c2", sender=xiaoliu, name="X")))
    print(out[0]); assert "公开了线索" in out[0]
    other = next(u for u, s in g["roles"].items() if s == "s1")
    assert "没找到" in (await run(p.rp_reveal(ev("公开 c2", sender=other))))[0]
    # 投票前不能投
    assert "还没到投票" in (await run(p.rp_vote(ev("投票 沈先生"))))[0]
    # 推进三次 → 投票
    for i in range(3):
        out = await run(p.advance(ev("案件 推进")))
        print(out[0][:40])
    g = p.storage.load(UMO)
    assert g["final"] and "c9" in g["found"]
    # 新一轮可以再搜（已进入投票也允许）
    # 投票：3 人投真凶，凶手投别人 → 侦探胜
    for uid, _ in PLAYERS:
        target = "柳三娘" if uid == culprit_uid else "沈先生"
        out = await run(p.rp_vote(ev(f"投票 {target}", sender=uid)))
    print("\n".join(out))
    assert "侦探获胜" in out[1] and p.storage.load(UMO) is None
    rows = p.storage.ranking(UMO)
    pts = {r[0]: r[1] for r in rows}
    print(pts)

    # 凶手胜：平票
    ctx2 = Ctx()
    p2 = MistDetective(ctx2, AstrBotConfig({"image_mode": False, "rp_min_players": 3}))
    await run(p2.rp_open(ev("案件 剧本杀")))
    await run(p2.rp_join(ev("加入", sender="2", name="小美")))
    await run(p2.rp_join(ev("报名", sender="3", name="老王")))
    await run(p2.rp_start(ev("案件 发车")))
    g = p2.storage.load(UMO)
    for _ in range(3):
        await run(p2.advance(ev("案件 推进")))
    sids = list(g["roles"].values())
    await run(p2.rp_vote(ev("投票 沈先生", sender="1")))
    out = await run(p2.advance(ev("案件 推进")))  # 局长提前揭晓
    print(out[0])
    assert "侦探获胜" in out[0] or "凶手胜" in out[0]
    p._task.cancel(); p2._task.cancel()


def test_main():
    asyncio.run(main())


if __name__ == "__main__":
    test_main()
    print("OK")
