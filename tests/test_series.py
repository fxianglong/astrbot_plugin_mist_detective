"""系列主线：开始 → 下一章（注入要求、缺主线线索会重写）→ 破案解锁碎片 → 终章完结；失败不推进。"""
import asyncio
import copy
import json

import _path  # noqa: F401
from astrbot.api import AstrBotConfig

from astrbot_plugin_mist_detective import generator, series
from astrbot_plugin_mist_detective.main import MistDetective
from fixture_case import CASE
from test_flow import Resp, ev, run
from test_v04 import Ctx as Ctx4

UMO = "qq:GroupMessage:888"


class Ctx(Ctx4):
    def __init__(self):
        super().__init__()
        self.series_gen = 0

    async def llm_generate(self, chat_provider_id, prompt, system_prompt=None, **kw):
        if system_prompt == generator.GEN_SYSTEM and "系列主线" in prompt:
            self.calls.append((system_prompt[:8], prompt))
            self.series_gen += 1
            c = copy.deepcopy(CASE)
            if "缺少系列主线线索" in prompt:  # 第二次按反馈补上
                c["clues"].append({"id": "c20", "name": "灰蛾纸片", "text": "一只旧报纸折的灰色纸蛾。", "source": "search",
                                   "location": "大堂", "points_to": "", "key": False})
            return Resp(json.dumps(c, ensure_ascii=False))
        return await super().llm_generate(chat_provider_id, prompt, system_prompt, **kw)


async def main():
    arc = series.arc_of("moth")
    assert len(arc.chapters) == 5 and all(c.fragment for c in arc.chapters)
    ctx = Ctx()
    p = MistDetective(ctx, AstrBotConfig({"image_mode": False, "vote_accuse": False}))
    out = await run(p.series_cmd(ev("案件 主线")))
    assert "主线 开始" in out[0]
    assert "还没开始主线" in (await run(p.series_cmd(ev("案件 主线 下一章"))))[0]
    out = await run(p.series_cmd(ev("案件 主线 开始")))
    print(out[0]); assert "▶ 第 1 章" in out[0]
    out = await run(p.series_cmd(ev("案件 主线 下一章")))
    print("\n".join(out)[:200])
    assert ctx.series_gen == 2 and "第 1 章" in out[-1]
    g = p.storage.load(UMO)
    assert g["series"] == {"arc": "moth", "chapter": 1} and g["meta"]["theme"] == "inn"
    gp = [x for k, x in ctx.calls if k == generator.GEN_SYSTEM[:8]][-1]
    assert "第一只" in gp
    out = await run(p.accuse(ev("指认 沈先生 复仇，下毒")))
    print(out[0]); assert "解锁的真相" in out[0] and "十三年前" in out[0] and "第七包厢" not in out[0]
    assert p.storage.get_series(UMO) == ("moth", 2, False)
    out = await run(p.series_cmd(ev("案件 主线")))
    print(out[0]); assert "✅ 第 1 章" in out[0] and "▶ 第 2 章" in out[0]
    # 第 2 章失败不推进
    await run(p.series_cmd(ev("案件 主线 下一章")))
    assert p.storage.load(UMO)["meta"]["theme"] == "shanghai"
    await run(p.accuse(ev("指认 小六")))
    out = await run(p.accuse(ev("指认 赵铁")))
    assert "纸蛾从窗缝飞走" in out[0] and p.storage.get_series(UMO) == ("moth", 2, False)
    # 终章
    p.storage.set_series(UMO, "moth", 5)
    await run(p.series_cmd(ev("案件 主线 下一章")))
    gp = [x for k, x in ctx.calls if k == generator.GEN_SYSTEM[:8]][-1]
    assert "终章" in gp and "顾雾" in gp
    out = await run(p.accuse(ev("指认 沈先生")))
    print(out[0]); assert "《灰蛾》完" in out[0]
    assert p.storage.get_series(UMO) == ("moth", 5, True)
    assert "已经完结" in (await run(p.series_cmd(ev("案件 主线 下一章"))))[0]
    assert "确认" in (await run(p.series_cmd(ev("案件 主线 重置"))))[0]
    await run(p.series_cmd(ev("案件 主线 重置 确认")))
    assert p.storage.get_series(UMO) is None
    p._task.cancel()


def test_main():
    asyncio.run(main())


if __name__ == "__main__":
    test_main()
    print("OK")
