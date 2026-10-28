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


if __name__ == "__main__":
    unittest.main()
