import unittest

from vox import config, lexicon
from tests.support import IsolatedCase


class DirsTest(IsolatedCase):
    def test_dirs_follow_xdg_and_are_created(self):
        self.assertEqual(config.config_dir(), self.tmp / "config" / "vox")
        self.assertEqual(config.state_dir(), self.tmp / "state" / "vox")
        self.assertEqual(config.cache_dir(), self.tmp / "cache" / "vox")
        self.assertTrue(config.state_dir().is_dir())
        self.assertTrue(config.cache_dir().is_dir())


class LoadTest(IsolatedCase):
    def test_defaults_without_files(self):
        cfg = config.load()
        self.assertEqual(cfg.engine, "say")
        self.assertTrue(cfg.auto)
        self.assertEqual(cfg.min_chars, 600)
        self.assertEqual(cfg.text.code_blocks, "announce")
        self.assertEqual(cfg.silero.voice, "aidar")
        self.assertEqual(cfg.silero.pitch, "medium")
        self.assertEqual(cfg.silero.sample_rate, 48000)
        self.assertTrue(cfg.silero.put_accent)

    def test_partial_override_keeps_other_defaults(self):
        self.write("config/vox/config.toml",
                   'engine = "silero"\nrate = 150\n\n[say]\nvoice = "Yuri"\n')
        cfg = config.load()
        self.assertEqual(cfg.engine, "silero")
        self.assertEqual(cfg.rate, 150)
        self.assertEqual(cfg.say.voice, "Yuri")
        self.assertEqual(cfg.say.voice_en, "Samantha")     # не тронут
        self.assertEqual(cfg.volume, 0.9)

    def test_unknown_keys_are_ignored(self):
        self.write("config/vox/config.toml", 'nonsense = 1\n[text]\nwhat = "x"\n')
        cfg = config.load()
        self.assertFalse(hasattr(cfg, "nonsense"))
        self.assertFalse(hasattr(cfg.text, "what"))

    def test_broken_toml_falls_back_to_defaults_and_reports(self):
        self.write("config/vox/config.toml", "engine = = =")
        import contextlib, io
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            cfg = config.load()
        self.assertEqual(cfg.engine, "say")
        self.assertIn("не читается", buf.getvalue())

    def test_user_lexicon_is_merged_into_terms(self):
        self.write("config/vox/lexicon.toml", '[terms]\nMyApp = "майапп"\n')
        config.load()
        self.assertEqual(lexicon.TERMS["myapp"], "майапп")

    def test_flat_lexicon_without_terms_table_is_accepted(self):
        self.write("config/vox/lexicon.toml", 'hetzner = "хетцнер-2"\n')
        config.load()
        self.assertEqual(lexicon.TERMS["hetzner"], "хетцнер-2")

    def test_broken_lexicon_does_not_break_load(self):
        self.write("config/vox/lexicon.toml", "[terms\n")
        import contextlib, io
        with contextlib.redirect_stdout(io.StringIO()):
            cfg = config.load()
        self.assertEqual(cfg.engine, "say")


class EnsureFilesTest(IsolatedCase):
    def test_creates_config_and_lexicon(self):
        d = config.ensure_files()
        self.assertEqual(d, config.config_dir())
        self.assertTrue((d / "config.toml").is_file())
        self.assertTrue((d / "lexicon.toml").is_file())

    def test_does_not_overwrite_existing(self):
        path = self.write("config/vox/config.toml", 'engine = "silero"\n')
        config.ensure_files()
        self.assertEqual(path.read_text(), 'engine = "silero"\n')

    def test_default_file_is_consistent_with_dataclass_defaults(self):
        config.ensure_files()
        self.assertEqual(config.load(), config.Config())

    def test_default_lexicon_loads_cleanly(self):
        config.ensure_files()
        before = dict(lexicon.TERMS)
        config.load()
        self.assertEqual(lexicon.TERMS, before)


if __name__ == "__main__":
    unittest.main()
