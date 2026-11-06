import asyncio
import random
import time
from pathlib import Path

from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star, StarTools, register

from . import engine, npc
from .generator import GEN_SYSTEM, SOLVE_SYSTEM, gen_prompt, normalize, parse_json, pick_skeleton, solve_prompt
from .library import DIFFICULTIES, STYLES, THEMES, match_difficulty, match_style, match_theme
from .storage import Storage
from .validator import solve_matches, validate

PLUGIN_NAME = "astrbot_plugin_mist_detective"

HELP = """🕯 雾夜侦探社 · AI 推理游戏
群友一起审讯嫌疑人、搜查现场、出示证据，在行动点用完前找出真凶。每个案件都由 AI 现场生成。

开局：/案件 开局 [题材] [风格] [难度]
  例：/案件 开局　/案件 开局 客栈 社会派 困难
  题材、风格、难度都可省略，发 /案件 题材 查看全部
调查（每次消耗 1 个行动点，全群共用）：
  /审讯 名字 问题　　例：/审讯 沈先生 你昨晚戌时在哪
  /搜查 地点　　　　例：/搜查 厨房
  /出示 线索编号 名字　例：/出示 c3 柳三娘
结案：/指认 名字 动机和手法（说中动机、手法有额外分）
其他：/案件 卷宗｜/提示（扣 5 分）｜/笔记 内容｜/案件 排行｜/案件 结束 确认"""


class GenFailed(Exception):
    pass


@register(PLUGIN_NAME, "fxianglong", "雾夜侦探社：AI 现场生成剧本，群友一起审讯、搜证、指认真凶的推理游戏", "0.1.0")
class MistDetective(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config
        try:
            data_dir = Path(StarTools.get_data_dir(PLUGIN_NAME))
        except Exception:
            data_dir = Path("data") / "plugin_data" / PLUGIN_NAME
        data_dir.mkdir(parents=True, exist_ok=True)
        self.storage = Storage(data_dir / "detective.db")
        self._busy: set[str] = set()
        self._rng = random.Random()

    async def terminate(self):
        self.storage.close()

    # ------------------------------------------------------------ 工具
    @staticmethod
    def _args(event: AstrMessageEvent, *heads: str) -> str:
        """取指令后面的全部文字（允许包含空格）。"""
        t = (event.message_str or "").strip().lstrip("/").strip()
        for h in heads:
            if t.startswith(h):
                t = t[len(h):].strip()
                break
        return t

    @staticmethod
    def _who(event: AstrMessageEvent) -> tuple[str, str]:
        uid = str(event.get_sender_id())
        try:
            name = event.get_sender_name() or uid
        except Exception:
            name = uid
        return uid, name

    def _cfg_int(self, key: str, default: int) -> int:
        try:
            return int(self.config.get(key, default) or default)
        except (TypeError, ValueError):
            return default

    async def _llm(self, kind: str, umo: str, prompt: str, system: str, timeout: int) -> str:
        pid = str(self.config.get(f"{kind}_provider_id", "") or "").strip()
        if not pid:
            pid = await self.context.get_current_chat_provider_id(umo)
        resp = await asyncio.wait_for(
            self.context.llm_generate(chat_provider_id=pid, prompt=prompt, system_prompt=system), timeout=timeout
        )
        return (getattr(resp, "completion_text", "") or "").strip()

    def _active(self, umo: str) -> tuple[dict | None, str]:
        """取进行中的对局；闲置超时的自动归档，并返回一段说明。"""
        game = self.storage.load(umo)
        if not game:
            return None, ""
        idle = self._cfg_int("idle_hours", 48) * 3600
        if idle > 0 and time.time() - game.get("updated", 0) > idle:
            self.storage.finish(umo, game, "expired", 0)
            cul = engine.suspect(game, game["case"]["truth"]["culprit"])
            return None, f"上一个案件《{game['case']['title']}》闲置太久，已归档。真凶是 {cul['name'] if cul else '?'}。"
        return game, ""

    async def _need_game(self, event: AstrMessageEvent):
        game, note = self._active(event.unified_msg_origin)
        if not game:
            return None, (note + "\n" if note else "") + "现在没有进行中的案件。发 /案件 开局 开始一局。"
        return game, ""

    def _suspect_list(self, game: dict) -> str:
        return "，".join(f"{i}.{s['name']}" for i, s in enumerate(engine.suspects(game), 1))

    # ------------------------------------------------------------ 生成
    async def _generate(self, umo: str, sk) -> dict:
        timeout = self._cfg_int("gen_timeout", 240)
        attempts = max(1, self._cfg_int("gen_attempts", 3))
        verify = bool(self.config.get("verify_solvable", True))
        feedback = ""
        last_err = ""
        for i in range(attempts):
            try:
                text = await self._llm("gen", umo, gen_prompt(sk, feedback), GEN_SYSTEM, timeout)
            except asyncio.TimeoutError:
                last_err = "模型响应超时，可以在插件配置里调大生成超时"
                continue
            except Exception as e:
                last_err = f"模型调用失败：{e}"
                logger.warning(f"[侦探社] 第 {i + 1} 次生成调用失败：{e}")
                continue
            try:
                case = normalize(parse_json(text))
            except Exception as e:  # 解析失败
                last_err = f"档案格式错误：{e}"
                feedback = "输出不是合法的 JSON，请只输出一个完整的 JSON 对象。"
                logger.warning(f"[侦探社] 第 {i + 1} 次生成解析失败：{e}")
                continue
            errs = validate(case, sk.diff)
            if errs:
                last_err = errs[0]
                feedback = "\n".join(f"- {e}" for e in errs[:12])
                logger.info(f"[侦探社] 第 {i + 1} 次生成未通过：{errs}")
                continue
            if verify:
                try:
                    ans = parse_json(await self._llm("gen", umo, solve_prompt(case), SOLVE_SYSTEM, 120)).get("culprit", "")
                except Exception as e:
                    logger.warning(f"[侦探社] 盲解检查失败，跳过：{e}")
                    ans = None
                if ans is not None and not solve_matches(case, str(ans)):
                    cul = engine.suspect({"case": case}, case["truth"]["culprit"])
                    last_err = "线索有歧义，推不出唯一凶手"
                    feedback = (
                        f"- 只看线索的侦探推出的凶手是“{ans}”，而真凶是 {cul['name']}。线索有歧义：请加强指向 {cul['name']} 的关键线索，"
                        f"让破绽更明确，并确保对“{ans}”的怀疑能被某条线索合理解释掉。"
                    )
                    logger.info(f"[侦探社] 第 {i + 1} 次生成盲解不一致：{ans}")
                    continue
            return case
        raise GenFailed(last_err or "未知原因")

    # ------------------------------------------------------------ 指令：案件
    @filter.command_group("案件")
    def case_group(self):
        pass

    @case_group.command("帮助", alias={"help"})
    async def help_(self, event: AstrMessageEvent):
        yield event.plain_result(HELP)

    @case_group.command("题材", alias={"列表"})
    async def themes(self, event: AstrMessageEvent):
        lines = ["📚 题材："]
        lines += [f"· {t.name}（{'/'.join(t.aliases[:3])}）：{t.mood}" for t in THEMES.values()]
        lines += ["", "🎭 风格："]
        lines += [f"· {s.name}：{s.guide.split('：', 1)[1][:40]}…" for s in STYLES.values()]
        lines += ["", "⚙️ 难度：" + "｜".join(f"{d.name} {d.suspects} 名嫌疑人" for d in DIFFICULTIES.values())]
        lines += ["", "例：/案件 开局 民国 社会派 困难。不写就随机题材、本格、标准。"]
        yield event.plain_result("\n".join(lines))

    @case_group.command("开局", alias={"开始", "新案"})
    async def start(self, event: AstrMessageEvent):
        umo = event.unified_msg_origin
        game, note = self._active(umo)
        if game:
            yield event.plain_result(f"本群已有进行中的案件《{game['case']['title']}》。发 /案件 卷宗 查看进度，或 /案件 结束 确认 放弃本案。")
            return
        if umo in self._busy:
            yield event.plain_result("卷宗正在整理中，请稍等。")
            return
        theme = style = diff = None
        for w in self._args(event, "案件").split()[1:]:
            if (t := match_theme(w)) and not theme:
                theme = t
            elif (s := match_style(w)) and not style:
                style = s
            elif (d := match_difficulty(w)) and not diff:
                diff = d
            else:
                yield event.plain_result(f"没认出“{w}”。发 /案件 题材 查看可选的题材、风格和难度。")
                return
        if style is None:
            style = match_style(str(self.config.get("default_style", "本格") or "本格")) or STYLES["honkaku"]
        sk = pick_skeleton(self._rng, theme, style, diff, avoid=self.storage.recent_combos(umo))
        self._busy.add(umo)
        try:
            yield event.plain_result(
                (note + "\n" if note else "")
                + f"🕯 雾夜侦探社接到一桩新案子（{sk.theme.name}｜{sk.style.name}｜{sk.diff.name}）。\n卷宗整理中，大约需要一两分钟……"
            )
            try:
                case = await self._generate(umo, sk)
            except GenFailed as e:
                yield event.plain_result(f"这次没能写出一桩靠谱的案子（{e}）。再发一次 /案件 开局 试试。")
                return
            except Exception as e:
                logger.error(f"[侦探社] 生成失败：{e}")
                yield event.plain_result(f"生成案件时出错：{e}")
                return
            game = engine.new_game(case, sk)
            self.storage.save(umo, game)
            yield event.plain_result(engine.opening(game))
        finally:
            self._busy.discard(umo)

    @case_group.command("卷宗", alias={"进度", "状态"})
    async def dossier(self, event: AstrMessageEvent):
        game, msg = await self._need_game(event)
        yield event.plain_result(engine.dossier(game) if game else msg)

    @case_group.command("排行", alias={"排行榜", "榜单"})
    async def ranking(self, event: AstrMessageEvent):
        umo = event.unified_msg_origin
        rows = self.storage.ranking(umo)
        total, solved = self.storage.stats(umo)
        if not rows:
            yield event.plain_result("还没有结案记录。")
            return
        lines = [f"🏆 侦探排行（本群共破案 {solved}/{total}）"]
        for i, (name, pts, sv, gs) in enumerate(rows, 1):
            lines.append(f"{i}. {name}｜{engine.title_of(sv)}｜{pts} 分｜破案 {sv}/{gs}")
        yield event.plain_result("\n".join(lines))

    @case_group.command("结束", alias={"放弃"})
    async def abandon(self, event: AstrMessageEvent):
        umo = event.unified_msg_origin
        game, msg = await self._need_game(event)
        if not game:
            yield event.plain_result(msg)
            return
        if "确认" not in self._args(event, "案件"):
            yield event.plain_result(f"确定放弃《{game['case']['title']}》并公布真相吗？发 /案件 结束 确认")
            return
        if umo in self._busy:
            yield event.plain_result("正在处理上一个行动，请稍等。")
            return
        self.storage.finish(umo, game, "abandoned", 0)
        yield event.plain_result("案件已放弃。\n\n" + engine.truth_text(game))

    # ------------------------------------------------------------ 指令：调查
    async def _act_guard(self, event: AstrMessageEvent, allow_final: bool = False):
        game, msg = await self._need_game(event)
        if not game:
            return None, msg
        if game["final"] and not allow_final:
            return None, "行动点已经用完了，现在只能 /指认 名字。"
        if event.unified_msg_origin in self._busy:
            return None, "正在处理上一个行动，请稍等。"
        return game, ""

    async def _breakdown(self, umo: str, game: dict, s: dict, uid: str) -> str:
        engine.credit(game, uid, engine.PTS_BREAKDOWN)
        try:
            mono = await self._llm("npc", umo, npc.breakdown_prompt(game, s), npc.BREAKDOWN_SYSTEM, 60)
        except Exception:
            mono = ""
        new = engine.give_clues(game, [c["id"] for c in engine.testimony_pool(game, s["id"])], uid)
        lines = [f"💥 {s['name']}的情绪崩溃了！", mono or f"（{s['name']}终于说出了藏在心里的事）", f"秘密：{s['secret']}"]
        if new:
            lines.append("📌 新线索：\n" + "\n".join(engine.clue_line(c) for c in new))
        return "\n".join(lines)

    @filter.command("审讯", alias={"审问", "询问"})
    async def interrogate(self, event: AstrMessageEvent):
        umo = event.unified_msg_origin
        game, msg = await self._act_guard(event)
        if not game:
            yield event.plain_result(msg)
            return
        s, question = engine.split_target(game, self._args(event, "审讯", "审问", "询问"))
        if not s:
            yield event.plain_result(f"要审讯谁？{self._suspect_list(game)}\n例：/审讯 {engine.suspects(game)[0]['name']} 案发时你在哪")
            return
        if not question:
            yield event.plain_result(f"要问{s['name']}什么？例：/审讯 {s['name']} 你和死者是什么关系")
            return
        uid, name = self._who(event)
        self._busy.add(umo)
        try:
            try:
                out = npc.parse_npc(await self._llm("npc", umo, npc.npc_prompt(game, s, name, question), npc.NPC_SYSTEM, self._cfg_int("npc_timeout", 60)))
            except Exception as e:
                logger.warning(f"[侦探社] 审讯调用失败：{e}")
                yield event.plain_result(f"（{s['name']}沉默不语）模型调用失败，本次不消耗行动点。")
                return
            engine.touch(game, uid, name)
            new = engine.accept_reveal(game, s["id"], out["reveal"], uid)
            broke = engine.add_pressure(game, s["id"], out["pressure"])
            engine.record(game, s["id"], name, question, out["reply"], out["claim"])
            lines = [f"🗣 {s['name']}：{out['reply']}", f"紧张度 {engine.pressure_bar(game['pressure'][s['id']])}"]
            if new:
                lines.append("📌 新线索：\n" + "\n".join(engine.clue_line(c) for c in new))
            if broke:
                lines.append(await self._breakdown(umo, game, s, uid))
            lines += engine.spend(game)
            lines.append(engine.status_line(game))
            self.storage.save(umo, game)
            yield event.plain_result("\n".join(lines))
        finally:
            self._busy.discard(umo)

    @filter.command("搜查", alias={"搜", "调查"})
    async def search(self, event: AstrMessageEvent):
        umo = event.unified_msg_origin
        game, msg = await self._act_guard(event)
        if not game:
            yield event.plain_result(msg)
            return
        loc = engine.find_location(game, self._args(event, "搜查", "搜", "调查"))
        if not loc:
            locs = game["case"]["locations"]
            yield event.plain_result("要搜查哪里？" + "，".join(f"{i}.{l}" for i, l in enumerate(locs, 1)))
            return
        searched = game.setdefault("searched", [])
        remaining = [c for c in game["case"]["clues"] if c["source"] == "search" and c["location"] == loc and c["id"] not in game["found"]]
        if loc in searched and not remaining:
            yield event.plain_result(f"{loc}已经被翻了个遍，没有新的发现了（不消耗行动点）。")
            return
        uid, name = self._who(event)
        engine.touch(game, uid, name)
        new = engine.search(game, loc, uid)
        if loc not in searched:
            searched.append(loc)
        if new:
            lines = [f"🔎 {name}搜查了{loc}，发现："] + [engine.clue_line(c) for c in new]
        else:
            lines = [f"🔎 {name}把{loc}仔细搜了一遍，没有发现可疑的东西。"]
        lines += engine.spend(game)
        lines.append(engine.status_line(game))
        self.storage.save(umo, game)
        yield event.plain_result("\n".join(lines))

    @filter.command("出示", alias={"举证"})
    async def present(self, event: AstrMessageEvent):
        umo = event.unified_msg_origin
        game, msg = await self._act_guard(event)
        if not game:
            yield event.plain_result(msg)
            return
        parts = self._args(event, "出示", "举证").split(maxsplit=2)
        c = s = None
        extra = ""
        if len(parts) >= 2:
            c = engine.find_found_clue(game, parts[0])
            if c:
                s, extra = engine.split_target(game, " ".join(parts[1:]))
            else:
                s = engine.find_suspect(game, parts[0])
                c = engine.find_found_clue(game, parts[1])
                extra = parts[2] if len(parts) > 2 else ""
        if not c or not s:
            found = "、".join(game["found"]) or "暂无"
            yield event.plain_result(f"用法：/出示 线索编号 名字，例：/出示 c3 {engine.suspects(game)[0]['name']}\n已获得的线索：{found}\n嫌疑人：{self._suspect_list(game)}")
            return
        uid, name = self._who(event)
        lies = engine.lies_broken_by(game, s["id"], c["id"])
        self._busy.add(umo)
        try:
            try:
                prompt = npc.npc_prompt(game, s, name, extra, presented=c, broken=lies)
                out = npc.parse_npc(await self._llm("npc", umo, prompt, npc.NPC_SYSTEM, self._cfg_int("npc_timeout", 60)))
            except Exception as e:
                logger.warning(f"[侦探社] 出示调用失败：{e}")
                yield event.plain_result(f"（{s['name']}盯着证据一言不发）模型调用失败，本次不消耗行动点。")
                return
            engine.touch(game, uid, name)
            engine.mark_broken(game, lies, uid)
            bonus = 30 if lies else (10 if c["points_to"] == s["id"] else 0)
            broke = engine.add_pressure(game, s["id"], out["pressure"] + bonus)
            new = engine.accept_reveal(game, s["id"], out["reveal"], uid)
            claim = lies[0]["truth"][:30] if lies else out["claim"]
            engine.record(game, s["id"], name, f"（出示{c['name']}）{extra}", out["reply"], claim)
            lines = [f"🧾 {name}向{s['name']}出示了【{c['id']}】{c['name']}", f"🗣 {s['name']}：{out['reply']}"]
            if lies:
                lines.append("💡 谎言被识破！" + "；".join(f"{s['name']}承认：{l['truth']}" for l in lies))
            lines.append(f"紧张度 {engine.pressure_bar(game['pressure'][s['id']])}")
            if new:
                lines.append("📌 新线索：\n" + "\n".join(engine.clue_line(x) for x in new))
            if broke:
                lines.append(await self._breakdown(umo, game, s, uid))
            lines += engine.spend(game)
            lines.append(engine.status_line(game))
            self.storage.save(umo, game)
            yield event.plain_result("\n".join(lines))
        finally:
            self._busy.discard(umo)

    @filter.command("提示")
    async def hint(self, event: AstrMessageEvent):
        game, msg = await self._need_game(event)
        if not game:
            yield event.plain_result(msg)
            return
        text = engine.hint(game)
        self.storage.save(event.unified_msg_origin, game)
        yield event.plain_result(f"{text}\n（本案已用提示 {game['hints']} 次，每次扣 5 分）")

    @filter.command("笔记")
    async def note(self, event: AstrMessageEvent):
        game, msg = await self._need_game(event)
        if not game:
            yield event.plain_result(msg)
            return
        text = self._args(event, "笔记")
        if not text:
            notes = game["notes"]
            yield event.plain_result("📝 笔记：\n" + "\n".join(f"· {n['who']}：{n['text']}" for n in notes[-10:]) if notes else "还没有笔记。用 /笔记 内容 记下你的推理。")
            return
        _, name = self._who(event)
        game["notes"].append({"who": name, "text": text[:200]})
        del game["notes"][:-30]
        self.storage.save(event.unified_msg_origin, game)
        yield event.plain_result("📝 已记下。发 /案件 卷宗 可以看到所有笔记。")

    # ------------------------------------------------------------ 指令：指认
    @filter.command("指认", alias={"指控", "破案"})
    async def accuse(self, event: AstrMessageEvent):
        umo = event.unified_msg_origin
        game, msg = await self._act_guard(event, allow_final=True)
        if not game:
            yield event.plain_result(msg)
            return
        s, reasoning = engine.split_target(game, self._args(event, "指认", "指控", "破案"))
        if not s:
            yield event.plain_result(f"要指认谁？{self._suspect_list(game)}\n例：/指认 名字 他因为……用……的手法")
            return
        uid, name = self._who(event)
        engine.touch(game, uid, name)
        case = game["case"]
        self._busy.add(umo)
        try:
            if s["id"] == case["truth"]["culprit"]:
                motive_ok = method_ok = False
                comment = ""
                if reasoning:
                    try:
                        motive_ok, method_ok, comment = npc.parse_judge(await self._llm("npc", umo, npc.judge_prompt(game, reasoning), npc.JUDGE_SYSTEM, 60))
                    except Exception:
                        pass
                engine.credit(game, uid, engine.PTS_ACCUSE)
                score = engine.case_score(game, True, motive_ok, method_ok)
                try:
                    confess = await self._llm("npc", umo, npc.confess_prompt(game), npc.CONFESS_SYSTEM, 90)
                except Exception:
                    confess = ""
                head = [f"⚖️ {name}指认：{s['name']}！", "—— 正确，真凶就是 TA。"]
                if reasoning:
                    head.append(f"动机{'✅' if motive_ok else '❌'}　手法{'✅' if method_ok else '❌'}" + (f"　{comment}" if comment else ""))
                else:
                    head.append("（没有说明动机和手法，只拿凶手分。下次可以 /指认 名字 后面接上你的推理）")
                if confess:
                    head += ["", f"🗣 {s['name']}：{confess}"]
                self.storage.finish(umo, game, "solved", score)
                yield event.plain_result("\n".join(head))
                yield event.plain_result(engine.truth_text(game) + "\n\n" + engine.scoreboard(game, score))
                return
            game["wrong"].append(s["id"])
            if len(game["wrong"]) < engine.MAX_WRONG and not game["final"]:
                self.storage.save(umo, game)
                yield event.plain_result(
                    f"⚖️ {name}指认：{s['name']}！\n{s['name']}据理力争，现有的证据不足以定罪——TA 不是真凶。\n本案扣 5 分，还剩 {engine.MAX_WRONG - len(game['wrong'])} 次指认机会。\n{engine.status_line(game)}"
                )
                return
            try:
                after = await self._llm("npc", umo, npc.wrong_prompt(game, s), npc.WRONG_SYSTEM, 60)
            except Exception:
                after = ""
            self.storage.finish(umo, game, "failed", 0)
            text = f"⚖️ {name}指认：{s['name']}！\n这是一桩错案。"
            if after:
                text += f"\n\n{after}"
            yield event.plain_result(text)
            yield event.plain_result(engine.truth_text(game) + "\n\n" + engine.scoreboard(game, 0))
        finally:
            self._busy.discard(umo)
