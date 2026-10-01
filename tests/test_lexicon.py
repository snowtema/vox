import re
import unittest

from vox import lexicon
from tests.support import IsolatedCase

_LATIN = re.compile(r"[A-Za-z]")


class TermsTest(unittest.TestCase):
    def test_keys_are_lowercase(self):
        bad = [k for k in lexicon.TERMS if k != k.lower()]
        self.assertEqual(bad, [])

    def test_values_are_spoken_in_cyrillic(self):
        bad = {k: v for k, v in lexicon.TERMS.items() if _LATIN.search(v)}
        self.assertEqual(bad, {})

    def test_stress_marks_only_before_vowels(self):
        bad = {k: v for k, v in lexicon.TERMS.items()
               if re.search(r"\+(?![аеёиоуыэюя])", v)}
        self.assertEqual(bad, {})

    def test_letter_names_cover_alphabet(self):
        self.assertEqual(set(lexicon.LETTER_NAMES), set("abcdefghijklmnopqrstuvwxyz"))


class SpellOutTest(unittest.TestCase):
    def test_acronym_by_letters(self):
        self.assertEqual(lexicon.spell_out("CDN"), "си ди эн")
        self.assertEqual(lexicon.spell_out("xyz"), "икс уай зед")

    def test_digits_pass_through_and_punctuation_is_dropped(self):
        self.assertEqual(lexicon.spell_out("S3"), "эс 3")
        self.assertEqual(lexicon.spell_out("a-b"), "эй би")


class TranslitTest(unittest.TestCase):
    def test_digraphs(self):
        self.assertEqual(lexicon.translit("shop"), "шоп")
        self.assertEqual(lexicon.translit("check"), "чек")

    def test_result_is_lowercase_cyrillic_for_plain_words(self):
        for word in ("Banana", "Quick", "Harbor", "twilight", "gadget", "zzz"):
            with self.subTest(word=word):
                out = lexicon.translit(word)
                self.assertTrue(out)
                self.assertNotRegex(out, r"[A-Za-z]")
                self.assertEqual(out, out.lower())

    def test_suffixes(self):
        self.assertTrue(lexicon.translit("station").endswith("шн"))
        self.assertTrue(lexicon.translit("dangerous").endswith("ус"))

    def test_silent_e_is_dropped(self):
        self.assertEqual(lexicon.translit("table"), "табл")

    def test_suffixes_ending_in_e_are_not_shadowed_by_silent_e(self):
        # Раньше «немая e» срезалась до проверки суффиксов: picture -> «пиктур»
        self.assertEqual(lexicon.translit("picture"), "пикчер")
        self.assertEqual(lexicon.translit("bridge"), "бридж")
        self.assertEqual(lexicon.translit("uncle"), "юнкл")


class LatinizeTest(IsolatedCase):
    def test_known_terms(self):
        self.assertEqual(lexicon.latinize("pnpm install"), "пи эн пи эм инсталл")
        self.assertEqual(lexicon.latinize("Next.js"), "некст джей эс")

    def test_lookup_is_case_insensitive(self):
        self.assertEqual(lexicon.latinize("GitHub"), "гитхаб")
        self.assertEqual(lexicon.latinize("GITHUB"), "гитхаб")

    def test_unknown_acronym_is_spelled(self):
        self.assertEqual(lexicon.latinize("XYZ"), "икс уай зед")

    def test_known_acronym_uses_dictionary(self):
        self.assertEqual(lexicon.latinize("CDN"), "си ди эн")

    def test_cyrillic_and_punctuation_are_kept(self):
        self.assertEqual(lexicon.latinize("Запусти: pnpm, потом git."),
                         "Запусти: пи эн пи эм, потом гит.")

    def test_camel_case_is_split_into_parts(self):
        self.assertEqual(lexicon.latinize("useEffect"), "юз эффект")
        out = lexicon.latinize("getUserName")
        self.assertIn(" ", out)
        self.assertTrue(out.endswith("нейм"))        # Name — из словаря
        self.assertNotRegex(out, r"[A-Za-z]")

    def test_screaming_snake_case_is_read_as_words(self):
        out = lexicon.latinize("MAX_RETRY")
        self.assertEqual(out, "макс ретрай")

    def test_kebab_and_dotted_names_are_split(self):
        out = lexicon.latinize("my-app")
        self.assertTrue(out.endswith("апп"))
        self.assertNotRegex(out, r"[A-Za-z]")

    def test_mode_off_changes_nothing(self):
        self.assertEqual(lexicon.latinize("pnpm install", "off"), "pnpm install")

    def test_mode_dict_translates_only_known_terms(self):
        self.assertEqual(lexicon.latinize("pnpm foobar", "dict"), "пи эн пи эм foobar")
        self.assertEqual(lexicon.latinize("my-app", "dict"), "my апп")
        self.assertEqual(lexicon.latinize("foo-bar", "dict"), "foo-bar")

    def test_mode_translit_leaves_no_latin(self):
        out = lexicon.latinize("Hetzner, Myapp, wrangler.toml, FooBarBaz")
        self.assertNotRegex(out, r"[A-Za-z]")

    def test_add_terms_overrides_builtin(self):
        self.assertEqual(lexicon.latinize("myapp"), lexicon.translit("myapp"))
        lexicon.add_terms({"MyApp": "майапп", "git": "гитт"})
        self.assertEqual(lexicon.latinize("myapp"), "майапп")
        self.assertEqual(lexicon.latinize("MYAPP"), "майапп")
        self.assertEqual(lexicon.latinize("git"), "гитт")


class PluralTest(IsolatedCase):
    def test_regular_plurals_from_dictionary_stems(self):
        cases = {
            "tests": "тесты", "commits": "коммиты", "files": "файлы", "builds": "билды",
            "endpoints": "эндпоинты", "errors": "эрроры", "bugs": "баги",
            "configs": "конфиги", "handlers": "хендлеры", "users": "юзеры",
            "assets": "ассеты", "scripts": "скрипты", "workers": "воркеры",
        }
        for word, expected in cases.items():
            with self.subTest(word=word):
                self.assertEqual(lexicon.latinize(word), expected)

    def test_es_and_ies_plurals(self):
        cases = {"classes": "классы", "fixes": "фиксы", "hashes": "хэши", "queries": "квери",
                 "branches": "бранчи", "processes": "процессы"}
        for word, expected in cases.items():
            with self.subTest(word=word):
                self.assertEqual(lexicon.latinize(word), expected)

    def test_ending_follows_russian_spelling_rules(self):
        self.assertEqual(lexicon._plural("баг"), "баги")          # после г — «и»
        self.assertEqual(lexicon._plural("пэкидж"), "пэкиджи")   # после ж — «и»
        self.assertEqual(lexicon._plural("тест"), "тесты")
        self.assertEqual(lexicon._plural("модуль"), "модули")
        self.assertEqual(lexicon._plural("версия"), "версии")
        self.assertEqual(lexicon._plural("фича"), "фичи")
        self.assertEqual(lexicon._plural("кей"), "кей")           # на -й не склоняем
        self.assertEqual(lexicon._plural("реди"), "реди")         # на гласную — как есть
        self.assertEqual(lexicon._plural("эй пи ай"), "эй пи ай")  # буквенные чтения
        self.assertEqual(lexicon._plural(""), "")

    def test_modules_versions_packages(self):
        self.assertEqual(lexicon.latinize("modules"), "модули")
        self.assertEqual(lexicon.latinize("versions"), "версии")
        self.assertEqual(lexicon.latinize("packages"), "пэкиджи")

    def test_unknown_stem_gets_transliterated_with_plural(self):
        out = lexicon.latinize("widgets")
        self.assertTrue(out.endswith("ы"), out)
        self.assertNotRegex(out, r"[A-Za-z]")

    def test_acronym_plural_is_spelled(self):
        self.assertEqual(lexicon.latinize("APIs"), "эй пи ай")
        self.assertEqual(lexicon.latinize("IDs"), "ай ди")
        self.assertEqual(lexicon.latinize("ids"), "ай ди")
        self.assertEqual(lexicon.latinize("UIs"), "юай")

    def test_explicit_entries_beat_the_rule(self):
        self.assertEqual(lexicon.latinize("hooks"), "хуки")
        lexicon.add_terms({"tests": "тестики"})
        self.assertEqual(lexicon.latinize("tests"), "тестики")

    def test_words_that_only_look_like_plurals_are_not_split(self):
        for word in ("status", "process", "address", "access", "always", "canvas", "this",
                     "class", "news", "does"):
            with self.subTest(word=word):
                self.assertNotIn(lexicon._plural(lexicon.translit(word[:-1])), [lexicon.latinize(word)],
                                 f"{word} принят за множественное число")

    def test_status_and_process_read_as_words(self):
        self.assertEqual(lexicon.latinize("process"), "процесс")
        self.assertEqual(lexicon.latinize("address"), "адрес")
        self.assertEqual(lexicon.latinize("class"), "класс")


class VerbFormsTest(IsolatedCase):
    def test_ing_from_dictionary_stem(self):
        cases = {"caching": "кэшинг", "building": "билдинг", "testing": "тестинг",
                 "linting": "линтинг", "using": "юзинг"}
        for word, expected in cases.items():
            with self.subTest(word=word):
                self.assertEqual(lexicon.latinize(word), expected)

    def test_doubled_consonant(self):
        self.assertEqual(lexicon.latinize("running"), "раннинг")
        self.assertEqual(lexicon.latinize("committing"), "коммиттинг")

    def test_ed_from_dictionary_stem(self):
        self.assertEqual(lexicon.latinize("cached"), "кэшед")
        self.assertEqual(lexicon.latinize("tested"), "тестед")

    def test_short_or_unrelated_words_with_the_same_ending_are_untouched(self):
        for word in ("string", "thing", "need", "red", "ring"):
            with self.subTest(word=word):
                out = lexicon.latinize(word)
                self.assertNotRegex(out, r"[A-Za-z]")
        self.assertEqual(lexicon.latinize("string"), "стринг")


class ApostropheTest(IsolatedCase):
    def test_possessive_is_silent(self):
        self.assertEqual(lexicon.latinize("Claude's"), "кл+од")
        self.assertEqual(lexicon.latinize("GitHub's"), "гитхаб")
        self.assertEqual(lexicon.latinize("agent’s"), "+эйджент")       # типографский апостроф

    def test_contractions_are_words(self):
        cases = {"it's": "итс", "don't": "донт", "can't": "кэнт", "I'm": "айм",
                 "They're": "зэр", "let's": "летс", "wasn't": "уознт"}
        for word, expected in cases.items():
            with self.subTest(word=word):
                self.assertEqual(lexicon.latinize(word), expected)

    def test_no_apostrophe_left_in_a_sentence(self):
        out = lexicon.latinize("Так как it's agent's job, мы don't спорим.")
        self.assertNotIn("'", out)
        self.assertEqual(out, "Так как итс +эйджент job, мы донт спорим.".replace("job", lexicon.translit("job")))

    def test_quotes_around_a_word_are_not_apostrophes(self):
        self.assertEqual(lexicon.latinize("'git' и 'npm'"), "'гит' и 'эн пи эм'")

    def test_contraction_table_is_cyrillic_only(self):
        bad = {k: v for k, v in lexicon.CONTRACTIONS.items() if _LATIN.search(v)}
        self.assertEqual(bad, {})


class AbbreviationTest(IsolatedCase):
    def test_eg_ie_etc_vs(self):
        self.assertEqual(lexicon.latinize("e.g., foo"), "например, фу")
        self.assertEqual(lexicon.latinize("i.e. так"), "то есть так")
        self.assertEqual(lexicon.latinize("a, b, etc."), lexicon.latinize("a") + ", " + lexicon.latinize("b") + ", и так далее.")
        self.assertEqual(lexicon.latinize("A vs B"), "эй против би")

    def test_capital_at_sentence_start(self):
        self.assertEqual(lexicon.latinize("E.g. так"), "Например так")
        self.assertEqual(lexicon.latinize("I.e. так"), "То есть так")

    def test_dotted_without_space_and_with_space(self):
        self.assertEqual(lexicon.latinize("e. g. так"), "например так")

    def test_vs_code_is_not_versus(self):
        self.assertEqual(lexicon.latinize("VS Code"), "ви эс к+од")

    def test_off_mode_leaves_abbreviations(self):
        self.assertEqual(lexicon.latinize("e.g. x", "off"), "e.g. x")


class LettersAndDigitsTest(IsolatedCase):
    def test_cloud_and_protocol_names(self):
        cases = {"S3": "эс 3", "EC2": "и си 2", "v2": "ви 2", "HTTP2": "эйч ти ти пи 2",
                 "OAuth2": "о аус 2", "mp3": "эм пи 3", "gpt4": "джи пи ти 4",
                 "sha256": "ша 256", "base64": "бейс 64", "python3": "питон 3"}
        for word, expected in cases.items():
            with self.subTest(word=word):
                self.assertEqual(lexicon.latinize(word), expected)

    def test_dictionary_entries_with_digits_win(self):
        self.assertEqual(lexicon.latinize("x86"), "икс восемьдесят шесть")
        self.assertEqual(lexicon.latinize("k8s"), "кубернетес")

    def test_digits_survive_for_numbers_module(self):
        from vox import numbers
        self.assertEqual(numbers.expand(lexicon.latinize("S3 и EC2")), "эс три и и си два")

    def test_dict_mode_leaves_unknown_alphanumerics(self):
        self.assertEqual(lexicon.latinize("EC2", "dict"), "EC2")
        self.assertEqual(lexicon.latinize("python3", "dict"), "питон 3")

    def test_version_with_dash(self):
        self.assertEqual(lexicon.latinize("UTF-8"), "ю ти эф 8")


class NewTermsTest(IsolatedCase):
    def test_compound_names(self):
        cases = {
            "package.json": "пэкидж джейсон", "tsconfig.json": "тэ эс конфиг джейсон",
            "node_modules": "нода модули", "VSCode": "ви эс к+од", "vscode": "ви эс к+од",
            "Xcode": "экс к+од", "iPhone": "айфон", "Dockerfile": "докерфайл",
        }
        for word, expected in cases.items():
            with self.subTest(word=word):
                self.assertEqual(lexicon.latinize(word), expected)

    def test_path_is_not_the_russian_word_pas(self):
        self.assertEqual(lexicon.latinize("path"), "пэс")

    def test_everything_new_is_pronounceable(self):
        text = ("setup workflow pipeline template terminal model frontend backend database "
                "webhook snapshot mock coverage proxy repo docs")
        self.assertNotRegex(lexicon.latinize(text), r"[A-Za-z]")


if __name__ == "__main__":
    unittest.main()
