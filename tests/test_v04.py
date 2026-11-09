"""v0.3/v0.4：图片卷宗、彩蛋、自定义题材、私下推理、评分/案件库/重玩、称号、局长推进、悬案之夜、每日上限、关闭题材。"""
import asyncio, json, random, sys, os
from datetime import datetime
import _path  # noqa: F401
from astrbot.api import AstrBotConfig  # noqa
from astrbot.api.event import AstrMessageEvent as Ev  # noqa
from astrbot_plugin_mist_detective import engine, generator, npc, library  # noqa
from astrbot_plugin_mist_detective.main import MistDetective, CN_TZ  # noqa
from test_flow import Resp, run, ev  # noqa
from test_v02 import Ctx as Ctx2  # noqa

UMO = "qq:GroupMessage:888"


class Ctx(Ctx2):
    def __init__(self):
        super().__init__()
        self.review_ok = True

    async def llm_generate(self, chat_provider_id, prompt, system_prompt=None, **kw):
        if system_prompt == npc.REVIEW_SYSTEM:
            self.calls.append(("review", prompt))
            return Resp(json.dumps({"ok": self.review_ok, "reason": "涉及真实人物"}, ensure_ascii=False))
        if system_prompt == npc.PRIVATE_SYSTEM:
            ok = "沈先生" in prompt.split("玩家的推理：")[-1]
            return Resp(json.dumps({"culprit": ok, "motive": ok, "method": False}))
        if system_prompt == npc.NPC_SYSTEM and "问你】你的刀" in prompt:
            assert "只有侦探的问题明确问到“他的刀”" in prompt
            return Resp(json.dumps({"reply": "嗯……这刀鞘里，是俺娘的信。", "pressure": 2, "reveal": ["c13"], "claim": ""}, ensure_ascii=False))
        return await super().llm_generate(chat_provider_id, prompt, system_prompt, **kw)


def pev(text, sender="1", name="阿福"):
    e = Ev(text, private=True, sender=sender)
    e.name = name
    return e


async def main():
    # ---------- 内容扩充
    assert len(library.THEMES) == 10 and len(library.TRICKS) == 12
    for t in library.THEMES.values():
        for tr in library.TRICKS.values():
            p = generator.gen_prompt(generator.Skeleton(t, tr, library.STYLES["honkaku"], library.DIFFICULTIES["normal"], 0))
            assert "hidden" in p and t.name in p and tr.name in p
    ct = library.custom_theme("1920 年代横渡大西洋的远洋邮轮")
    assert "按题材自拟" in generator.gen_prompt(generator.Skeleton(ct, library.TRICKS["clock"], library.STYLES["social"], library.DIFFICULTIES["easy"], 0))
    rng = random.Random(3)
    sks = [generator.pick_skeleton(rng, disabled_themes={"station", "cyber"}, disabled_tricks={"delayed"}) for _ in range(80)]
    assert not any(s.theme.key in ("station", "cyber") or s.trick.key == "delayed" for s in sks)
    c = generator.normalize(__import__("fixture_case").CASE)
    assert any(x["hidden"] for x in c["clues"]) and "刀鞘" not in generator.blind_view(c)
    bad = json.loads(json.dumps(c)); bad["clues"][-2]["key"] = True
    from astrbot_plugin_mist_detective.validator import validate
    assert any("彩蛋" in e for e in validate(bad, library.DIFFICULTIES["normal"]))

    # ---------- 图片模式开局 + 彩蛋 + 卷宗图 + 局长推进 + 私下推理 + 结案图
    ctx = Ctx(); p = MistDetective(ctx, AstrBotConfig({"vote_accuse": False}))
    out = await run(p.start(ev("案件 开局 长安")))
    print(out)
    assert out[1].startswith("[图片:") and "开局" in out[2]
    g = p.storage.load(UMO)
    assert g["host"] == "1" and g["meta"]["theme"] == "changan"
    out = await run(p.interrogate(ev("审讯 赵铁 你的刀", sender="2", name="小美")))
    print(out[0]); assert "彩蛋" in out[0]
    g = p.storage.load(UMO); assert g["eggs"] == 1 and g["players"]["2"]["pts"] >= 10
    out = await run(p.dossier(ev("案件 卷宗")))
    assert out[0].startswith("[图片:")
    html = open(p.rendered[-1]).read(); assert "刀鞘里的家书" in html and "长安卷宗" not in html  # 线索墙没有印章
    out = await run(p.dossier(ev("案件 卷宗 文字")))
    assert "卷宗" in out[0] and not out[0].startswith("[图片")
    assert "只有局长" in (await run(p.advance(ev("案件 推进", sender="2", name="小美"))))[0]
    out = await run(p.advance(ev("案件 推进")))
    print(out[0]); assert "第二幕" in out[0]
    # 私聊推理
    assert "请私聊" in (await run(p.private_reason(ev("推理 沈先生")))) [0]
    out = await run(p.private_reason(pev("推理 凶手是沈先生，他在酒里下毒", sender="2", name="小美")))
    print(out[0]); assert "已记下" in out[0]
    assert "还没有参与" in (await run(p.private_reason(pev("推理 柳三娘", sender="9"))))[0]
    await run(p.private_reason(pev("推理 我猜是柳三娘", sender="1")))
    out = await run(p.accuse(ev("指认 沈先生 复仇，下毒")))
    print("\n".join(out))
    assert "私下推理揭晓" in out[0] and "小美：凶手✅" in out[0] and "阿福：凶手❌" in out[0]
    assert out[1].startswith("[图片:") and "评分" in out[2]
    html = open(p.rendered[-1]).read(); assert "当 晚 时 间 线" in html and "已结案" in html
    # ---------- 评分 / 案件库 / 重玩
    out = await run(p.rate(ev("案件 评分 5")))
    print(out[0]); assert "5 星" in out[0]
    await run(p.rate(ev("案件 评分 4", sender="2", name="小美")))
    out = await run(p.library_(ev("案件 案件库")))
    print(out[0]); assert "#1" in out[0] and "★4.5" in out[0]
    # 另一个群重玩
    e2 = ev("案件 重玩 1", sender="7", name="路人"); e2.unified_msg_origin = "qq:GroupMessage:999"
    out = await run(p.replay(e2))
    print(out[0][:30]); assert "重玩精品案件 #1" in out[0]
    g2 = p.storage.load("qq:GroupMessage:999")
    assert g2["meta"]["replay_of"] == 1 and g2["case"]["title"] == "风雪客栈的最后一壶酒" and g2["found"] == []
    assert ctx.gen_n == 2  # 重玩不调用生成
    e3 = ev("案件 结束 确认", sender="7"); e3.unified_msg_origin = "qq:GroupMessage:999"
    await run(p.abandon(e3))
    e4 = ev("案件 评分 3", sender="7"); e4.unified_msg_origin = "qq:GroupMessage:999"
    await run(p.rate(e4))
    out = await run(p.library_(ev("案件 案件库")))
    print(out[0]); assert "玩过 2 次" in out[0] and "（3 人）" in out[0]
    # ---------- 称号
    out = await run(p.ranking(ev("案件 排行")))
    print(out[0])
    # ---------- 自定义题材
    ctx.review_ok = False
    out = await run(p.start(ev("案件 开局 自定义 某明星的生日派对")))
    assert "不太合适" in out[0]
    assert "不适合" in (await run(p.start(ev("案件 开局 自定义 小学生春游"))))[0]
    assert "群友的名字" in (await run(p.start(ev("案件 开局 自定义 小美的远洋邮轮之旅"))))[0]
    ctx.review_ok = True
    out = await run(p.start(ev("案件 开局 自定义 1920 年代横渡大西洋的远洋邮轮 喜剧"))); print("CUSTOM", out)
    g = p.storage.load(UMO)
    assert g["meta"]["theme"] == "custom" and "1920" in g["meta"]["theme_name"]
    gp = [x for k, x in ctx.calls if k == generator.GEN_SYSTEM[:8]][-1]
    assert "远洋邮轮" in gp
    await run(p.abandon(ev("案件 结束 确认")))
    # ---------- 每日上限
    p.config["daily_limit"] = 2
    out = await run(p.start(ev("案件 开局")))
    print(out[0]); assert "已经开了 2 局" in out[0]
    p.config["daily_limit"] = 0
    # ---------- 悬案之夜
    assert "已订阅" in (await run(p.subscribe(ev("案件 订阅 周三 20:30"))))[0]
    assert p.storage.sub_of(UMO) == (2, "20:30")
    now = datetime(2026, 11, 11, 20, 40, tzinfo=CN_TZ)  # 周三
    await p._tick(now)
    for _ in range(30): await asyncio.sleep(0)
    await asyncio.sleep(0.05)
    print(ctx.sent[-3:])
    assert any("悬案之夜" in s for s in ctx.sent) and any(s.startswith("[图片:") for s in ctx.sent)
    g = p.storage.load(UMO); assert g and g["host"] == ""
    n = len(ctx.sent); await p._tick(now); await asyncio.sleep(0.05)
    assert len(ctx.sent) == n  # 同一天不重复
    assert "已取消" in (await run(p.unsubscribe(ev("案件 退订"))))[0]
    # 管理员可推进无局长的局
    e = ev("案件 推进"); e.is_admin = lambda: True
    assert "推进" in (await run(p.advance(e)))[0]
    # ---------- 插画（无 key 不生成；有 key 时调用）
    assert not p.illustrator.enabled
    p.illustrator.api_key = "k"
    async def fake_draw(prompt, name):
        assert "唐代" in prompt or "悬疑" in prompt
        return "/tmp/art.png"
    p.illustrator.draw = fake_draw
    await run(p.abandon(ev("案件 结束 确认")))
    out = await run(p.start(ev("案件 开局 长安")))
    assert out[-1] == "[图片:/tmp/art.png]", out
    p._task.cancel()
    print("V04 OK")


def test_main():
    asyncio.run(main())


if __name__ == "__main__":
    test_main()
    print("OK")
