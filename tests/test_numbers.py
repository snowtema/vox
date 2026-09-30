import unittest

from vox import numbers


class IntWordsTest(unittest.TestCase):
    def test_basic(self):
        cases = {
            0: "ноль", 1: "один", 12: "двенадцать", 21: "двадцать один",
            100: "сто", 101: "сто один", 999: "девятьсот девяносто девять",
        }
        for n, words in cases.items():
            with self.subTest(n=n):
                self.assertEqual(numbers.int_words(n), words)

    def test_feminine(self):
        self.assertEqual(numbers.int_words(1, fem=True), "одна")
        self.assertEqual(numbers.int_words(2, fem=True), "две")
        self.assertEqual(numbers.int_words(22, fem=True), "двадцать две")
        self.assertEqual(numbers.int_words(5, fem=True), "пять")

    def test_thousands_are_feminine_and_inflected(self):
        cases = {
            1000: "тысяча",
            2000: "две тысячи",
            5000: "пять тысяч",
            21000: "двадцать одна тысяча",
            1234: "тысяча двести тридцать четыре",
        }
        for n, words in cases.items():
            with self.subTest(n=n):
                self.assertEqual(numbers.int_words(n), words)

    def test_millions_and_billions(self):
        self.assertEqual(numbers.int_words(1_000_000), "один миллион")
        self.assertEqual(numbers.int_words(2_000_000), "два миллиона")
        self.assertEqual(numbers.int_words(5_000_000), "пять миллионов")
        self.assertEqual(numbers.int_words(1_000_000_000), "один миллиард")


class FormTest(unittest.TestCase):
    def test_agreement(self):
        forms = ("строка", "строки", "строк")
        cases = {1: "строка", 2: "строки", 4: "строки", 5: "строк", 11: "строк",
                 12: "строк", 14: "строк", 21: "строка", 22: "строки", 25: "строк",
                 100: "строк", 101: "строка", 111: "строк"}
        for n, expected in cases.items():
            with self.subTest(n=n):
                self.assertEqual(numbers.form(n, forms), expected)


class DecimalWordsTest(unittest.TestCase):
    def test_tenths(self):
        self.assertEqual(numbers.decimal_words("2", "4"), "две целых четыре десятых")
        self.assertEqual(numbers.decimal_words("1", "5"), "одна целая пять десятых")

    def test_hundredths_keep_leading_zero_meaning(self):
        self.assertEqual(numbers.decimal_words("0", "25"), "ноль целых двадцать пять сотых")
        self.assertEqual(numbers.decimal_words("3", "05"), "три целых пять сотых")

    def test_many_digits_are_read_one_by_one(self):
        self.assertEqual(numbers.decimal_words("1", "2345"), "один точка два три четыре пять")


class ExpandTest(unittest.TestCase):
    def test_plain_text_is_untouched(self):
        self.assertEqual(numbers.expand("Просто текст без цифр."), "Просто текст без цифр.")

    def test_number_before_noun(self):
        self.assertEqual(numbers.expand("Прошло 12 строк"), "Прошло двенадцать строк")

    def test_gender_follows_next_word(self):
        cases = {
            "1 строка": "одна строка", "1 файл": "один файл",
            "2 строки": "две строки", "2 файла": "два файла",
            "5 строк": "пять строк",
        }
        for src, expected in cases.items():
            with self.subTest(src=src):
                self.assertEqual(numbers.expand(src), expected)

    def test_units(self):
        cases = {
            "5 мс": "пять миллисекунд",
            "1 сек": "одна секунда",
            "2 мин": "две минуты",
            "10 МБ": "десять мегабайт",
            "2 ГБ": "два гигабайта",
            "3 ч": "три часа",
        }
        for src, expected in cases.items():
            with self.subTest(src=src):
                self.assertEqual(numbers.expand(src), expected)

    def test_single_letter_unit_needs_punctuation_or_end(self):
        # «5 с 6» — предлог, а не секунды
        self.assertEqual(numbers.expand("сравнил 5 с 6"), "сравнил пять с шесть")
        self.assertEqual(numbers.expand("ждал 5 с."), "ждал пять секунд.")
        self.assertEqual(numbers.expand("ушёл на 5 с ним"), "ушёл на пять с ним")

    def test_decimal(self):
        self.assertEqual(numbers.expand("2.4 сек"), "две целых четыре десятых секунды")
        self.assertEqual(numbers.expand("1,5"), "одна целая пять десятых")

    def test_percent(self):
        self.assertEqual(numbers.expand("50%"), "пятьдесят процентов")
        self.assertEqual(numbers.expand("1 %"), "один процент")
        self.assertEqual(numbers.expand("3%"), "три процента")
        self.assertEqual(numbers.expand("2.5%"), "две целых пять десятых процента")

    def test_version_is_read_by_parts(self):
        self.assertEqual(numbers.expand("0.1.1"), "ноль точка один точка один")
        self.assertEqual(numbers.expand("версия 3.12.4"), "версия три точка двенадцать точка четыре")

    def test_thousands_separator_is_collapsed(self):
        self.assertEqual(numbers.expand("1 000"), "тысяча")
        self.assertEqual(numbers.expand("12 345"), "двенадцать тысяч триста сорок пять")
        self.assertEqual(numbers.expand("1 000 000"), "один миллион")

    def test_very_long_number_is_read_by_digits(self):
        self.assertEqual(
            numbers.expand("1234567890123"),
            "один два три четыре пять шесть семь восемь девять ноль один два три",
        )

    def test_no_digits_survive(self):
        text = "Тесты: 12 прошло, 3 упало, 0.5 сек, 99%, версия 1.2.3, 4 файла."
        self.assertNotRegex(numbers.expand(text), r"\d")


if __name__ == "__main__":
    unittest.main()
