"""v0.2：对质、投票指认、第三幕事件。"""
import asyncio, json, sys
import _path  # noqa: F401
from astrbot.api import AstrBotConfig  # noqa
from astrbot_plugin_mist_detective import engine, generator, npc  # noqa
from astrbot_plugin_mist_detective.main import MistDetective  # noqa
from test_flow import Ctx as BaseCtx, Resp, ev, run  # noqa  (test_flow 的 main 在 import 时也会跑一遍)

class Ctx(BaseCtx):
    def __init__(self):
        super().__init__(); self.gen_n = 1; self.sent = []
    async def send_message(self, umo, chain): self.sent.append(chain.text)
    async def llm_generate(self, chat_provider_id, prompt, system_prompt=None, **kw):
        if system_prompt == npc.CONFRONT_SYSTEM:
            self.calls.append(("confront", prompt))
            return Resp(json.dumps({"lines": [{"who": "柳三娘", "say": "你算老几？哼"}, {"who": "赵铁", "say": "嗯。"}],
                                    "reveal": ["c10", "c2"], "claim_a": "戌时在马厩", "claim_b": "听到摔碗声"}, ensure_ascii=False))
        return await super().llm_generate(chat_provider_id, prompt, system_prompt, **kw)

UMO = "qq:GroupMessage:888"

async def main():
    c = generator.normalize(__import__("fixture_case").CASE)
    assert c["climax"]["text"].startswith("寅时")
    ctx = Ctx(); p = MistDetective(ctx, AstrBotConfig({"image_mode": False, "vote_seconds": 15}))
    await run(p.start(ev("案件 开局")))
    # 对质前先搜到发簪 c5（可识破柳三娘谎言）
    await run(p.search(ev("搜查 马厩")))
    out = await run(p.confront(ev("对质 柳三娘 赵铁 戌时你们在哪", sender="2", name="小美")))
    print(out[0])
    g = p.storage.load(UMO)
    assert "l1" in g["broken"] and "c10" in g["found"] and "c2" not in g["found"]  # c2 不归二人
    assert "当面戳穿" in out[0] and g["pressure"]["s1"] >= 25 and g["ap"] == 6
    pr = [x for k, x in ctx.calls if k == "confront"][0]
    assert "必须改口承认：戌时去马厩见了赵铁" in pr and "金老九是山贼" not in pr
    assert "让谁和谁" in (await run(p.confront(ev("对质 柳三娘 柳三娘"))))[0]
    # 把行动点用到第三幕，检查事件
    for _ in range(14):
        out = await run(p.search(ev("搜查 大堂")))  # 第二次起无新线索不扣点，换着搜
        g = p.storage.load(UMO)
        if g["act"] == 3: break
        for loc in ["厨房", "后院柴房", "客房走廊", "掌柜房间"]:
            if g["act"] == 3: break
            await run(p.interrogate(ev("审讯 赵铁 你在哪", sender="3", name="老王")))
            g = p.storage.load(UMO)
    g = p.storage.load(UMO)
    assert g["act"] == 3, g["act"]
    # 投票：3 名玩家，提议人 1 票，再 1 票赞成即过半
    out = await run(p.accuse(ev("指认 柳三娘 她想保住客栈")))
    print(out[0]); assert "投票" in out[0]
    assert "正在投票" in (await run(p.search(ev("搜查 厨房"))))[0]
    out = await run(p.vote_no(ev("反对", sender="2", name="小美")))
    print(out[0])
    out = await run(p.vote_no(ev("反对", sender="3", name="老王")))
    print(out[0]); assert "未通过" in out[0]
    g = p.storage.load(UMO); assert "vote" not in g and g["wrong"] == []
    # 第二次：过半赞成，正确
    await run(p.accuse(ev("指认 沈先生 复仇；酒里下毒，细绳拉门闩", sender="2", name="小美")))
    out = await run(p.vote_yes(ev("赞成", sender="3", name="老王")))
    print(out[0], out[1][:40]); assert "投票通过" in out[0] and "正确" in out[1]
    assert p.storage.load(UMO) is None

    # 超时结算：计时器触发后通过 send_message 发出
    ctx2 = Ctx(); p2 = MistDetective(ctx2, AstrBotConfig({"image_mode": False, "vote_seconds": 15}))
    await run(p2.start(ev("案件 开局")))
    await run(p2.search(ev("搜查 马厩")))
    await run(p2.search(ev("搜查 厨房", sender="2", name="小美")))
    await run(p2.search(ev("搜查 大堂", sender="3", name="老王")))
    real_sleep = asyncio.sleep
    async def fast(s): await real_sleep(0)
    asyncio.sleep = fast
    try:
        await run(p2.accuse(ev("指认 小六")))
        for _ in range(20): await real_sleep(0)
    finally:
        asyncio.sleep = real_sleep
    print(ctx2.sent)
    assert ctx2.sent and "投票通过" not in ctx2.sent[0] and "未通过" in ctx2.sent[0] and "无人附议" in ctx2.sent[0]
    print("V02 OK")

def test_main():
    asyncio.run(main())


if __name__ == "__main__":
    test_main()
    print("OK")
