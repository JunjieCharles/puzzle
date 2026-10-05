import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from build_toy import build_toy
from vocabulary_policy import REVISION, filter_endless, filter_words
import json
import hashlib


class ToyBuildTests(unittest.TestCase):
    def test_separate_package_without_save_code(self):
        with tempfile.TemporaryDirectory() as directory:
            target = build_toy(directory)
            names = {p.name for p in target.iterdir()}
            self.assertNotIn("save-code.js", names)
            html = (target / "index.html").read_text(encoding="utf-8")
            app = (target / "app.js").read_text(encoding="utf-8")
            self.assertNotIn('id="save-open"', html)
            self.assertNotIn('id="save-dialog"', html)
            self.assertNotIn("encodeSave", app)
            self.assertNotIn("decodeSave", app)
            self.assertIn('id="rank-two"', html)
            for name in ("rank-endless-one", "rank-endless-two"):
                self.assertIn(f'id="{name}"', html)
            self.assertNotIn('!platform && ["endless', app)
            for name in ("endless.js",):
                self.assertEqual((target / name).read_bytes(), (ROOT / "public" / name).read_bytes())
            vocabulary = json.loads((ROOT / "public/endless-lexicon.json").read_text(encoding="utf-8"))
            # Independent regressions from the previous shipped dictionary audit.
            # Generic words only; never associate these with real puzzle records.
            rejected = set("鸡巴 鸡掰 我操 做鸡 叫鸡 奶子 奶头 奶罩 叫床 床技 床友 床戏 发骚 骚货 聊骚 撩骚 猥亵 娈童 肛塞 舔肛 蜜穴 春画 欲女 欲经 胸推 臀推 鸡鸡 鸡儿 二奶 蛋逼 逼逼 娘的 脑残 黄片 黄书 睪丸 屁精".split())
            built = json.loads((target / "endless-lexicon.json").read_text(encoding="utf-8"))
            hints_built = json.loads((target / "hsk-two-words.json").read_text(encoding="utf-8"))["words"]
            self.assertFalse(rejected.intersection(built["common"] + built["broad"] + hints_built))
            self.assertTrue(set("性能 阴天 精神 乳酪 消毒 杀菌 黑人 白人 残疾".split()).issubset(set(built["common"] + built["broad"])))
            self.assertEqual(json.loads((target / "endless-lexicon.json").read_text(encoding="utf-8")), filter_endless(vocabulary))
            self.assertIn(REVISION, (target / "endless-engine.js").read_text(encoding="utf-8"))
            self.assertIn(hashlib.sha256((target / "endless-lexicon.json").read_bytes()).hexdigest(),
                          (target / "endless-worker.js").read_text(encoding="utf-8"))
            self.assertIn("toy-sdk.js", html)
            for name in ("campaign.json", "campaign-two.json"):
                original = json.loads((ROOT / "public" / name).read_text(encoding="utf-8"))
                result = json.loads((target / name).read_text(encoding="utf-8"))
                self.assertTrue(all(p in original["puzzles"] for p in result["puzzles"]))
                if len(result["puzzles"]) != len(original["puzzles"]):
                    self.assertNotEqual(result["revision"], original["revision"])
            hints = json.loads((ROOT / "public/hsk-two-words.json").read_text(encoding="utf-8"))
            self.assertEqual(json.loads((target / "hsk-two-words.json").read_text(encoding="utf-8"))["words"], filter_words(hints["words"]))
            with self.assertRaises(ValueError):
                build_toy(directory)


if __name__ == "__main__":
    unittest.main()
