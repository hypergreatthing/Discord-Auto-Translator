import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.ru_slang import normalize_ru


class TestRussianSlang(unittest.TestCase):

    def test_known_slang_is_rewritten(self):
        self.assertEqual(normalize_ru("гг"), "хорошая игра")
        self.assertEqual(normalize_ru("хз что делать"), "не знаю что делать")
        self.assertEqual(normalize_ru("ну блин"), "ну чёрт")

    def test_case_is_preserved(self):
        self.assertEqual(normalize_ru("Блин, опять"), "Чёрт, опять")
        self.assertEqual(normalize_ru("БЛИН"), "ЧЁРТ")

    def test_longer_phrases_win(self):
        self.assertEqual(normalize_ru("го в дс"), "давай в дискорд")
        self.assertEqual(normalize_ru("ржу не могу"), "умираю со смеху")

    def test_standard_words_untouched(self):
        # Words that merely contain a slang token must not be rewritten.
        for s in ["человек", "погода", "блинчики", "голова", "привет", "Hello world"]:
            self.assertEqual(normalize_ru(s), s)

    def test_non_cyrillic_passthrough(self):
        self.assertEqual(normalize_ru("gg ez"), "gg ez")
        self.assertEqual(normalize_ru(""), "")

    def test_metaphorical_euphemisms_and_idioms(self):
        # "Hang noodles on ears" -> "deceive"
        self.assertEqual(normalize_ru("не вешай лапшу на уши"), "не обманывай меня")
        # "It is violet to me" / "to the drum" -> "I don't care at all"
        self.assertEqual(normalize_ru("мне фиолетово"), "мне абсолютно всё равно")
        self.assertEqual(normalize_ru("по барабану"), "совершенно всё равно")
        # "Changed shoes in mid-air" -> "changed opinion"
        self.assertEqual(normalize_ru("переобулся в воздухе"), "резко поменять своё мнение")
        # "Info 100%" / "Zero market"
        self.assertEqual(normalize_ru("инфа сотка"), "это стопроцентная правда")
        self.assertEqual(normalize_ru("базару ноль"), "без проблем, договорились")
        # Softened profanity euphemisms
        self.assertEqual(normalize_ru("ёлки-палки, это капец"), "чёрт возьми, это полный ужас")
        self.assertEqual(normalize_ru("нифига себе"), "вот это удивление")

    def test_gaming_and_modern_slang_verbs(self):
        self.assertIn("не справляюсь", normalize_ru("я уже не вывожу"))
        self.assertIn("выиграть сложный матч", normalize_ru("он смог затащить катку"))
        self.assertIn("вышел из игры", normalize_ru("чел ливнул из катки"))
        self.assertIn("хватит придираться", normalize_ru("не души братан"))
        self.assertIn("хорошо разбираюсь", normalize_ru("я шарю в этом"))


if __name__ == "__main__":
    unittest.main()
