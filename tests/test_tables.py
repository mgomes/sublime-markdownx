"""Table column solver tests. Run under plain python3 -- no Sublime needed."""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from markdownx.tables import (  # noqa: E402
    layout,
    pad,
    solve_widths,
    text_width,
    truncate,
)


class TestWidth(unittest.TestCase):
    def test_ascii_counts_one_per_char(self):
        self.assertEqual(text_width("hello"), 5)

    def test_cjk_counts_two_per_char(self):
        self.assertEqual(text_width("日本語"), 6)

    def test_mixed_script(self):
        self.assertEqual(text_width("go 言語"), 7)

    def test_combining_marks_are_free(self):
        # "e" + combining acute renders as one cell.
        self.assertEqual(text_width("é"), 1)

    def test_empty(self):
        self.assertEqual(text_width(""), 0)


class TestTruncate(unittest.TestCase):
    def test_leaves_short_text_alone(self):
        self.assertEqual(truncate("abc", 10), "abc")

    def test_clips_with_ellipsis(self):
        self.assertEqual(truncate("abcdefgh", 4), "abc…")
        self.assertEqual(text_width(truncate("abcdefgh", 4)), 4)

    def test_never_exceeds_budget_with_wide_chars(self):
        for width in range(1, 8):
            self.assertLessEqual(text_width(truncate("日本語テキスト", width)), width)

    def test_zero_width_budget(self):
        self.assertEqual(truncate("abc", 0), "")


class TestPad(unittest.TestCase):
    def test_left_align_is_default(self):
        self.assertEqual(pad("ab", 5, None), "ab   ")

    def test_right_align(self):
        self.assertEqual(pad("ab", 5, "right"), "   ab")

    def test_center_align_biases_left(self):
        self.assertEqual(pad("ab", 5, "center"), " ab  ")

    def test_cjk_padding_accounts_for_double_width(self):
        self.assertEqual(pad("日本", 6, None), "日本  ")
        self.assertEqual(text_width(pad("日本", 6, None)), 6)

    def test_overlong_text_is_returned_unchanged(self):
        self.assertEqual(pad("abcdef", 3, None), "abcdef")


class TestSolveWidths(unittest.TestCase):
    def test_natural_width_is_widest_cell(self):
        rows = [["a", "bbb"], ["cccc", "d"]]
        self.assertEqual(solve_widths(rows), [4, 3])

    def test_ragged_rows_are_tolerated(self):
        rows = [["a", "b", "c"], ["dd"]]
        self.assertEqual(solve_widths(rows), [2, 1, 1])

    def test_shrinks_widest_column_first(self):
        rows = [["short", "a" * 40]]
        widths = solve_widths(rows, max_total=30)
        self.assertEqual(widths[0], 5)
        self.assertLess(widths[1], 40)

    def test_respects_total_budget(self):
        rows = [["a" * 30, "b" * 30, "c" * 30]]
        widths = solve_widths(rows, max_total=60)
        self.assertLessEqual(sum(widths) + 6, 60)

    def test_impossible_budget_degrades_instead_of_looping(self):
        rows = [["a" * 20, "b" * 20]]
        widths = solve_widths(rows, max_total=1)
        self.assertEqual(widths, [5, 5])

    def test_empty_input(self):
        self.assertEqual(solve_widths([]), [])


class TestLayout(unittest.TestCase):
    def test_every_row_has_equal_shape(self):
        rows = [["Name", "Qty"], ["Bolt", "12"], ["Very long widget", "3"]]
        out = layout(rows, ["left", "right"])
        self.assertTrue(all(len(r) == 2 for r in out))
        for column in range(2):
            widths = {text_width(r[column]) for r in out}
            self.assertEqual(len(widths), 1, "column %d ragged: %s" % (column, widths))

    def test_alignment_is_applied_per_column(self):
        rows = [["a", "a", "a"], ["xxxx", "xxxx", "xxxx"]]
        out = layout(rows, ["left", "right", "center"])
        self.assertEqual(out[0], ["a   ", "   a", " a  "])

    def test_cjk_columns_stay_aligned(self):
        rows = [["Name", "説明"], ["日本語", "a"]]
        out = layout(rows, ["left", "left"])
        for column in range(2):
            widths = {text_width(r[column]) for r in out}
            self.assertEqual(len(widths), 1)

    def test_ragged_input_is_filled_out(self):
        out = layout([["a", "b"], ["c"]], ["left", "left"])
        self.assertEqual(len(out[1]), 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
