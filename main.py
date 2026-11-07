import asyncio
import random
import re
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import AstrMessageEvent, MessageChain, filter
from astrbot.api.star import Context, Star, StarTools, register

from . import engine, npc, render
from .generator import GEN_SYSTEM, SOLVE_SYSTEM, Skeleton, gen_prompt, normalize, parse_json, pick_skeleton, solve_prompt
from .illustrate import Illustrator, art_prompt
from .library import (
    DIFFICULTIES,
    STYLES,
    THEMES,
    TRICKS,
    custom_theme,
    match_difficulty,
    match_style,
    match_theme,
)
from .storage import Storage
from .validator import solve_matches, validate

PLUGIN_NAME = "astrbot_plugin_mist_detective"
CN_TZ = timezone(timedelta(hours=8))
WEEKDAYS = "一二三四五六日"

HELP = """🕯 雾夜侦探社 · AI 推理游戏
群友一起审讯嫌疑人、搜查现场、出示证据，在行动点用完前找出真凶。每个案件都由 AI 现场生成。

开局：/案件 开局 [题材] [风格] [难度]
  例：/案件 开局　/案件 开局 客栈 社会派 困难
  自定义：/案件 开局 自定义 1920 年代的远洋邮轮
  /案件 题材 查看全部题材、风格和难度
调查（每次消耗 1 个行动点，全群共用）：
  /审讯 名字 问题　　例：/审讯 沈先生 你昨晚戌时在哪
  /搜查 地点　　　　例：/搜查 厨房
  /出示 线索编号 名字　例：/出示 c3 柳三娘
  /对质 名字 名字 话题　例：/对质 柳三娘 赵铁 戌时你们在哪
结案：/指认 名字 动机和手法（说中动机、手法有额外分）
  群里多人参与时发起投票，/赞成 或 /反对，过半通过
  私聊我 /推理 内容，提交只有自己知道的推理，结案时单独计分
其他：/案件 卷宗｜/提示（扣 5 分）｜/笔记 内容｜/案件 推进（局长）
案件库：/案件 评分 1-5｜/案件 案件库｜/案件 重玩 编号
排行：/案件 排行｜悬案之夜：/案件 订阅 周五 21:00｜/案件 退订
放弃：/案件 结束 确认"""

CUSTOM_BLOCK = re.compile(r"未成年|小学生|初中生|幼儿|儿童|小孩|萝莉|正太|色情|性侵|强奸|乱伦|恐怖袭击|炸弹|制毒|贩毒")


class GenFailed(Exception):
    pass


Items = list[tuple[str, str]]  # [("text", 文本) | ("image", 本地路径)]


@register(PLUGIN_NAME, "fxianglong", "雾夜侦探社：AI 现场生成剧本的群聊推理游戏", "0.4.0")
class MistDetective(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config
        try:
            data_dir = Path(StarTools.get_data_dir(PLUGIN_NAME))
        except Exception:
            data_dir = Path("data") / "plugin_data" / PLUGIN_NAME
        data_dir.mkdir(parents=True, exist_ok=True)
        self.data_dir = data_dir
        self.storage = Storage(data_dir / "detective.db")
        self.illustrator = Illustrator(
            str(config.get("dashscope_api_key", "") or ""),
            str(config.get("image_model", "qwen-image") or "qwen-image"),
            str(config.get("image_size", "1328*1328") or "1328*1328"),
            data_dir / "art",
        )
        self._busy: set[str] = set()
        self._rng = random.Random()
        self._task = asyncio.create_task(self._scheduler_loop())

    async def terminate(self):
        if self._task:
            self._task.cancel()
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

    @staticmethod
    def _is_admin(event: AstrMessageEvent) -> bool:
        try:
            return bool(event.is_admin())
        except Exception:
            return False

    @staticmethod
    def _is_private(event: AstrMessageEvent) -> bool:
        try:
            return bool(event.is_private_chat())
        except Exception:
            return False

    def _cfg_int(self, key: str, default: int) -> int:
        try:
            v = self.config.get(key, default)
            return default if v is None or v == "" else int(v)
        except (TypeError, ValueError):
            return default

    def _cfg_list(self, key: str) -> list[str]:
        v = self.config.get(key, []) or []
        if isinstance(v, str):
            v = re.split(r"[,，、\s]+", v)
        return [str(x).strip() for x in v if str(x).strip()]

    @property
    def _image_mode(self) -> bool:
        return bool(self.config.get("image_mode", True))

    async def _llm(self, kind: str, umo: str, prompt: str, system: str, timeout: int) -> str:
        pid = str(self.config.get(f"{kind}_provider_id", "") or "").strip()
        if not pid:
            pid = await self.context.get_current_chat_provider_id(umo)
        resp = await asyncio.wait_for(
            self.context.llm_generate(chat_provider_id=pid, prompt=prompt, system_prompt=system), timeout=timeout
        )
        return (getattr(resp, "completion_text", "") or "").strip()

    async def _render(self, tmpl: str, data: dict, umo: str | None = None) -> str | None:
        try:
            return await self.html_render(tmpl, data, return_url=False, umo=umo)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"[侦探社] 图片渲染失败，改发文字：{e}")
            return None

    @staticmethod
    def _emit(event: AstrMessageEvent, items: Items):
        for kind, v in items:
            yield event.image_result(v) if kind == "image" else event.plain_result(v)

    async def _send(self, umo: str, items: Items) -> None:
        for kind, v in items:
            try:
                chain = MessageChain()
                chain = chain.file_image(v) if kind == "image" else chain.message(v)
                await self.context.send_message(umo, chain)
            except Exception as e:  # noqa: BLE001
                logger.error(f"[侦探社] 主动发送失败：{e}")

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

    def _today_start(self) -> float:
        now = datetime.now(CN_TZ)
        return now.replace(hour=0, minute=0, second=0, microsecond=0).timestamp()

    def _limit_msg(self, umo: str) -> str:
        n = self._cfg_int("daily_limit", 0)
        if n > 0 and self.storage.starts_since(umo, self._today_start()) >= n:
            return f"本群今天已经开了 {n} 局，明天再来吧（群管理可以在插件配置里调整每日上限）。"
        return ""

    def _disabled(self) -> tuple[set[str], set[str]]:
        themes = set()
        for w in self._cfg_list("disabled_themes"):
            t = match_theme(w)
            if t:
                themes.add(t.key)
        tricks = {t.key for w in self._cfg_list("disabled_tricks") for t in TRICKS.values() if w == t.key or w in t.name}
        return themes, tricks

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

    async def _opening_items(self, umo: str, game: dict, prefix: str = "") -> Items:
        items: Items = []
        if self._image_mode:
            path = await self._render(render.OPENING_TMPL, render.opening_data(game), umo)
            if path:
                if prefix:
                    items.append(("text", prefix.strip()))
                items.append(("image", path))
                items.append(("text", f"《{game['case']['title']}》开局！{engine.status_line(game)}。\n/案件 帮助 查看全部指令；私聊我 /推理 内容 可以提交个人推理。"))
                return items
        items.append(("text", prefix + engine.opening(game)))
        return items

    async def _illustration(self, game: dict) -> Items:
        if not self.illustrator.enabled:
            return []
        m = game["meta"]
        prompt = art_prompt(m["theme"], game["case"]["intro"], game["case"]["title"])
        path = await self.illustrator.draw(prompt, f"{int(time.time())}_{m['seed']}")
        return [("image", path)] if path else []

    async def _start_case(self, umo: str, sk: Skeleton, host: str, host_name: str = "") -> tuple[dict | None, Items]:
        """生成并保存新对局。返回 (game, 开场消息)；失败时 game 为 None。"""
        try:
            case = await self._generate(umo, sk)
        except GenFailed as e:
            return None, [("text", f"这次没能写出一桩靠谱的案子（{e}）。再发一次 /案件 开局 试试。")]
        except Exception as e:
            logger.error(f"[侦探社] 生成失败：{e}")
            return None, [("text", f"生成案件时出错：{e}")]
        game = engine.new_game(case, sk, host=host)
        if host:  # 局长算作本案侦探，可以私聊提交推理、参与投票
            game["players"][host] = {"name": host_name or host, "pts": 0, "actions": 0}
        self.storage.save(umo, game)
        self.storage.add_start(umo)
        return game, await self._opening_items(umo, game)

    async def _review_custom(self, umo: str, desc: str) -> str:
        """自定义题材审核，返回不通过的原因；空字符串表示通过。"""
        if not bool(self.config.get("allow_custom", True)):
            return "本群没有开启自定义题材。"
        if not (4 <= len(desc) <= 120):
            return "题材描述请写 4~120 个字，例如：/案件 开局 自定义 1920 年代横渡大西洋的远洋邮轮"
        if CUSTOM_BLOCK.search(desc):
            return "这个题材不适合用来做推理游戏，换一个吧。"
        for n in self.storage.player_names(umo):
            if len(n) >= 2 and n in desc:
                return "题材里不能出现群友的名字，避免变成影射。"
        try:
            ok, why = npc.parse_review(await self._llm("gen", umo, f"题材：{desc}", npc.REVIEW_SYSTEM, 60))
        except Exception as e:
            logger.warning(f"[侦探社] 自定义题材审核失败：{e}")
            return "题材审核暂时不可用，请稍后再试或使用内置题材。"
        return "" if ok else f"这个题材不太合适（{why or '内容不适合'}），换一个吧。"

    # ------------------------------------------------------------ 指令：案件
    @filter.command_group("案件")
    def case_group(self):
        pass

    @case_group.command("帮助", alias={"help"})
    async def help_(self, event: AstrMessageEvent):
        yield event.plain_result(HELP)

    @case_group.command("题材", alias={"列表"})
    async def themes(self, event: AstrMessageEvent):
        off_t, off_k = self._disabled()
        lines = ["📚 题材："]
        lines += [f"· {t.name}（{'/'.join(t.aliases[:3])}）{'【已关闭】' if t.key in off_t else ''}" for t in THEMES.values()]
        lines += ["· 自定义：/案件 开局 自定义 你想要的场景"]
        lines += ["", "🎭 风格："]
        lines += [f"· {s.name}：{s.guide.split('：', 1)[1][:40]}…" for s in STYLES.values()]
        lines += ["", "⚙️ 难度：" + "｜".join(f"{d.name} {d.suspects} 名嫌疑人" for d in DIFFICULTIES.values())]
        lines += ["", f"🧩 诡计库共 {len(TRICKS)} 种，开局随机抽取" + (f"（已关闭 {len(off_k)} 种）" if off_k else "")]
        lines += ["", "例：/案件 开局 民国 社会派 困难。不写就随机题材、默认风格、标准难度。"]
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
        if msg := self._limit_msg(umo):
            yield event.plain_result(msg)
            return
        words = self._args(event, "案件").split()[1:]
        theme = style = diff = None
        if words and words[0] in ("自定义", "自定"):
            desc = " ".join(words[1:]).strip()
            why = await self._review_custom(umo, desc)
            if why:
                yield event.plain_result(why)
                return
            theme = custom_theme(desc)
        else:
            for w in words:
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
        off_t, off_k = self._disabled()
        sk = pick_skeleton(self._rng, theme, style, diff, avoid=self.storage.recent_combos(umo), disabled_themes=off_t, disabled_tricks=off_k)
        uid, uname = self._who(event)
        self._busy.add(umo)
        try:
            yield event.plain_result(
                (note + "\n" if note else "")
                + f"🕯 雾夜侦探社接到一桩新案子（{sk.theme.name}｜{sk.style.name}｜{sk.diff.name}）。\n卷宗整理中，大约需要一两分钟……"
            )
            game, items = await self._start_case(umo, sk, host=uid, host_name=uname)
            for r in self._emit(event, items):
                yield r
            if game:
                for r in self._emit(event, await self._illustration(game)):
                    yield r
        finally:
            self._busy.discard(umo)

    @case_group.command("卷宗", alias={"进度", "状态", "线索墙"})
    async def dossier(self, event: AstrMessageEvent):
        game, msg = await self._need_game(event)
        if not game:
            yield event.plain_result(msg)
            return
        if self._image_mode and "文字" not in self._args(event, "案件"):
            path = await self._render(render.BOARD_TMPL, render.board_data(game), event.unified_msg_origin)
            if path:
                yield event.image_result(path)
                return
        yield event.plain_result(engine.dossier(game))

    @case_group.command("推进", alias={"下一幕"})
    async def advance(self, event: AstrMessageEvent):
        umo = event.unified_msg_origin
        game, msg = await self._need_game(event)
        if not game:
            yield event.plain_result(msg)
            return
        uid, _ = self._who(event)
        if uid != game.get("host") and not self._is_admin(event):
            host = game["players"].get(game.get("host") or "", {}).get("name") or "开局的人"
            yield event.plain_result(f"只有局长（{host}）或管理员可以推进幕次。")
            return
        if game["final"] or umo in self._busy or game.get("vote"):
            yield event.plain_result("现在不能推进（已是最后时刻、正在处理或正在投票）。")
            return
        game["ap"] = 1
        lines = engine.spend(game) + [engine.status_line(game)]
        self.storage.save(umo, game)
        yield event.plain_result("⏭ 局长推进了剧情。\n" + "\n".join(lines))

    @case_group.command("排行", alias={"排行榜", "榜单"})
    async def ranking(self, event: AstrMessageEvent):
        umo = event.unified_msg_origin
        rows = self.storage.ranking(umo)
        total, solved = self.storage.stats(umo)
        if not rows:
            yield event.plain_result("还没有结案记录。")
            return
        bd = engine.badges(rows)
        lines = [f"🏆 侦探排行（本群共破案 {solved}/{total}）"]
        for i, r in enumerate(rows, 1):
            name, pts, sv, gs = r[:4]
            extra = "".join(f"「{b}」" for b in bd.get(name, []))
            lines.append(f"{i}. {name}｜{engine.title_of(sv)}{extra}｜{pts} 分｜破案 {sv}/{gs}")
        lines.append("称号：见习侦探 → 侦探（破 3 案）→ 名侦探（10）→ 神探（25）")
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
        yield event.plain_result("案件已放弃，成了一桩悬案。")
        for r in self._emit(event, await self._truth_items(umo, game, 0, "abandoned")):
            yield r

    # ------------------------------------------------------------ 指令：案件库
    @case_group.command("评分", alias={"打分"})
    async def rate(self, event: AstrMessageEvent):
        umo = event.unified_msg_origin
        m = re.search(r"[1-5]", self._args(event, "案件").replace("评分", "").replace("打分", ""))
        last = self.storage.last_case(umo)
        if not last:
            yield event.plain_result("本群还没有结案的案件可以评分。")
            return
        if not m:
            yield event.plain_result(f"给《{last[1]}》打几颗星？/案件 评分 1-5")
            return
        uid, _ = self._who(event)
        avg, n = self.storage.rate(last[0], uid, int(m.group()))
        yield event.plain_result(f"⭐ 已为 #{last[0]}《{last[1]}》打 {m.group()} 星。目前平均 {avg:.1f}（{n} 人）。高分案件会进入 /案件 案件库，供其他群重玩。")

    @case_group.command("案件库", alias={"精品", "精品案件"})
    async def library_(self, event: AstrMessageEvent):
        min_avg = float(self.config.get("library_min_stars", 4) or 4)
        rows = self.storage.library(min_avg)
        if not rows:
            yield event.plain_result(f"案件库还是空的。结案后用 /案件 评分 打分，平均 {min_avg:g} 星以上的案件会收进来。")
            return
        lines = ["📚 精品案件库（/案件 重玩 编号）"]
        for cid, title, theme, style, avg, n, plays in rows:
            tn = THEMES[theme].name if theme in THEMES else "自定义"
            sn = STYLES[style].name if style in STYLES else style
            lines.append(f"#{cid}《{title}》｜{tn}｜{sn}｜★{avg:.1f}（{n} 人）｜玩过 {plays} 次")
        yield event.plain_result("\n".join(lines))

    @case_group.command("重玩", alias={"replay"})
    async def replay(self, event: AstrMessageEvent):
        umo = event.unified_msg_origin
        m = re.search(r"\d+", self._args(event, "案件").replace("重玩", ""))
        if not m:
            yield event.plain_result("用法：/案件 重玩 编号（编号见 /案件 案件库）")
            return
        game, _ = self._active(umo)
        if game:
            yield event.plain_result(f"本群已有进行中的案件《{game['case']['title']}》。")
            return
        if umo in self._busy:
            yield event.plain_result("卷宗正在整理中，请稍等。")
            return
        if msg := self._limit_msg(umo):
            yield event.plain_result(msg)
            return
        d = self.storage.case_data(int(m.group()))
        if not d:
            yield event.plain_result("没有这个编号的案件。")
            return
        meta = d["meta"]
        theme = THEMES.get(meta.get("theme")) or custom_theme(meta.get("theme_name", "自定义").replace("自定义 · ", ""))
        sk = Skeleton(
            theme,
            TRICKS.get(meta.get("trick")) or next(iter(TRICKS.values())),
            STYLES.get(meta.get("style")) or STYLES["honkaku"],
            DIFFICULTIES.get(meta.get("diff")) or DIFFICULTIES["normal"],
            int(meta.get("seed") or 0),
        )
        uid, uname = self._who(event)
        game = engine.new_game(d["case"], sk, host=uid, replay_of=d["origin"])
        game["players"][uid] = {"name": uname, "pts": 0, "actions": 0}
        if meta.get("theme_name"):
            game["meta"]["theme_name"] = meta["theme_name"]
        self.storage.save(umo, game)
        self.storage.add_start(umo)
        for r in self._emit(event, await self._opening_items(umo, game, prefix=f"📚 重玩精品案件 #{d['origin']}\n")):
            yield r

    # ------------------------------------------------------------ 指令：悬案之夜
    @staticmethod
    def _parse_when(text: str, default_wd: int, default_hm: str) -> tuple[int, str] | None:
        wd, hm = default_wd, default_hm
        m = re.search(r"(?:周|星期|礼拜)([一二三四五六日天])", text)
        if m:
            wd = WEEKDAYS.index(m.group(1).replace("天", "日"))
        m = re.search(r"(\d{1,2})[:：](\d{2})", text)
        if m:
            h, mi = int(m.group(1)), int(m.group(2))
            if h > 23 or mi > 59:
                return None
            hm = f"{h:02d}:{mi:02d}"
        return wd, hm

    @case_group.command("订阅", alias={"悬案之夜"})
    async def subscribe(self, event: AstrMessageEvent):
        if self._is_private(event):
            yield event.plain_result("悬案之夜只能在群里订阅。")
            return
        when = self._parse_when(self._args(event, "案件"), 4, "21:00")
        if not when:
            yield event.plain_result("时间格式不对，例：/案件 订阅 周五 21:00")
            return
        self.storage.subscribe(event.unified_msg_origin, *when)
        yield event.plain_result(f"🌙 已订阅「悬案之夜」：每周{WEEKDAYS[when[0]]} {when[1]} 自动开一局随机案件。/案件 退订 取消。")

    @case_group.command("退订")
    async def unsubscribe(self, event: AstrMessageEvent):
        ok = self.storage.unsubscribe(event.unified_msg_origin)
        yield event.plain_result("已取消悬案之夜。" if ok else "本群没有订阅悬案之夜。")

    async def _scheduler_loop(self) -> None:
        await asyncio.sleep(20)
        while True:
            try:
                await self._tick(datetime.now(CN_TZ))
            except asyncio.CancelledError:
                raise
            except Exception as e:  # noqa: BLE001
                logger.error(f"[侦探社] 定时任务出错：{e}")
            await asyncio.sleep(30)

    async def _tick(self, now: datetime) -> None:
        today = now.strftime("%Y-%m-%d")
        for umo, wd, hm, last in self.storage.subs():
            if now.weekday() != wd or last == today:
                continue
            h, m = map(int, hm.split(":"))
            fire = now.replace(hour=h, minute=m, second=0, microsecond=0)
            if not (fire <= now < fire + timedelta(minutes=30)):
                continue
            self.storage.mark_sub(umo, today)
            asyncio.create_task(self._night(umo))

    async def _night(self, umo: str) -> None:
        game, _ = self._active(umo)
        if game or umo in self._busy:
            await self._send(umo, [("text", "🌙 悬案之夜到了，不过本群还有一桩没结的案子，先把它破了吧！")])
            return
        off_t, off_k = self._disabled()
        style = match_style(str(self.config.get("default_style", "本格") or "本格")) or STYLES["honkaku"]
        sk = pick_skeleton(self._rng, None, style, None, avoid=self.storage.recent_combos(umo), disabled_themes=off_t, disabled_tricks=off_k)
        self._busy.add(umo)
        try:
            await self._send(umo, [("text", f"🌙 悬案之夜 · 雾夜侦探社今晚接到一桩新案子（{sk.theme.name}）。卷宗整理中……")])
            game, items = await self._start_case(umo, sk, host="")
            await self._send(umo, items)
            if game:
                await self._send(umo, await self._illustration(game))
        finally:
            self._busy.discard(umo)

    # ------------------------------------------------------------ 指令：调查
    async def _act_guard(self, event: AstrMessageEvent, allow_final: bool = False):
        game, msg = await self._need_game(event)
        if not game:
            return None, msg
        if game["final"] and not allow_final:
            return None, "行动点已经用完了，现在只能 /指认 名字。"
        if event.unified_msg_origin in self._busy:
            return None, "正在处理上一个行动，请稍等。"
        if game.get("vote"):
            if time.time() < game["vote"]["deadline"]:
                return None, "正在投票指认中，请先 /赞成 或 /反对。"
            self._busy.add(event.unified_msg_origin)
            try:
                items = await self._settle_vote(event.unified_msg_origin, game, force=True) or []
            finally:
                self._busy.discard(event.unified_msg_origin)
            texts = [v for k, v in items if k == "text"]
            return None, "\n\n".join(texts) + "\n（上一轮投票已结算，请重新发送指令）"
        return game, ""

    async def _breakdown(self, umo: str, game: dict, s: dict, uid: str) -> str:
        engine.credit(game, uid, engine.PTS_BREAKDOWN)
        engine.bump(game, uid, "breaks")
        try:
            mono = await self._llm("npc", umo, npc.breakdown_prompt(game, s), npc.BREAKDOWN_SYSTEM, 60)
        except Exception:
            mono = ""
        new = engine.give_clues(game, [c["id"] for c in engine.testimony_pool(game, s["id"], with_hidden=False)], uid)
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
                if any(c.get("hidden") for c in new):
                    lines.append(f"🥚 {name}挖出了一个隐藏彩蛋！个人 +{engine.PTS_EGG}，本案 +5")
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

    @filter.command("对质", alias={"当面对质"})
    async def confront(self, event: AstrMessageEvent):
        umo = event.unified_msg_origin
        game, msg = await self._act_guard(event)
        if not game:
            yield event.plain_result(msg)
            return
        a, rest = engine.split_target(game, self._args(event, "对质", "当面对质"))
        b, topic = engine.split_target(game, rest) if a else (None, "")
        if not a or not b or a["id"] == b["id"]:
            yield event.plain_result(f"让谁和谁对质？{self._suspect_list(game)}\n例：/对质 柳三娘 赵铁 戌时你们各自在哪")
            return
        uid, name = self._who(event)
        broken = engine.confront_breaks(game, a["id"], b["id"])
        self._busy.add(umo)
        try:
            try:
                raw = await self._llm("npc", umo, npc.confront_prompt(game, a, b, topic, broken), npc.CONFRONT_SYSTEM, self._cfg_int("npc_timeout", 60))
                out = npc.parse_confront(raw, a, b)
            except Exception as e:
                logger.warning(f"[侦探社] 对质调用失败：{e}")
                yield event.plain_result(f"（{a['name']}和{b['name']}互相瞪着，谁也不肯先开口）模型调用失败，本次不消耗行动点。")
                return
            engine.touch(game, uid, name)
            engine.mark_broken(game, [l for _, l in broken], uid)
            liars = {s["id"] for s, _ in broken}
            crashed = []
            for s in (a, b):
                if engine.add_pressure(game, s["id"], 25 if s["id"] in liars else 8):
                    crashed.append(s)
            new = engine.accept_reveal(game, a["id"], out["reveal"], uid) + engine.accept_reveal(game, b["id"], out["reveal"], uid)
            for s, cl in ((a, out["claim_a"]), (b, out["claim_b"])):
                engine.record(game, s["id"], name, f"（与{(b if s is a else a)['name']}对质）{topic}", "", cl)
            lines = [f"⚔️ {name}让{a['name']}和{b['name']}当面对质" + (f"：{topic}" if topic else "")]
            lines += [f"{w}：{t}" for w, t in out["lines"]]
            for s, l in broken:
                lines.append(f"💡 当面戳穿！{s['name']}承认：{l['truth']}")
            lines.append(f"紧张度　{a['name']} {engine.pressure_bar(game['pressure'][a['id']])}　{b['name']} {engine.pressure_bar(game['pressure'][b['id']])}")
            if new:
                lines.append("📌 新线索：\n" + "\n".join(engine.clue_line(c) for c in new))
            for s in crashed:
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

    # ------------------------------------------------------------ 指令：私下推理
    @filter.command("推理", alias={"我的推理"})
    async def private_reason(self, event: AstrMessageEvent):
        if not self._is_private(event):
            yield event.plain_result("🤫 个人推理请私聊我发送：/推理 你的推理（凶手、动机、手法），别让群友看到。结案时单独计分。")
            return
        uid, name = self._who(event)
        games = self.storage.games_with_player(uid)
        text = self._args(event, "推理", "我的推理")
        if not games:
            yield event.plain_result("你还没有参与任何进行中的案件。先在群里审讯或搜查一次，再来提交推理。")
            return
        idx = 0
        m = re.match(r"^(\d)\s+", text)
        if len(games) > 1:
            if not m or not (1 <= int(m.group(1)) <= len(games)):
                lst = "\n".join(f"{i}. 《{g['case']['title']}》" for i, (_, g) in enumerate(games, 1))
                yield event.plain_result(f"你同时在玩好几个案件，请在推理前写上序号，例如：/推理 1 我觉得是……\n{lst}")
                return
            idx = int(m.group(1)) - 1
            text = text[m.end():]
        umo, game = games[idx]
        if not text.strip():
            mine = game.get("private", {}).get(uid)
            yield event.plain_result(f"《{game['case']['title']}》你提交的推理：{mine['text']}" if mine else "写上你的推理：/推理 凶手是……，因为……，手法是……")
            return
        if umo in self._busy:
            yield event.plain_result("群里正在处理行动，请稍后再提交。")
            return
        game.setdefault("private", {})[uid] = {"name": game["players"][uid]["name"] or name, "text": text.strip()[:400]}
        self.storage.save(umo, game)
        yield event.plain_result(f"🤫 已记下你对《{game['case']['title']}》的推理（可以随时重新提交覆盖）。结案时公布并计分：凶手 10、动机 5、手法 5。")

    async def _settle_private(self, umo: str, game: dict) -> list[str]:
        subs = game.get("private") or {}
        if not subs:
            return []
        lines = ["🤫 私下推理揭晓："]
        for uid, p in subs.items():
            try:
                c, mo, me = npc.parse_private(await self._llm("npc", umo, npc.private_prompt(game, p["text"]), npc.PRIVATE_SYSTEM, 60))
            except Exception:
                c = mo = me = False
            pts = (10 if c else 0) + (5 if mo else 0) + (5 if me else 0)
            engine.credit(game, uid, pts)
            lines.append(f"· {p['name']}：凶手{'✅' if c else '❌'} 动机{'✅' if mo else '❌'} 手法{'✅' if me else '❌'}　+{pts}")
        return lines

    # ------------------------------------------------------------ 指令：指认
    async def _truth_items(self, umo: str, game: dict, score: int, result: str, confess: str = "") -> Items:
        if self._image_mode:
            path = await self._render(render.CLOSING_TMPL, render.closing_data(game, score, result, confess), umo)
            if path:
                return [("image", path), ("text", engine.scoreboard(game, score) + "\n\n给这个案件打个分吧：/案件 评分 1-5")]
        return [("text", engine.truth_text(game) + "\n\n" + engine.scoreboard(game, score) + "\n\n给这个案件打个分吧：/案件 评分 1-5")]

    async def _do_accuse(self, umo: str, game: dict, s: dict, reasoning: str, uid: str, name: str) -> Items:
        """执行指认并返回要发出的消息；结案时归档。调用方负责加 busy。"""
        case = game["case"]
        if s["id"] == case["truth"]["culprit"]:
            motive_ok = method_ok = False
            comment = ""
            if reasoning:
                try:
                    motive_ok, method_ok, comment = npc.parse_judge(await self._llm("npc", umo, npc.judge_prompt(game, reasoning), npc.JUDGE_SYSTEM, 60))
                except Exception:
                    pass
            engine.credit(game, uid, engine.PTS_ACCUSE)
            if game["act"] == 1:
                engine.bump(game, uid, "quick")
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
            if game["act"] == 1:
                head.append("👁 第一幕就锁定真凶，一眼看穿！")
            if confess:
                head += ["", f"🗣 {s['name']}：{confess}"]
            head += [""] + await self._settle_private(umo, game) if game.get("private") else []
            self.storage.finish(umo, game, "solved", score)
            return [("text", "\n".join(head).strip())] + await self._truth_items(umo, game, score, "solved", confess)
        game["wrong"].append(s["id"])
        engine.bump(game, uid, "wrongs")
        if len(game["wrong"]) < engine.MAX_WRONG and not game["final"]:
            self.storage.save(umo, game)
            return [(
                "text",
                f"⚖️ {name}指认：{s['name']}！\n{s['name']}据理力争，现有的证据不足以定罪——TA 不是真凶。\n本案扣 5 分，还剩 {engine.MAX_WRONG - len(game['wrong'])} 次指认机会。\n{engine.status_line(game)}",
            )]
        try:
            after = await self._llm("npc", umo, npc.wrong_prompt(game, s), npc.WRONG_SYSTEM, 60)
        except Exception:
            after = ""
        priv = await self._settle_private(umo, game)
        self.storage.finish(umo, game, "failed", 0)
        text = f"⚖️ {name}指认：{s['name']}！\n这是一桩错案。" + (f"\n\n{after}" if after else "") + ("\n\n" + "\n".join(priv) if priv else "")
        return [("text", text)] + await self._truth_items(umo, game, 0, "failed")

    def _vote_on(self, event: AstrMessageEvent, game: dict) -> bool:
        if not bool(self.config.get("vote_accuse", True)) or self._is_private(event):
            return False
        return len(game["players"]) >= 2

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
        if self._vote_on(event, game):
            secs = max(15, self._cfg_int("vote_seconds", 60))
            vote = engine.start_vote(game, s["id"], uid, name, reasoning, secs)
            self.storage.save(umo, game)
            asyncio.create_task(self._vote_timer(umo, vote["id"], secs))
            n = len(game["players"])
            yield event.plain_result(
                f"🗳 {name}提议指认：{s['name']}！"
                + (f"\n推理：{reasoning}" if reasoning else "")
                + f"\n请参与本案的 {n} 位侦探投票：/赞成 或 /反对。{secs} 秒后结算，过半赞成即执行（提议人已算赞成）。"
            )
            return
        self._busy.add(umo)
        try:
            for r in self._emit(event, await self._do_accuse(umo, game, s, reasoning, uid, name)):
                yield r
        finally:
            self._busy.discard(umo)

    async def _settle_vote(self, umo: str, game: dict, force: bool) -> Items | None:
        """结算投票；force=False 时只在票数已经决定结果时结算。返回 None 表示还没结算。"""
        v = game.get("vote")
        if not v:
            return None
        verdict = engine.vote_verdict(game)
        if verdict is None and not force:
            return None
        game.pop("vote", None)
        yes, no = len(v["yes"]), len(v["no"])
        s = engine.suspect(game, v["target"])
        # 超时时：赞成多于反对、且至少有一人附议才通过，避免一个人的提议在无人理会时直接生效
        if verdict is True or (verdict is None and yes > no and yes >= 2):
            items = await self._do_accuse(umo, game, s, v["reasoning"], v["by"], v["by_name"])
            return [("text", f"🗳 投票通过（赞成 {yes} / 反对 {no}）")] + items
        self.storage.save(umo, game)
        why = "无人附议" if yes < 2 and no == 0 else f"赞成 {yes} / 反对 {no}"
        return [("text", f"🗳 投票未通过（{why}），{s['name']}暂不指认。继续调查吧。\n{engine.status_line(game)}")]

    async def _vote_timer(self, umo: str, vote_id: str, secs: int):
        await asyncio.sleep(secs)
        while umo in self._busy:
            await asyncio.sleep(1)
        game = self.storage.load(umo)
        if not game or (game.get("vote") or {}).get("id") != vote_id:
            return
        self._busy.add(umo)
        try:
            items = await self._settle_vote(umo, game, force=True) or []
        except Exception as e:
            logger.error(f"[侦探社] 投票结算失败：{e}")
            items = []
        finally:
            self._busy.discard(umo)
        await self._send(umo, items)

    async def _cast(self, event: AstrMessageEvent, agree: bool) -> Items:
        umo = event.unified_msg_origin
        game, msg = await self._need_game(event)
        if not game:
            return [("text", msg)]
        if not game.get("vote"):
            return [("text", "现在没有进行中的投票。")]
        if umo in self._busy:
            return [("text", "正在结算，请稍等。")]
        uid, name = self._who(event)
        engine.cast_vote(game, uid, name, agree)
        self._busy.add(umo)
        try:
            expired = time.time() >= game["vote"]["deadline"]
            items = await self._settle_vote(umo, game, force=expired)
            if items is None:
                self.storage.save(umo, game)
                v = game["vote"]
                return [("text", f"🗳 {name}{'赞成' if agree else '反对'}。当前 赞成 {len(v['yes'])} / 反对 {len(v['no'])}")]
            return items
        finally:
            self._busy.discard(umo)

    @filter.command("赞成", alias={"同意", "支持"})
    async def vote_yes(self, event: AstrMessageEvent):
        for r in self._emit(event, await self._cast(event, True)):
            yield r

    @filter.command("反对", alias={"不同意"})
    async def vote_no(self, event: AstrMessageEvent):
        for r in self._emit(event, await self._cast(event, False)):
            yield r
