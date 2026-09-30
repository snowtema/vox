import unittest

from vox import chunker


class ChunksTest(unittest.TestCase):
    def test_empty(self):
        self.assertEqual(chunker.chunks(""), [])
        self.assertEqual(chunker.chunks("  \n\n  "), [])

    def test_short_text_is_single_chunk_without_trailing_pause(self):
        self.assertEqual(chunker.chunks("Привет, мир."), [("Привет, мир.", 0)])

    def test_sentences_are_packed_up_to_limit(self):
        out = chunker.chunks("Раз. Два. Три.", limit=340)
        self.assertEqual(out, [("Раз. Два. Три.", 0)])

    def test_chunks_do_not_cross_sentence_boundary(self):
        sentences = [f"Предложение номер {i} достаточно длинное для теста." for i in range(10)]
        out = chunker.chunks(" ".join(sentences), limit=120)
        self.assertGreater(len(out), 1)
        for chunk, _ in out:
            self.assertTrue(chunk.endswith("."), chunk)
            self.assertLessEqual(len(chunk), 120)

    def test_paragraph_boundary_gets_pause_but_last_chunk_does_not(self):
        out = chunker.chunks("Первый абзац.\n\nВторой абзац.\n\nТретий.", pause_ms=500)
        self.assertEqual([p for _, p in out], [500, 500, 0])

    def test_pause_only_after_last_chunk_of_paragraph(self):
        long_par = " ".join(f"Фраза {i} тут." for i in range(30))
        out = chunker.chunks(long_par + "\n\nКонец.", limit=60, pause_ms=300)
        pauses = [p for _, p in out]
        self.assertEqual(pauses[-1], 0)
        self.assertEqual(pauses.count(300), 1)
        self.assertGreater(len(pauses), 3)

    def test_long_sentence_split_by_commas_first(self):
        sentence = ", ".join(["часть предложения номер " + str(i) for i in range(12)]) + "."
        out = chunker.chunks(sentence, limit=80)
        self.assertGreater(len(out), 1)
        for chunk, _ in out:
            self.assertLessEqual(len(chunk), 80)
        self.assertTrue(all(c.endswith((",", ".")) for c, _ in out))

    def test_long_sentence_without_commas_split_by_words(self):
        sentence = " ".join(["слово"] * 100) + "."
        out = chunker.chunks(sentence, limit=50)
        for chunk, _ in out:
            self.assertLessEqual(len(chunk), 50)
        self.assertEqual(" ".join(c for c, _ in out).split(), sentence.split())

    def test_word_longer_than_limit_is_hard_cut(self):
        out = chunker.chunks("х" * 250, limit=100)
        self.assertEqual([len(c) for c, _ in out], [100, 100, 50])

    def test_no_text_is_lost_or_reordered(self):
        text = ("Первое предложение. Второе, с запятой, и продолжением! "
                "Третье? Четвёртое…\n\nНовый абзац идёт здесь. И ещё один.")
        out = chunker.chunks(text, limit=40)
        self.assertEqual(" ".join(c for c, _ in out).split(), text.split())


if __name__ == "__main__":
    unittest.main()
