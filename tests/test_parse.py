"""Parse-layer tests. These run under a plain python3 -- no Sublime needed."""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from vellum.parse import parse_tokens, split_front_matter  # noqa: E402


def types_of(tokens):
    return [t["type"] for t in tokens if t["type"] != "blank_line"]


class TestFrontMatter(unittest.TestCase):
    def test_extracted_and_counted(self):
        front, body, offset = split_front_matter("---\ntitle: Hi\n---\n# Head\n")
        self.assertEqual(front, "title: Hi")
        self.assertEqual(body, "# Head\n")
        self.assertEqual(offset, 3)

    def test_absent_leaves_text_untouched(self):
        front, body, offset = split_front_matter("# Head\n")
        self.assertIsNone(front)
        self.assertEqual(body, "# Head\n")
        self.assertEqual(offset, 0)

    def test_horizontal_rule_is_not_front_matter(self):
        front, _, _ = split_front_matter("Intro\n\n---\n\nMore\n")
        self.assertIsNone(front)


class TestLineStamping(unittest.TestCase):
    def test_top_level_blocks_carry_source_lines(self):
        text = "# One\n\npara\n\n```go\nfunc main() {}\n```\n\n> quote\n"
        tokens, _, _ = parse_tokens(text)
        stamped = {t["type"]: t["line"] for t in tokens if "line" in t}
        self.assertEqual(stamped["heading"], 0)
        self.assertEqual(stamped["paragraph"], 2)
        self.assertEqual(stamped["block_code"], 4)
        self.assertEqual(stamped["block_quote"], 8)

    def test_lines_are_offset_past_front_matter(self):
        text = "---\na: 1\n---\n# Head\n"
        tokens, front, offset = parse_tokens(text)
        self.assertEqual(front, "a: 1")
        self.assertEqual(offset, 3)
        heading = next(t for t in tokens if t["type"] == "heading")
        self.assertEqual(heading["line"], 3)


class TestGfmCoverage(unittest.TestCase):
    def test_table_alignment_is_parsed(self):
        tokens, _, _ = parse_tokens("| a | b | c |\n|:--|--:|:-:|\n| 1 | 2 | 3 |\n")
        table = tokens[0]
        self.assertEqual(table["type"], "table")
        head = table["children"][0]["children"]
        self.assertEqual([c["attrs"]["align"] for c in head], ["left", "right", "center"])

    def test_fence_language_is_available(self):
        tokens, _, _ = parse_tokens("```go\nfunc main() {}\n```\n")
        self.assertEqual(tokens[0]["type"], "block_code")
        self.assertEqual(tokens[0]["attrs"]["info"], "go")

    def test_mermaid_fence_is_detectable(self):
        tokens, _, _ = parse_tokens("```mermaid\ngraph TD; A-->B;\n```\n")
        self.assertEqual(tokens[0]["attrs"]["info"], "mermaid")

    def test_task_list_checked_state(self):
        tokens, _, _ = parse_tokens("- [x] done\n- [ ] todo\n")
        items = tokens[0]["children"]
        self.assertEqual([i["attrs"]["checked"] for i in items], [True, False])

    def test_strikethrough_and_footnotes(self):
        tokens, _, _ = parse_tokens("~~gone~~ and a note[^1]\n\n[^1]: the note\n")
        self.assertIn("strikethrough", str(tokens))
        self.assertIn("footnote", str(tokens))


class TestMath(unittest.TestCase):
    def test_multiline_block_math(self):
        tokens, _, _ = parse_tokens("$$\nE = mc^2\n$$\n")
        self.assertEqual(types_of(tokens), ["block_math"])
        self.assertEqual(tokens[0]["raw"], "E = mc^2")

    def test_single_line_block_math(self):
        """GitHub accepts $$...$$ on one line; stock mistune does not."""
        tokens, _, _ = parse_tokens("$$E = mc^2$$\n")
        self.assertEqual(types_of(tokens), ["block_math"])
        self.assertEqual(tokens[0]["raw"], "E = mc^2")

    def test_inline_math_still_works(self):
        tokens, _, _ = parse_tokens("energy is $E = mc^2$ exactly\n")
        self.assertIn("inline_math", str(tokens))

    def test_currency_is_not_math(self):
        tokens, _, _ = parse_tokens("It cost $5 and then $6 more.\n")
        self.assertNotIn("inline_math", str(tokens))


if __name__ == "__main__":
    unittest.main(verbosity=2)
