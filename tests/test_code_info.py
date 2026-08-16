"""Tests for fence info-string parsing.

``markdownx.code`` imports sublime at module scope, so the pure helper is loaded
from source rather than importing the module. Syntax resolution itself needs a
running editor and is exercised through dev/probe.sh.
"""

import os
import re
import sys
import types
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load_info_module():
    source = open(os.path.join(ROOT, "markdownx", "code.py"), encoding="utf-8").read()

    chunks = ["import re"]
    for block in re.split(r"\n(?=def |class |[A-Z_]+ = )", source):
        if block.startswith(("def normalize_info", "NON_CODE_INFO = ", "PLAIN_TEXT_INFO = ")):
            chunks.append(block)

    module = types.ModuleType("info_only")
    exec(compile("\n".join(chunks), "code.py", "exec"), module.__dict__)
    return module


info = _load_info_module()


class TestNormalizeInfo(unittest.TestCase):
    def test_plain_language(self):
        self.assertEqual(info.normalize_info("python"), "python")

    def test_lowercased(self):
        self.assertEqual(info.normalize_info("Vibescript"), "vibescript")
        self.assertEqual(info.normalize_info("GO"), "go")

    def test_surrounding_whitespace(self):
        self.assertEqual(info.normalize_info("  ruby  "), "ruby")

    def test_only_the_first_word_counts(self):
        """Fences carry more than a language: ```python title="x" is common."""
        self.assertEqual(info.normalize_info('python title="setup.py"'), "python")

    def test_line_ranges_are_stripped(self):
        self.assertEqual(info.normalize_info("js{1,3-5}"), "js")

    def test_comma_separated_attributes(self):
        self.assertEqual(info.normalize_info("go,linenos"), "go")

    def test_colon_separated_attributes(self):
        self.assertEqual(info.normalize_info("ts:src/main.ts"), "ts")

    def test_empty_and_none(self):
        self.assertEqual(info.normalize_info(""), "")
        self.assertEqual(info.normalize_info(None), "")

    def test_extension_style_labels_survive(self):
        """Extensions are resolved against Sublime's syntax table downstream."""
        for label in ("vibe", "cr", "rs", "kt"):
            self.assertEqual(info.normalize_info(label), label)

    def test_names_with_symbols_are_preserved(self):
        self.assertEqual(info.normalize_info("c++"), "c++")
        self.assertEqual(info.normalize_info("C#"), "c#")


class TestConstants(unittest.TestCase):
    def test_non_code_fences_listed(self):
        self.assertIn("mermaid", info.NON_CODE_INFO)

    def test_plain_text_labels_include_empty(self):
        self.assertIn("", info.PLAIN_TEXT_INFO)
        self.assertIn("text", info.PLAIN_TEXT_INFO)


if __name__ == "__main__":
    unittest.main(verbosity=2)
