"""Манифесты плагина и запуск через bin/vox — то, что ломается тихо."""

import json
import os
import re
import subprocess
import sys
import unittest

from tests.support import IsolatedCase, ROOT


def load(path: str) -> dict:
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


class ManifestsTest(unittest.TestCase):
    def test_versions_are_in_sync(self):
        # Claude Code кеширует плагин по версии: рассинхрон = правки не доедут до пользователя
        plugin = load(".claude-plugin/plugin.json")["version"]
        market = load(".claude-plugin/marketplace.json")["metadata"]["version"]
        self.assertEqual(plugin, market)
        self.assertRegex(plugin, r"^\d+\.\d+\.\d+$")

    def test_plugin_identity(self):
        plugin = load(".claude-plugin/plugin.json")
        market = load(".claude-plugin/marketplace.json")
        self.assertEqual(plugin["name"], "vox")
        self.assertEqual(market["name"], "vox-local")
        self.assertEqual([p["name"] for p in market["plugins"]], ["vox"])
        self.assertEqual(market["plugins"][0]["source"], "./")

    def test_stop_hook_points_to_existing_script(self):
        hooks = load("hooks/hooks.json")["hooks"]["Stop"]
        commands = [h["command"] for entry in hooks for h in entry["hooks"]]
        self.assertEqual(len(commands), 1)
        self.assertIn("${CLAUDE_PLUGIN_ROOT}/hooks/stop-speak.py", commands[0])
        self.assertTrue((ROOT / "hooks" / "stop-speak.py").is_file())

    def test_say_command_frontmatter(self):
        text = (ROOT / "commands" / "say.md").read_text(encoding="utf-8")
        front = re.match(r"---\n(.*?)\n---\n", text, re.S)
        self.assertIsNotNone(front)
        self.assertIn("description:", front.group(1))
        self.assertIn("disable-model-invocation: true", front.group(1))
        self.assertIn('${CLAUDE_PLUGIN_ROOT}/bin/vox', text)
        self.assertIn("--detach", text)

    def test_entry_points_are_executable(self):
        self.assertTrue(os.access(ROOT / "bin" / "vox", os.X_OK))


class LauncherTest(IsolatedCase):
    def vox(self, *args, exe=None, stdin=None):
        return subprocess.run(
            [str(exe or ROOT / "bin" / "vox"), *args],
            input=stdin, capture_output=True, text=True, timeout=60,
            cwd=self.tmp, env=dict(os.environ),
        )

    def test_help(self):
        proc = self.vox("--help")
        self.assertEqual(proc.returncode, 0)
        self.assertIn("usage: vox", proc.stdout)

    def test_dry_run_file_end_to_end(self):
        doc = self.write("doc.md", "# Привет\n\nЗапусти `pnpm install`.\n")
        proc = self.vox(str(doc), "--dry-run")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(proc.stdout, "Привет.\n\nЗапусти пи эн пи эм инсталл.\n")

    def test_dry_run_from_stdin(self):
        proc = self.vox("--dry-run", stdin="Просто текст из пайпа")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(proc.stdout.strip(), "Просто текст из пайпа.")

    def test_works_through_symlink_chain(self):
        # Установка из README: ~/.local/bin/vox -> .../bin/vox (возможно через несколько ссылок)
        first = self.tmp / "bin1" / "vox"
        second = self.tmp / "bin2" / "vox"
        first.parent.mkdir()
        second.parent.mkdir()
        first.symlink_to(ROOT / "bin" / "vox")
        second.symlink_to(first)
        doc = self.write("doc.md", "Через симлинк.")
        proc = self.vox(str(doc), "--dry-run", exe=second)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(proc.stdout.strip(), "Через симлинк.")

    def test_relative_symlink(self):
        link = self.tmp / "rel" / "vox"
        link.parent.mkdir()
        link.symlink_to(os.path.relpath(ROOT / "bin" / "vox", link.parent))
        doc = self.write("doc.md", "Относительная ссылка.")
        proc = self.vox(str(doc), "--dry-run", exe=link)
        self.assertEqual(proc.returncode, 0, proc.stderr)

    def test_python_dash_m(self):
        doc = self.write("doc.md", "Модулем.")
        proc = subprocess.run(
            [sys.executable, "-m", "vox", str(doc), "--dry-run"],
            capture_output=True, text=True, timeout=60, cwd=self.tmp,
            env=dict(os.environ, PYTHONPATH=str(ROOT / "src")),
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(proc.stdout.strip(), "Модулем.")

    def test_missing_file_exit_code_and_message(self):
        proc = self.vox(str(self.tmp / "нет.md"))
        self.assertEqual(proc.returncode, 1)
        self.assertIn("vox:", proc.stderr)

    def test_first_run_creates_config_files(self):
        self.vox("status")
        self.assertTrue((self.tmp / "config" / "vox" / "config.toml").exists())
        self.assertTrue((self.tmp / "config" / "vox" / "lexicon.toml").exists())


if __name__ == "__main__":
    unittest.main()
