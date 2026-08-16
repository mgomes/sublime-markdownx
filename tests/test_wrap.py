"""Tests for soft-wrapping highlighted code lines.

``vellum.code`` imports sublime at module scope, so the two functions under test
are loaded from source into a bare module instead.
"""

import os
import re
import sys
import types
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load_wrap_module():
    """Load just the markup helpers from code.py, without importing sublime."""
    source = open(os.path.join(ROOT, "vellum", "code.py"), encoding="utf-8").read()
    wanted = ("def _tokenize", "def wrap_line", "def split_lines")

    chunks = []
    for block in re.split(r"\n(?=def |class )", source):
        if block.startswith(wanted):
            chunks.append(block)

    module = types.ModuleType("wrap_only")
    exec(compile("\n".join(chunks), "code.py", "exec"), module.__dict__)
    return module


wrap = _load_wrap_module()


def visible(html):
    """Visible text of a fragment, with entities counted as one character."""
    without_tags = re.sub(r"<[^>]+>", "", html)
    return re.sub(r"&[a-z]+;|&#\d+;", ".", without_tags)


class TestTokenize(unittest.TestCase):
    def test_entities_are_one_character(self):
        kinds = [k for k, _ in wrap._tokenize("a&nbsp;b")]
        self.assertEqual(kinds, ["char", "char", "char"])

    def test_tags_are_not_characters(self):
        pairs = list(wrap._tokenize('<span style="color:#fff;">ab</span>'))
        self.assertEqual([t for k, t in pairs if k == "char"], ["a", "b"])

    def test_unterminated_tag_does_not_hang(self):
        self.assertEqual(list(wrap._tokenize("a<span")), [("char", "a"), ("char", "<span")])

    def test_bare_ampersand(self):
        self.assertEqual([t for k, t in wrap._tokenize("a & b") if k == "char"], list("a & b"))


class TestWrapLine(unittest.TestCase):
    def test_short_line_is_untouched(self):
        html = '<span style="color:#fff;">short</span>'
        self.assertEqual(wrap.wrap_line(html, 40), html)

    def test_long_plain_line_is_broken(self):
        html = "x" * 100
        out = wrap.wrap_line(html, 20)
        self.assertIn("<br>", out)
        for segment in out.split("<br>"):
            self.assertLessEqual(len(visible(segment)), 22)

    def test_no_visible_characters_are_lost(self):
        html = "abcdefghij" * 10
        out = wrap.wrap_line(html, 15)
        self.assertEqual(visible(out).replace(".", ""), html)

    def test_span_is_closed_and_reopened_across_a_break(self):
        html = '<span style="color:#abc;">%s</span>' % ("y" * 60)
        out = wrap.wrap_line(html, 20)
        self.assertEqual(out.count("<span"), out.count("</span>"))
        self.assertGreater(out.count("<span"), 1)

    def test_colour_survives_the_break(self):
        html = '<span style="color:#abcdef;">%s</span>' % ("z" * 50)
        out = wrap.wrap_line(html, 20)
        for segment in out.split("<br>")[1:]:
            self.assertIn("#abcdef", segment)

    def test_entities_count_as_single_columns(self):
        html = "&nbsp;" * 60
        out = wrap.wrap_line(html, 20)
        for segment in out.split("<br>"):
            self.assertLessEqual(len(visible(segment)), 22)

    def test_tiny_width_is_refused_rather_than_shredding_output(self):
        html = "abcdef"
        self.assertEqual(wrap.wrap_line(html, 3), html)

    def test_multiple_spans_keep_their_own_colours(self):
        html = (
            '<span style="color:#111111;">%s</span>'
            '<span style="color:#222222;">%s</span>' % ("a" * 30, "b" * 30)
        )
        out = wrap.wrap_line(html, 25)
        self.assertEqual(out.count("<span"), out.count("</span>"))
        self.assertEqual(visible(out).replace(".", ""), "a" * 30 + "b" * 30)


if __name__ == "__main__":
    unittest.main(verbosity=2)
