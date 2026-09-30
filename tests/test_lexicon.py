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

    @unittest.expectedFailure
    def test_suffixes_ending_in_e_are_not_shadowed_by_silent_e(self):
        # Баг: «немая e» срезается раньше проверки суффиксов, поэтому
        # ture -> «чер» и dge -> «дж» недостижимы (picture -> «пиктур»).
        self.assertTrue(lexicon.translit("picture").endswith("чер"))
        self.assertTrue(lexicon.translit("bridge").endswith("дж"))


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


if __name__ == "__main__":
    unittest.main()
