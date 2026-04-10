from __future__ import annotations

import unittest

from final_edu.utils import build_custom_dictionary, tokenize


class UtilsTests(unittest.TestCase):
    def test_tokenize_filters_expanded_korean_stop_words(self) -> None:
        tokens = tokenize("여러분 그러면 이제 sql 데이터 분석 보겠습니다")

        self.assertEqual(tokens, ["sql", "데이터", "분석"])

    def test_tokenize_normalizes_hyphen_digits_without_crossing_whitespace(self) -> None:
        tokens = tokenize("GPT-4 데이터 분석 딥러닝")

        self.assertEqual(tokens, ["gpt4", "데이터", "분석", "딥러닝"])

    def test_build_custom_dictionary_is_idempotent(self) -> None:
        build_custom_dictionary(["시계열분석", "시계열분석"])
        build_custom_dictionary(["시계열분석"])

        tokens = tokenize("시계열분석 소개")

        self.assertIn("시계열분석", tokens)


if __name__ == "__main__":
    unittest.main()
