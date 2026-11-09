"""系列主线：几桩案件之间埋同一条暗线，连续破案逐章揭开幕后真相。

每章仍是一桩独立、可解的案件；程序在生成时注入主线要求（一张主线线索、凶手与幕后人的联系），
破案后公布一段主线碎片；第五章的凶手就是幕后人本人。
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Chapter:
    no: int
    title: str
    theme: str | None  # 指定题材 key；None 表示随机
    trick: str | None  # 指定诡计 key；None 表示随机
    inject: str  # 写进生成提示词的主线要求
    fragment: str  # 破案后揭晓的主线碎片


@dataclass(frozen=True)
class Arc:
    key: str
    name: str
    intro: str
    mark: str  # 主线线索必须包含的字样，用于校验
    chapters: tuple[Chapter, ...]
    epilogue: str


COMMON = (
    "【系列主线 · 灰蛾】本案是系列的一章：真凶并非独自想出诡计——案发前，一个看不清面目的陌生人教了他作案的办法，"
    "事后留下一只用旧报纸折成的灰色纸蛾。请在线索里加入一张主线线索：source=search，key=false，points_to 留空，"
    "名称里带“灰蛾”二字，描述那只纸蛾和{detail}。这张线索只是主线彩头，不能影响破案，破案仍然要靠其他线索。"
    "凶手的 secret 里写上他是如何遇到那个陌生人的（一两句）。"
)

ARCS: dict[str, Arc] = {
    "moth": Arc(
        key="moth",
        name="灰蛾",
        intro=(
            "最近的几桩命案，凶手都说过同一句话：“是一个看不清脸的人，教我该怎么做。”每个现场，都留下一只用旧报纸折成的灰色纸蛾。"
            "有人在替自己杀人，却从不亲自动手。五桩案子，五只纸蛾——找到放出纸蛾的人。"
        ),
        mark="灰蛾",
        chapters=(
            Chapter(1, "第一只纸蛾", "inn", None,
                    COMMON.format(detail="翅膀内侧用细笔写着的“第一只”三个字"),
                    "纸蛾展开后，是一角发黄的旧报纸，能辨认出半个标题：“……港码头仓库大火，十三人……”。凶手说，那个陌生人临走前问他：“你知道十三年前那场火吗？”"),
            Chapter(2, "乐谱里的数字", "shanghai", None,
                    COMMON.format(detail="夹在乐谱或账本里、背面印着“七·一三”这串数字"),
                    "翻遍旧报馆的合订本，你们找到了那条新闻：十三年前七月十三日，雾港码头的顾家仓库一夜烧尽，十三人遇难。遇难名单的最后一个名字，被人用墨涂掉了。"),
            Chapter(3, "第七包厢", "train", None,
                    COMMON.format(detail="一张写着“你恨的人在第七包厢”的字条"),
                    "被涂掉的名字是“顾雾”——仓库主人的养子，当年十九岁，被认定葬身火海，却始终没有找到遗骸。而这三桩案子的死者，当年都在那份仓库值夜名单上。"),
            Chapter(4, "面具之下", "opera", "swap",
                    COMMON.format(detail="纸蛾内侧画着的一张没有五官的面具"),
                    "凶手终于想起那人的一个细节：他左手少了一截小指，说话时习惯用右手遮住嘴。十三年前的火，不是意外——有人锁上了仓库的门。还活着的知情者，只剩最后一个。"),
            Chapter(5, "灰蛾", None, "swap",
                    "【系列主线 · 终章】本案的真凶就是一直放出纸蛾的“灰蛾”：十三年前雾港仓库大火中被认为已死的顾雾，如今化名为本案的一名嫌疑人。"
                    "他左手少了一截小指、习惯用右手遮嘴（要作为一条线索出现）。动机：向当年锁上仓库大门、害死他养父的最后一名知情者复仇。"
                    "他这一次亲自动手。凶手的 secret 写明真实身份顾雾。请在线索里加入一张名称带“灰蛾”的搜查线索：一整盒尚未折完的旧报纸纸蛾，key=false。",
                    "顾雾摘下手套，露出缺了一截的小指：“那天晚上，门是从外面锁上的。我在火里听着他们喊了一夜。”"),
        ),
        epilogue=(
            "五只纸蛾，终于落定。十三年前锁门的人都已不在，顾雾被带走时没有反抗。"
            "他最后说：“我教给他们的，只是办法；恨，是他们自己的。”——《灰蛾》完。"
        ),
    ),
}

DEFAULT_ARC = "moth"


def arc_of(key: str) -> Arc:
    return ARCS.get(key) or ARCS[DEFAULT_ARC]


def chapter(arc: Arc, no: int) -> Chapter | None:
    return next((c for c in arc.chapters if c.no == no), None)


def status_text(arc: Arc, ch_no: int, done: bool) -> str:
    lines = [f"🦋 主线《{arc.name}》", arc.intro, ""]
    for c in arc.chapters:
        mark = "✅" if c.no < ch_no or done else ("▶" if c.no == ch_no else "·")
        lines.append(f"{mark} 第 {c.no} 章 · {c.title}")
    revealed = [c.fragment for c in arc.chapters if c.no < ch_no or done]
    if revealed:
        lines += ["", "已揭开的真相："] + [f"{i}. {f}" for i, f in enumerate(revealed, 1)]
    lines.append("")
    lines.append(arc.epilogue if done else f"发 /案件 主线 下一章 开始第 {ch_no} 章。")
    return "\n".join(lines)
