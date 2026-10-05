"""Generic editorial exclusions for the Toy build only; never store puzzle/solution mappings.

This is a project policy, not a platform-provided banned-word list or approval guarantee.
Source dictionaries remain unchanged. Policy changes require a new sequence revision.
"""
import hashlib
import json

REVISION = "endless-v3"
POLICY_VERSION = "vocabulary-v3"
# Unambiguous vulgar characters; deliberately do not blanket-filter 性/阴/精/乳.
EXCLUDED_CHARACTERS = frozenset("淫婬嫖妓娼婊屄肏屌睾睪㚻㞗閪")
EXCLUDED_WORDS = frozenset("""
性交 性爱 性欲 性侵 性器 性媾 性乐 性事 性伴 性病 性瘾 性癖 性福
色情 色欲 色狼 色情 色情 春宫 春药 春梦 媚药 催情 调情 偷情 滥交 乱交
口交 肛交 乳交 足交 群交 杂交 交媾 媾合 嫖娼 卖春 买春 援交
自慰 自淫 手淫 意淫 强奸 轮奸 迷奸 诱奸 兽奸 鸡奸 通奸 奸淫 奸污 奸尸 奸杀
奸夫 奸情 视奸 指奸 抓奸 捉奸 逼奸 㚻奸
阴茎 阴道 阴唇 阴囊 阴蒂 阴核 阴户 阴毛 阴部 阴门 阴阜 阴径 阴穴 阴精
下阴 外阴 女阴 会阴 舔阴 缩阴 阳具 龟头 包皮 包茎 勃起 阳痿 早泄 遗精
射精 吞精 排精 精液 精子 精囊 精巢 精索 精虫 卵巢 卵子 输精 肛门 屁眼
乳头 乳房 乳晕 乳沟 乳贴 乳罩 巨乳 丰乳 爆乳 胸乳 双乳 下乳 贫乳 隆乳
裸体 裸露 裸女 裸男 裸照 裸聊 裸奔 裸泳 裸模 裸像 裸戏 裸替 裸睡 裸袒 裸裎 裸贷 赤裸 全裸 半裸
傻逼 傻叉 傻冒 傻帽 傻缺 傻蛋 傻子 傻瓜 笨蛋 白痴 蠢货 蠢猪 蠢蛋 蠢材 蠢才 蠢驴
贱人 贱货 嘴贱 手贱 下贱 狗屁 狗屎 狗日 狗娘 杂种 畜生 王八 龟孙 龟儿 混蛋 浑蛋
妈的 他妈 你妈 尼玛 操你 操蛋 操逼 草泥 艹 操逼 煞笔 沙比 傻比 装逼 牛逼 撕逼 逗逼 二逼 苦逼
毒品 吸毒 贩毒 冰毒 毒枭 毒贩 毒资 毒瘾 毒驾 嗑药 大麻 鸦片 罂粟 迷药
赌博 赌场 赌坊 赌客 赌局 赌徒 赌桌 赌棍 赌注 赌狗 赌球 赌窝 赌资 赌钱 赌鬼 聚赌 签赌
自杀 自残 自尽 自焚 上吊 割腕 跳楼 跳河 服毒 寻死 轻生
虐杀 奸杀 屠杀 凶杀 仇杀 谋杀 暗杀 刺杀 枪杀 绞杀 缢杀 残杀 砍杀 劫杀 情杀
杀人 杀婴 杀头 杀戮 杀害 杀死 分尸 碎尸 焚尸 锉尸 尸块 尸臭 腐尸 尸骸 尸首
虐待 施虐 受虐 虐恋 凌虐 残虐 毒刑 毒打 酷刑 鞭刑 斩首 腰斩 活埋 灭门
恐袭 恐怖 暴恐 爆头 血腥 血案 血洗 血祭 血尸 食人 吃人
鸡巴 鸡掰 我操 做鸡 叫鸡 奶子 奶头 奶罩 叫床 床技 床友 床戏
发骚 骚货 聊骚 撩骚 猥亵 娈童 肛塞 舔肛 蜜穴 春画 欲女 欲经
胸推 臀推 鸡鸡 鸡儿 二奶 蛋逼 逼逼 娘的 脑残
交合 交尾 交欢 交配 兽交 内射 口射 手交 拳交 指交 股交
偷人 同房 圆房 房事 房劳 行房 开房 壮阳 阳物 阳萎 阳道 男根 命根 肉棒
姘 姘夫 姘头 姘妇 姘居 抽插 插喉 撸管 秒射 颜射 荡妇 爱奴 色鬼 色魔
劫色 贩婴 溺婴 童婚 婚驴 媚男 龟公 性行 性腺 性学 性征 性感 奸宿
肛 肛毛 肛裂 脱肛 床笫 春妇 春宵 春情 春心 兽欲 情欲 泄欲 纵欲 肉欲
欲火 欲海 秽语 猥 发春 叫春 上床 骚包 骚情 骚话 骚驴
懵逼 绝逼 逼尖 逼格 硬逼 咖逼 娘炮 娘泡 骂娘 喷粪 狗贼 人渣 人妖
支那 黑鬼 鬼佬 鬼婆 鬼子 洋鬼 共匪 绿教 穆黑 精障 笨货 笨瓜 蠢人 蠢汉 贱格 泼贱
阉人 阉竖 阉割 捡尸 毒杀 下毒 投毒 勒杀 坑杀 射杀 棒杀 惨杀 故杀
吊死 吊颈 逼死 炸死 枪决 枪毙 枪崩 残肢 嗜血 喋血 歃血 血泊 血崩 血债 血刃
傻 蠢 贱 裸 尿 屎 粪 屁 屁股 粪便 尸体 尸 杀手 打赌 赌
丧尸 他杀 停尸 僵尸 全尸 击杀 厮杀 大粪 奸人 娈 完虐 宰杀 对赌 尝粪
尸僵 尸布 尸斑 尸身 尸骨 屎意 屙屎 屠毒 干尸 扒粪 打杀 把屎 投杀 拉屎
挺尸 掩杀 收尸 放毒 斩杀 暴虐 杀伤 杀掉 杀绝 梅毒 死尸 毒唯 毒害 毒手 毒药
活尸 滥杀 猥獕 猥琐 端屎 粪凼 粪坑 粪尿 粪蛆 粪青 背杀 胎粪 脐屎
虐 虐心 蠢话 裸骑 诈尸 诛杀 误杀 贱民 赌城 赌斗 赌烂 赌约 躺尸 追杀 逼供
陈尸 闷骚 风骚 骚 骚味 黄毒 嗝屁 响屁 尻 尿尿 尿泡 屁事 屁屁 屁民 屁精 屁话
屁轻 屙 屙尿 打屁 撒尿 放屁 自溺 臭屁 蔫屁 阴屁 黄书 黄片 黑屁 龟男
副乳 乳部 胯间 裆部 媾 阉
卖身 打炮 约炮
""".split())


def allowed(word):
    return word not in EXCLUDED_WORDS and not EXCLUDED_CHARACTERS.intersection(word)


def filter_words(words):
    return [word for word in words if allowed(word)]


def filter_endless(data):
    return {"version": data["version"], "common": filter_words(data["common"]),
            "broad": filter_words(data["broad"])}


def encode(value):
    return (json.dumps(value, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")


def filter_campaign(data, vocabulary, size):
    """Resolve only in memory to audit word edges; export original public records only."""
    words = set(vocabulary)
    before, after = {}, {}
    for word in words:
        if len(word) == 2:
            a, b = word
            after.setdefault(a, set()).add(b)
            before.setdefault(b, set()).add(a)
    kept = []
    for puzzle in data["puzzles"]:
        c = puzzle["clues"]
        top = [c["top"]] if size == 1 else c["top"]
        bottom = [c["bottom"]] if size == 1 else c["bottom"]
        domains = [after.get(top[i], set()) & before.get(bottom[i], set()) for i in range(size)]
        domains[0] &= after.get(c["left"], set())
        domains[-1] &= before.get(c["right"], set())
        candidates = domains[0] if size == 1 else (a + b for a in domains[0] for b in domains[1] if a + b in words)
        verified = False
        for candidate in candidates:
            value = f'{data["version"]}:{puzzle["id"]}:{puzzle["salt"]}:{candidate}'
            if hashlib.sha256(value.encode()).hexdigest() != puzzle["check"]:
                continue
            verified = True
            edges = [c["left"] + candidate[0], candidate[-1] + c["right"]]
            edges += [edge for i, char in enumerate(candidate) for edge in (top[i] + char, char + bottom[i])]
            if all(allowed(w) for w in [candidate, *edges, *top, *bottom, c["left"], c["right"]]):
                kept.append(puzzle)
            break
        if not verified:
            raise ValueError("Could not verify a campaign record during editorial audit")
    result = dict(data, puzzles=kept)
    if len(kept) != len(data["puzzles"]):
        result["revision"] = hashlib.sha256((data["revision"] + POLICY_VERSION + ''.join(p["id"] for p in kept)).encode()).hexdigest()[:16]
    if not kept:
        raise ValueError("Editorial policy removed the entire campaign")
    return result
