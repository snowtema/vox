import json
import os
import unittest
from pathlib import Path
from unittest import mock

from vox import transcript
from tests.support import IsolatedCase


def user(text: str | None = None, *, tool_result: bool = False, cwd: str | None = None) -> dict:
    content = [{"type": "tool_result", "content": "ok"}] if tool_result else text
    entry = {"type": "user", "message": {"role": "user", "content": content}}
    if cwd:
        entry["cwd"] = cwd
    return entry


def assistant(*blocks, sidechain: bool = False) -> dict:
    content = []
    for b in blocks:
        if isinstance(b, str):
            content.append({"type": "text", "text": b})
        else:
            content.append(b)
    entry = {"type": "assistant", "message": {"role": "assistant", "content": content}}
    if sidechain:
        entry["isSidechain"] = True
    return entry


TOOL_USE = {"type": "tool_use", "id": "t1", "name": "Bash", "input": {}}
THINKING = {"type": "thinking", "thinking": "скрытые мысли"}


class LastAssistantTextTest(IsolatedCase):
    def dump(self, entries: list[dict], raw_lines: list[str] | None = None) -> Path:
        lines = [json.dumps(e, ensure_ascii=False) for e in entries] + (raw_lines or [])
        return self.write("t.jsonl", "\n".join(lines) + "\n")

    def test_simple_answer(self):
        path = self.dump([user("привет"), assistant("Здравствуй!")])
        self.assertEqual(transcript.last_assistant_text(path), "Здравствуй!")

    def test_only_last_turn_is_returned(self):
        path = self.dump([user("раз"), assistant("Ответ один"),
                          user("два"), assistant("Ответ два")])
        self.assertEqual(transcript.last_assistant_text(path), "Ответ два")

    def test_final_text_after_tool_calls_by_default(self):
        path = self.dump([
            user("сделай"),
            assistant("Сейчас посмотрю.", TOOL_USE),
            user(tool_result=True),
            assistant(TOOL_USE),
            user(tool_result=True),
            assistant("Итог работы."),
        ])
        self.assertEqual(transcript.last_assistant_text(path), "Итог работы.")

    def test_whole_turn_includes_remarks_between_tools(self):
        path = self.dump([
            user("сделай"),
            assistant("Сейчас посмотрю.", TOOL_USE),
            user(tool_result=True),
            assistant("Итог работы."),
        ])
        self.assertEqual(transcript.last_assistant_text(path, whole_turn=True),
                         "Сейчас посмотрю.\n\nИтог работы.")

    def test_consecutive_text_entries_are_joined(self):
        path = self.dump([user("вопрос"), assistant("Часть раз."), assistant("Часть два.")])
        self.assertEqual(transcript.last_assistant_text(path), "Часть раз.\n\nЧасть два.")

    def test_thinking_blocks_are_never_read(self):
        path = self.dump([user("x"), assistant(THINKING, "Видимый ответ")])
        self.assertEqual(transcript.last_assistant_text(path), "Видимый ответ")

    def test_subagent_output_is_ignored(self):
        path = self.dump([user("x"), assistant("Главный ответ"),
                          assistant("Болтовня сабагента", sidechain=True)])
        self.assertEqual(transcript.last_assistant_text(path), "Главный ответ")

    def test_string_content_is_supported(self):
        entry = {"type": "assistant", "message": {"content": "Просто строка"}}
        path = self.dump([user("x"), entry])
        self.assertEqual(transcript.last_assistant_text(path), "Просто строка")

    def test_only_tool_calls_yield_empty(self):
        path = self.dump([user("x"), assistant(TOOL_USE)])
        self.assertEqual(transcript.last_assistant_text(path), "")

    def test_broken_and_blank_lines_are_skipped(self):
        path = self.dump([user("x"), assistant("Живой ответ")],
                         raw_lines=["", "{не json", "   "])
        self.assertEqual(transcript.last_assistant_text(path), "Живой ответ")

    def test_missing_file(self):
        self.assertEqual(transcript.last_assistant_text(self.tmp / "нет.jsonl"), "")


class FindTranscriptTest(IsolatedCase):
    def make(self, slug: str, name: str, cwd: str | None, mtime: int) -> Path:
        entries = [user("x", cwd=cwd), assistant("ответ")]
        path = self.write(
            f"claude/projects/{slug}/{name}.jsonl",
            "\n".join(json.dumps(e) for e in entries) + "\n",
        )
        os.utime(path, (mtime, mtime))
        return path

    def test_projects_dir_honours_claude_config_dir(self):
        self.assertEqual(transcript.projects_dir(), self.tmp / "claude" / "projects")

    def test_no_projects_dir(self):
        self.assertIsNone(transcript.find_transcript(str(self.tmp)))

    def test_matches_by_cwd_not_by_freshness(self):
        mine = self.make("a", "mine", str(self.tmp / "proj"), mtime=1_000)
        self.make("b", "other", str(self.tmp / "other"), mtime=2_000)
        (self.tmp / "proj").mkdir()
        self.assertEqual(transcript.find_transcript(str(self.tmp / "proj")), mine)

    def test_foreign_project_is_not_picked_up_by_default(self):
        # Озвучить ответ из чужого проекта хуже, чем честно сказать «не найдено»
        self.make("a", "old", "/somewhere/a", mtime=1_000)
        self.make("b", "new", "/somewhere/b", mtime=2_000)
        self.assertIsNone(transcript.find_transcript(str(self.tmp)))

    def test_fallback_takes_newest_from_any_project(self):
        self.make("a", "old", "/somewhere/a", mtime=1_000)
        newest = self.make("b", "new", "/somewhere/b", mtime=2_000)
        self.assertEqual(transcript.find_transcript(str(self.tmp), fallback=True), newest)

    def test_fallback_with_no_transcripts_at_all(self):
        (self.tmp / "claude" / "projects").mkdir(parents=True)
        self.assertIsNone(transcript.find_transcript(str(self.tmp), fallback=True))

    def test_matches_by_project_folder_name_when_cwd_changed(self):
        # Сессию стартовали в проекте, а потом сделали cd: cwd в записях другой
        proj = self.tmp / "my.proj"
        proj.mkdir()
        mine = self.make(transcript._slug(str(proj)), "s", "/elsewhere/after/cd", mtime=1_000)
        self.make("other", "new", "/somewhere/b", mtime=2_000)
        self.assertEqual(transcript.find_transcript(str(proj)), mine)

    def test_matches_session_that_moved_into_the_directory_after_start(self):
        # Сессия стартовала в родительской папке и потом сделала cd в проект:
        # первая запись — родитель, последняя — проект (именно так живёт эта сессия)
        proj = self.tmp / "parent" / "proj"
        proj.mkdir(parents=True)
        entries = [user("x", cwd=str(proj.parent)), assistant("a"), user("y", cwd=str(proj)),
                   assistant("b")]
        path = self.write("claude/projects/parent-slug/s.jsonl",
                          "\n".join(json.dumps(e) for e in entries) + "\n")
        os.utime(path, (1_000, 1_000))
        self.make("other", "new", "/somewhere/b", mtime=2_000)
        self.assertEqual(transcript.find_transcript(str(proj)), path)

    def test_last_cwd_reads_only_the_tail_of_a_big_file(self):
        big = self.write("big.jsonl", json.dumps({"cwd": "/old"}) + "\n"
                         + (json.dumps({"type": "user", "pad": "x" * 500}) + "\n") * 1000
                         + json.dumps({"cwd": "/new"}) + "\n")
        self.assertGreater(big.stat().st_size, transcript.TAIL_BYTES)
        self.assertEqual(transcript._last_cwd(big), "/new")
        self.assertEqual(transcript._first_cwd(big), "/old")

    def test_last_cwd_ignores_a_line_cut_by_the_tail_window(self):
        with mock.patch.object(transcript, "TAIL_BYTES", 120):
            path = self.write("t.jsonl", json.dumps({"cwd": "/a" * 200}) + "\n"
                              + json.dumps({"cwd": "/b"}) + "\n")
            self.assertEqual(transcript._last_cwd(path), "/b")

    def test_last_cwd_of_unreadable_or_cwd_less_file(self):
        self.assertIsNone(transcript._last_cwd(self.tmp / "нет.jsonl"))
        self.assertIsNone(transcript._last_cwd(self.write("e.jsonl", '{"type": "user"}\n')))

    def test_slug_replaces_everything_but_alphanumerics(self):
        self.assertEqual(transcript._slug("/Users/a.b/My Proj_1"), "-Users-a-b-My-Proj-1")

    def test_old_transcripts_beyond_scan_limit_are_not_read(self):
        proj = self.tmp / "proj"
        proj.mkdir()
        self.make("a", "mine", str(proj), mtime=1_000)
        for i in range(3):
            self.make(f"x{i}", "n", f"/other/{i}", mtime=2_000 + i)
        with mock.patch.object(transcript, "SCAN_LIMIT", 3):
            self.assertIsNone(transcript.find_transcript(str(proj)))

    def test_cwd_is_resolved(self):
        proj = self.tmp / "proj"
        proj.mkdir()
        link = self.tmp / "link"
        link.symlink_to(proj)
        mine = self.make("a", "mine", str(proj), mtime=1_000)
        self.make("b", "other", "/elsewhere", mtime=2_000)
        self.assertEqual(transcript.find_transcript(str(link)), mine)


if __name__ == "__main__":
    unittest.main()
