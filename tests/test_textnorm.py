import unittest

from vox import config, textnorm


def norm(md: str, **overrides) -> str:
    cfg = config.TextCfg()
    for key, value in overrides.items():
        setattr(cfg, key, value)
    return textnorm.normalize(md, cfg)


class HelpersTest(unittest.TestCase):
    def test_plural_ru(self):
        cases = {1: "1 строка", 2: "2 строки", 5: "5 строк", 11: "11 строк",
                 21: "21 строка", 22: "22 строки", 112: "112 строк"}
        for n, expected in cases.items():
            with self.subTest(n=n):
                self.assertEqual(textnorm.plural_ru(n, "строка", "строки", "строк"), expected)

    def test_detect_lang(self):
        self.assertEqual(textnorm.detect_lang("Привет, мир"), "ru")
        self.assertEqual(textnorm.detect_lang("Hello world, this is English text"), "en")
        self.assertEqual(textnorm.detect_lang(""), "ru")
        self.assertEqual(textnorm.detect_lang("123 456"), "ru")

    def test_detect_lang_tolerates_technical_latin_in_russian_text(self):
        self.assertEqual(textnorm.detect_lang("Поправил баг в useEffect и запустил pnpm"), "ru")


class CodeBlocksTest(unittest.TestCase):
    MD = "Вот код:\n\n```ts\nconst a = 1\n\nconst b = 2\n```\n\nГотово."

    def test_announce_counts_non_empty_lines(self):
        out = norm(self.MD)
        self.assertIn("Далее код на тэ эс, 2 строки.", out)
        self.assertNotIn("const", out)

    def test_announce_without_language(self):
        out = norm("Пример:\n\n```\nx\n```\n")
        self.assertIn("Далее код, 1 строка.", out)

    def test_skip_drops_block(self):
        out = norm(self.MD, code_blocks="skip")
        self.assertNotIn("Далее код", out)
        self.assertNotIn("const", out)
        self.assertIn("Готово.", out)

    def test_read_keeps_block_body(self):
        out = norm(self.MD, code_blocks="read")
        self.assertIn("конст а = 1", out)       # читается как обычный текст, латиница — по-русски
        self.assertIn("конст б = 2", out)
        self.assertNotIn("`", out)
        self.assertNotIn("Далее код", out)

    def test_unterminated_fence_does_not_swallow_error(self):
        out = norm("Текст.\n\n```py\nprint(1)\nprint(2)")
        self.assertIn("Далее код на пай, 2 строки.", out)

    def test_tilde_fence(self):
        out = norm("Текст.\n\n~~~\na\n~~~\n")
        self.assertIn("Далее код, 1 строка.", out)

    def test_inline_code_loses_backticks(self):
        self.assertEqual(norm("Запусти `make` сейчас.", latin="off"), "Запусти make сейчас.")

    def test_huge_inline_code_is_replaced(self):
        out = norm("Вот: `" + "x" * 120 + "` и всё.")
        self.assertIn("фрагмент кода", out)


class TablesTest(unittest.TestCase):
    MD = "Итоги:\n\n| имя | значение |\n|---|---|\n| а | 1 |\n| б | 2 |\n| в | - |\n"

    def test_announce(self):
        out = norm(self.MD)
        self.assertIn("Далее таблица, 3 строки.", out)
        self.assertNotIn("|", out)

    def test_skip(self):
        out = norm(self.MD, tables="skip")
        self.assertNotIn("таблица", out)
        self.assertNotIn("|", out)

    def test_read_row_by_row_with_headers(self):
        out = norm(self.MD, tables="read")
        self.assertIn("имя: а; значение: 1.", out)
        self.assertIn("имя: б; значение: 2.", out)
        self.assertIn("имя: в.", out)          # пустая ячейка («-») пропущена
        self.assertNotIn("|", out)

    def test_pipe_in_plain_text_is_not_a_table(self):
        out = norm("Используй a | b для канала.")
        self.assertNotIn("таблица", out)


class InlineMarkupTest(unittest.TestCase):
    def test_links_keep_label_only(self):
        self.assertEqual(norm("Смотри [документация](https://example.com/docs) тут."),
                         "Смотри документация тут.")

    def test_bare_urls_become_word(self):
        out = norm("Сайт https://example.com/very/long/path работает.")
        self.assertIn("ссылка", out)
        self.assertNotIn("http", out)

    def test_images_are_dropped(self):
        out = norm("До ![схема](pic.png) после.")
        self.assertNotIn("схема", out)
        self.assertNotIn("png", out)

    def test_bold_italic_strike(self):
        self.assertEqual(norm("Это **важно**, *очень* и ~~нет~~."), "Это важно, очень и нет.")

    def test_underscores_inside_identifiers_are_not_italics(self):
        self.assertEqual(norm("Переменная snake_case_name есть.", latin="off"),
                         "Переменная snake_case_name есть.")

    @unittest.expectedFailure
    def test_spaced_asterisks_are_not_italics(self):
        # Баг: `* 3 *` принимается за курсив и звёздочки пропадают («2 3 4»),
        # хотя выделение в markdown не может начинаться и кончаться пробелом.
        self.assertIn("2 * 3 * 4", norm("Считаем 2 * 3 * 4 вручную.", latin="off"))

    def test_html_tags_dropped(self):
        self.assertEqual(norm("Текст <br> дальше."), "Текст дальше.")

    def test_footnotes_dropped(self):
        self.assertNotIn("^", norm("Факт[^1] подтверждён."))

    def test_emoji_and_box_chars_dropped(self):
        out = norm("Готово 🎉 ✓ всё ├── дерево")
        self.assertNotIn("🎉", out)
        self.assertNotIn("✓", out)
        self.assertNotIn("├", out)

    def test_ansi_escape_codes_dropped(self):
        self.assertEqual(norm("\x1b[31mОшибка\x1b[0m найдена"), "Ошибка найдена.")

    def test_zero_width_characters_dropped(self):
        self.assertEqual(norm("сло​во"), "слово.")

    def test_dash_becomes_comma_pause(self):
        self.assertEqual(norm("Слово — слово"), "Слово, слово.")

    def test_dash_after_comma_does_not_double_up(self):
        self.assertEqual(norm("Слово, — слово"), "Слово, слово.")

    def test_frontmatter_removed(self):
        out = norm("---\ntitle: x\n---\nТекст документа.")
        self.assertEqual(out, "Текст документа.")


class StructureTest(unittest.TestCase):
    def test_headings_become_sentences(self):
        out = norm("# Заголовок\n\nТекст.\n\n## Подраздел:\n\nЕщё.")
        self.assertEqual(out, "Заголовок.\n\nТекст.\n\nПодраздел.\n\nЕщё.")

    def test_bullet_and_numbered_lists(self):
        out = norm("Шаги:\n\n- первый\n- второй\n\n1. раз\n2) два\n")
        self.assertIn("первый. второй.", out)
        self.assertIn("раз. два.", out)
        self.assertNotIn("- ", out)

    def test_checkboxes(self):
        out = norm("- [x] Готово\n- [ ] Осталось")
        self.assertIn("сделано: Готово.", out)
        self.assertIn("не сделано: Осталось.", out)

    def test_blockquote_marker_removed(self):
        self.assertEqual(norm("> Цитата"), "Цитата.")

    def test_horizontal_rule_removed(self):
        out = norm("До.\n\n---\n\nПосле.")
        self.assertEqual(out, "До.\n\nПосле.")

    def test_single_newlines_join_blank_lines_split(self):
        out = norm("строка раз\nстрока два\n\nновый абзац")
        self.assertEqual(out, "строка раз строка два.\n\nновый абзац.")

    def test_every_paragraph_ends_with_punctuation(self):
        out = norm("Первый\n\nВторой!\n\nТретий?\n\nЧетвёртый")
        for par in out.split("\n\n"):
            self.assertIn(par[-1], ".!?")

    def test_empty_and_noise_only_input(self):
        self.assertEqual(norm(""), "")
        self.assertEqual(norm("\n\n   \n"), "")
        self.assertEqual(norm("---\n\n***\n"), "")

    def test_crlf_normalized(self):
        self.assertEqual(norm("раз\r\n\r\nдва"), "раз.\n\nдва.")


class PathsAndNumbersTest(unittest.TestCase):
    def test_long_path_reduced_to_file_name(self):
        out = norm("Правка в `src/app/components/Hero.tsx` готова.")
        self.assertNotIn("src", out)
        self.assertNotIn("/", out)
        self.assertIn("х+иро тэ эс икс", out)

    def test_short_path_is_kept_as_words(self):
        out = norm("Файл `lib/utils.ts` тоже.")
        self.assertIn("либ", out)

    def test_file_line_reference(self):
        out = norm("Смотри `next.config.mjs:12` сейчас.")
        self.assertIn("строка 12", out)
        self.assertIn("эм джей эс", out)
        self.assertNotIn(":12", out)

    def test_env_vars_lose_dollar_and_braces(self):
        out = norm("Задай ${CLAUDE_PLUGIN_ROOT} и $HOME заранее.")
        self.assertNotIn("$", out)
        self.assertNotIn("{", out)

    def test_hash_number(self):
        self.assertIn("номер 12", norm("Смотри PR #12 сейчас."))

    def test_plus_between_spaces_is_spoken(self):
        self.assertIn("плюс", norm("Два + два равно четыре."))


class LanguageTest(unittest.TestCase):
    def test_russian_text_gets_latin_transliterated(self):
        out = norm("Запусти pnpm install и проверь git.")
        self.assertNotRegex(out, r"[A-Za-z]")
        self.assertIn("пи эн пи эм", out)

    def test_latin_off_leaves_latin(self):
        out = norm("Запусти pnpm install.", latin="off")
        self.assertIn("pnpm install", out)

    def test_english_document_is_not_latinized(self):
        out = norm("Run pnpm install and check the docs carefully today.")
        self.assertIn("pnpm install", out)


class LimitsTest(unittest.TestCase):
    def test_max_chars_truncates_on_word_boundary(self):
        text = " ".join(["слово"] * 400)
        out = norm(text, max_chars=200)
        self.assertLessEqual(len(out), 200 + len(" … дальше пропущено."))
        self.assertTrue(out.endswith("слово … дальше пропущено."))   # обрезка по границе слова

    def test_max_chars_zero_disables_limit(self):
        text = " ".join(["слово"] * 400)
        self.assertNotIn("пропущено", norm(text, max_chars=0))

    def test_short_text_untouched_by_limit(self):
        self.assertNotIn("пропущено", norm("Коротко.", max_chars=50))


if __name__ == "__main__":
    unittest.main()
