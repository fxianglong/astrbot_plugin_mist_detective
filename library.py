"""题材库、诡计库、风格与难度。纯数据，生成案件时由程序随机组合。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Theme:
    key: str
    name: str
    aliases: tuple[str, ...]
    setting: str  # 场景与时代
    mood: str  # 气氛
    locations: tuple[str, ...]  # 可搜查地点的参考（模型可改名，数量 5~6）
    archetypes: tuple[str, ...]  # 人物原型参考
    naming: str  # 起名风格
    time_note: str  # 叙述时间的方式


@dataclass(frozen=True)
class Trick:
    key: str
    name: str
    idea: str  # 诡计结构
    flaws: tuple[str, ...]  # 必须留下的破绽
    themes: tuple[str, ...] = ()  # 适配的题材，空表示都可以


@dataclass(frozen=True)
class Style:
    key: str
    name: str
    aliases: tuple[str, ...]
    guide: str


@dataclass(frozen=True)
class Difficulty:
    key: str
    name: str
    suspects: int
    red_herrings: int
    ap: tuple[int, int, int]  # 三幕的行动点
    key_clues: int  # 至少几张指向凶手的关键线索


THEMES: dict[str, Theme] = {
    t.key: t
    for t in [
        Theme(
            key="inn",
            name="风雪客栈",
            aliases=("客栈", "江湖", "武侠", "古代"),
            setting="架空古代江湖。大雪封山，山道断绝，一间山间客栈里困着店家和几位各怀心思的江湖客、商旅。",
            mood="炉火、风雪、刀光与陈年恩怨；人人都像有故事，人人都不肯先开口。",
            locations=("大堂", "厨房", "掌柜房间", "客房走廊", "马厩", "后院柴房"),
            archetypes=("老板娘", "镖师", "跑堂伙计", "落第书生", "游方郎中", "卖艺女子", "退隐捕快"),
            naming="古风人名或江湖称呼，如柳三娘、赵铁、沈先生、小六",
            time_note="对白里用时辰（戌时三刻、子时），time 字段仍写 24 小时制 HH:MM",
        ),
        Theme(
            key="shanghai",
            name="民国上海 · 百乐门",
            aliases=("民国", "上海", "百乐门", "舞厅"),
            setting="1930 年代上海，一家灯红酒绿的舞厅。歌女、帮派、报馆、洋行在这里交汇，命案发生在一场盛大的开业周年晚会上。",
            mood="爵士乐、香烟与霓虹；表面纸醉金迷，底下全是交易和把柄。",
            locations=("舞池", "后台化妆间", "经理办公室", "吧台", "天台", "后门弄堂"),
            archetypes=("当红歌女", "舞厅经理", "报馆记者", "帮会小头目", "留洋医生", "侍应生", "洋行买办"),
            naming="民国人名与称呼，如白玫、顾经理、陆记者、阿四",
            time_note="用钟点叙述（晚上九点一刻），time 字段写 HH:MM",
        ),
        Theme(
            key="homestay",
            name="网红民宿 · 直播间",
            aliases=("民宿", "直播", "网红", "现代", "当代"),
            setting="当代，一家海边网红民宿。台风天封路，民宿主人、主播团队和几位住客被困，一场直播进行到一半，主角出了事。",
            mood="镜头、弹幕、滤镜与流量焦虑；每个人在镜头前和镜头后是两副面孔。",
            locations=("直播间", "公共厨房", "露台", "主人卧室", "监控室", "停车场"),
            archetypes=("民宿主人", "网红主播", "运营助理", "摄影师", "前任", "投资人", "老住客"),
            naming="现代中文人名或网名，如林妙、阿哲、周总",
            time_note="用精确钟点，time 字段写 HH:MM",
        ),
        Theme(
            key="station",
            name="第七舱 · 太空站",
            aliases=("太空", "太空站", "科幻", "未来"),
            setting="近未来，一座近地轨道科研站。补给船推迟三天，站内只有几名成员，舱门日志、传感器与 AI 管家记录着一切——但记录也可能被改。",
            mood="寂静、失重、冷白灯光与倒计时；密闭空间里，信任一点点耗尽。",
            locations=("指挥舱", "实验舱", "生活舱", "气闸舱", "医疗舱", "动力舱"),
            archetypes=("站长", "系统工程师", "生物学家", "随站医生", "企业监察员", "维修技师"),
            naming="现代中文人名，可带代号或职务称呼，如顾站长、林工、陈医生",
            time_note="用站内标准时 HH:MM，可提及舱门日志、传感器读数",
        ),
    ]
}

TRICKS: dict[str, Trick] = {
    t.key: t
    for t in [
        Trick(
            key="clock",
            name="拨动钟表制造时间差",
            idea="凶手事先拨快或拨慢了现场或公共区域的钟表，让众人对作案时间产生误判，从而获得虚假的不在场证明。",
            flaws=("两个证人对同一时刻的描述对不上（一人凭钟表，一人凭别的参照，如更声、节目单、日志）", "被动过的钟表本身留有痕迹，或与另一处计时对不上"),
        ),
        Trick(
            key="fake_alibi",
            name="录音或替身伪造不在场",
            idea="凶手用事先准备的声音、灯光、身影或替身，让大家以为他在别处，实际上他在现场作案。",
            flaws=("伪造的声音或身影里缺了当时本该有的东西（钟声、雨声、某个人的插话）", "伪造用的道具或残留被找到"),
        ),
        Trick(
            key="locked_room",
            name="机关密室",
            idea="凶手离开后用细线、门闩机关或其他办法从外面锁上门窗，伪造成从里面锁死的密室，让人误以为是自杀、意外或无人能进出。",
            flaws=("门缝、门槛或窗框上留有机关痕迹或残留物", "做机关用的材料能在某个人的物品或附近找到同类"),
        ),
        Trick(
            key="delayed",
            name="延迟发作",
            idea="凶手提前下手，让伤害延迟发作（只写作“一种慢性毒药”或“延迟发作的手段”，不写名称、剂量和获取方式），案发时他早已离开现场、有人作证，不在场证明本身毫无意义。",
            flaws=("受害人最后一次饮食或接触某物的时间、地点和经手人", "凶手对“入口之物”表现出不该有的在意，或留下了处理痕迹"),
        ),
        Trick(
            key="first_finder",
            name="第一发现人即凶手",
            idea="凶手主动成为第一发现人，借“发现现场”的混乱掩盖作案或破坏证据，大家天然不会怀疑报案的人。",
            flaws=("他在看到现场之前，就说出了只有凶手才知道的细节", "他发现现场前后的行动有一段说不清的空白"),
        ),
        Trick(
            key="vanishing",
            name="凶器消失",
            idea="凶器在作案后消失或伪装成日常物件（会融化、会被吃掉、被拆开放回原处、混进道具里），让现场看起来没有凶器、无从下手。",
            flaws=("现场多出了或少了某样不起眼的东西（水渍、碎屑、空了一格的架子）", "凶器原本的出处少了一件，且只有少数人能接触到"),
        ),
    ]
}

STYLES: dict[str, Style] = {
    s.key: s
    for s in [
        Style(
            key="honkaku",
            name="本格",
            aliases=("本格", "推理", "逻辑", "默认"),
            guide="本格推理：重逻辑与公平，所有破案需要的信息都能被玩家拿到；诡计精巧但不靠巧合；红鲱鱼要合理，最后都能解释。",
        ),
        Style(
            key="social",
            name="社会派",
            aliases=("社会派", "社会", "人性", "情感"),
            guide="社会派：同样要求逻辑公平，但更重动机与人性——凶手的动机来自过去的伤害或无奈的处境，嫌疑人的秘密带着生活的重量，结局让人唏嘘。",
        ),
        Style(
            key="comedy",
            name="轻松喜剧",
            aliases=("喜剧", "轻松", "搞笑", "沙雕"),
            guide="轻松喜剧：没有人真的死去——案件是一件荒诞的“失窃案”或“恶作剧”（例如寿宴蛋糕被偷吃、镇店之宝被调包、主角被打晕后锁进储物间）。人物夸张有梗、说话好笑，但推理依然要公平、能推出来。",
        ),
    ]
}

DIFFICULTIES: dict[str, Difficulty] = {
    d.key: d
    for d in [
        Difficulty("easy", "简单", 3, 1, (6, 6, 4), 3),
        Difficulty("normal", "标准", 4, 2, (8, 8, 6), 3),
        Difficulty("hard", "困难", 5, 3, (10, 10, 8), 4),
    ]
}
DIFF_ALIASES = {"简单": "easy", "容易": "easy", "标准": "normal", "普通": "normal", "困难": "hard", "难": "hard", "地狱": "hard"}


def match_theme(word: str) -> Theme | None:
    w = word.strip()
    for t in THEMES.values():
        if w == t.key or w in t.name or any(w == a for a in t.aliases):
            return t
    return None


def match_style(word: str) -> Style | None:
    w = word.strip()
    for s in STYLES.values():
        if w == s.key or w == s.name or w in s.aliases:
            return s
    return None


def match_difficulty(word: str) -> Difficulty | None:
    w = word.strip()
    key = DIFF_ALIASES.get(w, w)
    return DIFFICULTIES.get(key)
