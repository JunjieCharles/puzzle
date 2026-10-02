"""Generic editorial exclusions for the Toy build only; never store puzzle/solution mappings.

This is a project policy, not a platform-provided banned-word list or approval guarantee.
Source dictionaries remain unchanged. Policy changes require a new sequence revision.
"""
import hashlib
import json

REVISION = "endless-v2"
POLICY_VERSION = "vocabulary-v2"
# Unambiguous vulgar characters; deliberately do not blanket-filter 性/阴/精/乳.
EXCLUDED_CHARACTERS = frozenset("淫嫖妓娼婊屄肏屌睾")
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
