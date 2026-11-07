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
        Theme(
            key="changan",
            name="上元夜 · 长安",
            aliases=("长安", "上元", "唐朝", "古风", "宫廷"),
            setting="盛唐长安，上元节灯会，坊门彻夜不闭。一座临街的酒楼雅间里，宴请的主人在满城花灯最盛时倒下，宾客与仆从都被金吾卫拦在楼中。",
            mood="花灯如昼、人潮如织、胡旋舞与宫廷秘闻；越是热闹，越容易藏住一个人。",
            locations=("雅间", "后厨", "灯楼", "账房", "回廊", "后巷马车"),
            archetypes=("酒楼东家", "胡姬舞女", "金吾卫校尉", "宫中女官", "落魄画师", "西域商人", "小厮"),
            naming="唐风人名或称呼，如裴十二娘、李校尉、阿史那、柳画师",
            time_note="对白用时辰与更鼓，time 字段写 HH:MM",
        ),
        Theme(
            key="manor",
            name="雾都庄园 · 维多利亚",
            aliases=("庄园", "英伦", "维多利亚", "伦敦", "雾都"),
            setting="19 世纪末英格兰乡间庄园。老爵士召集家人宣读遗嘱的前夜，暴雨冲断了唯一的桥，第二天清晨他被发现死在书房。",
            mood="壁炉、雨声、老式座钟与遗嘱；体面的笑容下，每个继承人都在算计。",
            locations=("书房", "温室", "餐厅", "仆人通道", "酒窖", "藏书阁"),
            archetypes=("管家", "长子", "继室夫人", "侄女", "家庭医生", "律师", "女仆"),
            naming="中文音译西式人名或称呼，如哈德森管家、艾琳夫人、维克多",
            time_note="用钟点叙述，time 字段写 HH:MM",
        ),
        Theme(
            key="train",
            name="绿皮火车 · 1988",
            aliases=("火车", "绿皮", "八十年代", "1988", "列车"),
            setting="1988 年冬，一列南下的绿皮火车卧铺车厢。大雪让列车停在山间小站，一位乘客在软卧包厢里没了气息，同车厢的人里藏着二十年前的旧识。",
            mood="铁轨声、搪瓷缸、绿皮车厢与站台广播；陌生人之间，往事一点点浮出来。",
            locations=("软卧包厢", "硬卧车厢", "餐车", "列车员室", "车厢连接处", "行李架"),
            archetypes=("列车员", "下海经商的老板", "返乡知青", "退休干部", "年轻教师", "倒爷", "医生"),
            naming="八十年代常见人名或称呼，如老周、小芳、王老板、李同志",
            time_note="用列车时刻表叙述，time 字段写 HH:MM",
        ),
        Theme(
            key="opera",
            name="古镇戏班",
            aliases=("戏班", "古镇", "戏曲", "戏台"),
            setting="江南古镇，一个即将散伙的老戏班在祠堂戏台唱最后一场。大轴戏唱到一半，班主倒在后台，戏服、面具与道具刀堆了满地。",
            mood="锣鼓、油彩、木偶与传家戏文；台上唱的是别人的故事，台下藏的是自己的恩怨。",
            locations=("戏台", "后台妆房", "衣箱房", "祠堂偏厅", "河埠头", "班主住处"),
            archetypes=("班主", "当家花旦", "武生", "琴师", "管箱人", "学徒", "镇上乡绅"),
            naming="戏班艺名或称呼，如小桂芳、陈班主、吴琴师、阿福",
            time_note="用钟点与戏码进度叙述（唱到第几折），time 字段写 HH:MM",
        ),
        Theme(
            key="campus",
            name="大学社团 · 一等奖之争",
            aliases=("校园", "大学", "社团", "学生"),
            setting="当代一所大学的创新大赛决赛前夜。社团活动室里，团队的核心成员被发现倒在实验台边，作品数据也不翼而飞。走廊门禁记录、群聊记录和监控都在说着各自的话。",
            mood="通宵、外卖、咖啡与群聊；友情与嫉妒只隔一条消息。",
            locations=("社团活动室", "实验室", "天台", "宿舍楼下", "图书馆研讨间", "监控室"),
            archetypes=("社长", "技术大神", "学生会干部", "指导老师", "合作方学长", "社团新人"),
            naming="当代大学生人名或昵称，如程一、苏苏、老陈",
            time_note="用精确钟点，time 字段写 HH:MM；参与者都是成年大学生",
        ),
        Theme(
            key="cyber",
            name="空中都市 · 赛博朋克",
            aliases=("赛博", "赛博朋克", "义体", "未来都市"),
            setting="2077 年，悬浮于云层之上的空中都市。一家义体公司的顶层发布会后，首席设计师死在自己的私人工作室，AI 管家的记录、门禁日志和记忆芯片都可能被篡改。",
            mood="霓虹、雨、全息广告与义体；每个人都可能换过一部分自己。",
            locations=("顶层工作室", "发布会大厅", "义体维修间", "服务器机房", "停机坪", "地下酒吧"),
            archetypes=("公司高管", "义体医生", "黑客", "保镖", "AI 管家维护员", "竞争对手代表", "记者"),
            naming="中英混合代号或人名，如零号、薇拉、K、陈博士",
            time_note="用精确钟点，可提及日志与系统时间戳，time 字段写 HH:MM",
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
            key="swap",
            name="身份替换",
            idea="某人并不是他自称的那个人（顶替、冒名、双胞胎或乔装），凶手借这个身份接近受害人或制造不在场。",
            flaws=("习惯动作或常识上的破绽（左右手、口音、对某件旧事一无所知）", "一件只有真身才拥有或才知道的东西对不上"),
        ),
        Trick(
            key="dying_message",
            name="死前留言被误读",
            idea="受害人临终留下了指向凶手的留言或记号，但大家第一眼的理解指向了别人；换个角度看，它说的是另一个意思。",
            flaws=("留言换个读法（倒过来、谐音、职业术语、方言）指向另一个人", "受害人留言时的处境决定了他只能用这种方式表达"),
        ),
        Trick(
            key="accomplice",
            name="两人共谋互相作证",
            idea="两个人事先串通，互相为对方提供不在场证明；其中一人动手，另一人负责制造假象或拖住旁人。（本案凶手 culprit 填主谋，共犯写进真相与时间线）",
            flaws=("两人的说法太过一致，像背好的台词，细节却在别处对不上", "两人之间有一条外人不知道的联系被线索揭开"),
        ),
        Trick(
            key="staged",
            name="受害人自导自演失败",
            idea="受害人原本设计了一场假戏（假装遇险、诬陷某人、制造混乱），凶手看穿并利用了这场戏，让真正的杀机藏在假戏里。",
            flaws=("受害人生前的反常安排（提前准备的道具、反常的叮嘱）", "假戏的剧本里有一处被凶手改动过的地方"),
        ),
        Trick(
            key="blackout",
            name="利用天气或停电",
            idea="凶手利用一段停电、雷雨、浓雾或断网的混乱时间作案，并让大家以为那段时间谁都没法行动。",
            flaws=("停电或混乱发生的确切时间与某人的说法对不上", "黑暗中只有熟悉环境或事先准备的人才能做到的事"),
        ),
        Trick(
            key="forged_log",
            name="伪造日志或记录",
            idea="凶手篡改或伪造了记录（账本、签到簿、门禁日志、聊天记录、车票），让作案时间或人员进出看起来完全不同。",
            flaws=("记录的格式、字迹或用语与平时不同", "记录里的一条信息与另一个独立来源（证人、实物）矛盾"),
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


def custom_theme(desc: str) -> Theme:
    """玩家自定义题材：把描述当作场景，其余交给模型自拟。"""
    desc = desc.strip()
    short = desc[:12] + ("…" if len(desc) > 12 else "")
    return Theme(
        key="custom",
        name=f"自定义 · {short}",
        aliases=(),
        setting=desc,
        mood="按题材自拟，要有鲜明的时代感或画面感",
        locations=(),
        archetypes=(),
        naming="符合题材的人名或称呼（不要使用现实中真实存在的人名）",
        time_note="time 字段写 24 小时制 HH:MM",
    )
