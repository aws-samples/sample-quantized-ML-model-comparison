"""Unit tests for benchmark runner error handling and edge cases.

Covers:
- load_benchmark_dataset fallback behaviour
- Default dataset validation
- compute_exact_match
- compute_bleu_score
- compute_rouge_l_score
- compute_degradation_report (empty, all-errored, valid, identical scores, per-category)
- Payload builders (text-only and image prompts)
- run_benchmark with mocked endpoints
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from benchmark_runner import (
    BenchmarkEntry,
    BenchmarkResult,
    DegradationReport,
    compute_bleu_score,
    compute_degradation_report,
    compute_exact_match,
    compute_rouge_l_score,
    get_default_dataset,
    load_benchmark_dataset,
    run_benchmark,
)
from comparison_utils import (
    build_full_precision_payload,
    build_quantized_payload,
)


# ---------------------------------------------------------------------------
# 1. load_benchmark_dataset fallback
# ---------------------------------------------------------------------------


class TestLoadBenchmarkDatasetFallback:
    """load_benchmark_dataset falls back to default for None / missing paths."""

    def test_none_path_returns_default(self) -> None:
        result = load_benchmark_dataset(None)
        assert isinstance(result, list)
        assert len(result) > 0
        assert result == get_default_dataset()

    def test_nonexistent_file_returns_default(self) -> None:
        result = load_benchmark_dataset("does_not_exist_xyz.csv")
        assert isinstance(result, list)
        assert len(result) > 0
        assert result == get_default_dataset()


# ---------------------------------------------------------------------------
# 2. Default dataset validation
# ---------------------------------------------------------------------------


class TestDefaultDataset:
    """The built-in default dataset meets minimum requirements."""

    def test_at_least_10_entries(self) -> None:
        ds = get_default_dataset()
        assert len(ds) >= 10

    def test_covers_vqa_category(self) -> None:
        categories = {e.category for e in get_default_dataset() if e.category}
        assert "VQA" in categories

    def test_covers_ocr_category(self) -> None:
        categories = {e.category for e in get_default_dataset() if e.category}
        assert "OCR" in categories

    def test_covers_image_description_category(self) -> None:
        categories = {e.category for e in get_default_dataset() if e.category}
        assert "image_description" in categories

    def test_all_entries_are_benchmark_entry(self) -> None:
        ds = get_default_dataset()
        assert all(isinstance(e, BenchmarkEntry) for e in ds)


# ---------------------------------------------------------------------------
# 3. compute_exact_match
# ---------------------------------------------------------------------------


class TestComputeExactMatch:
    """Exact match is case-insensitive and returns 0.0 or 1.0."""

    def test_matching_strings(self) -> None:
        assert compute_exact_match("cat", "cat") == 1.0

    def test_case_insensitive_match(self) -> None:
        assert compute_exact_match("Cat", "cat") == 1.0
        assert compute_exact_match("HOLLYWOOD", "hollywood") == 1.0

    def test_whitespace_tolerance(self) -> None:
        assert compute_exact_match("  cat  ", "cat") == 1.0

    def test_different_strings(self) -> None:
        assert compute_exact_match("dog", "cat") == 0.0

    def test_clearly_different(self) -> None:
        assert compute_exact_match("hello world", "goodbye universe") == 0.0


# ---------------------------------------------------------------------------
# 4. compute_bleu_score
# ---------------------------------------------------------------------------


class TestComputeBleuScore:
    """BLEU score edge cases and range validation."""

    def test_empty_generated(self) -> None:
        assert compute_bleu_score("", "some reference") == 0.0

    def test_empty_expected(self) -> None:
        assert compute_bleu_score("some text", "") == 0.0

    def test_both_empty(self) -> None:
        assert compute_bleu_score("", "") == 0.0

    def test_identical_strings(self) -> None:
        score = compute_bleu_score("the cat sat on the mat", "the cat sat on the mat")
        assert score == pytest.approx(1.0)

    def test_non_empty_in_range(self) -> None:
        score = compute_bleu_score("a cat is sitting outside", "the cat sat on the mat")
        assert 0.0 <= score <= 1.0

    def test_completely_different(self) -> None:
        score = compute_bleu_score("xyz abc", "the cat sat on the mat")
        assert 0.0 <= score <= 1.0


# ---------------------------------------------------------------------------
# 5. compute_rouge_l_score
# ---------------------------------------------------------------------------


class TestComputeRougeLScore:
    """ROUGE-L score edge cases and range validation."""

    def test_empty_generated(self) -> None:
        assert compute_rouge_l_score("", "some reference") == 0.0

    def test_empty_expected(self) -> None:
        assert compute_rouge_l_score("some text", "") == 0.0

    def test_both_empty(self) -> None:
        assert compute_rouge_l_score("", "") == 0.0

    def test_whitespace_only_generated(self) -> None:
        assert compute_rouge_l_score("   ", "some reference") == 0.0

    def test_identical_strings(self) -> None:
        score = compute_rouge_l_score("the cat sat on the mat", "the cat sat on the mat")
        assert score == pytest.approx(1.0)

    def test_non_empty_in_range(self) -> None:
        score = compute_rouge_l_score("a cat is sitting outside", "the cat sat on the mat")
        assert 0.0 <= score <= 1.0


# ---------------------------------------------------------------------------
# 6. compute_degradation_report
# ---------------------------------------------------------------------------


def _make_result(
    q_metrics: dict[str, float],
    fp_metrics: dict[str, float],
    category: str | None = None,
    error: str | None = None,
) -> BenchmarkResult:
    """Helper to build a BenchmarkResult with given metrics."""
    return BenchmarkResult(
        entry=BenchmarkEntry(
            image_path="test.jpg",
            prompt="test prompt",
            expected_answer="test answer",
            category=category,
        ),
        quantized_answer="q answer",
        full_precision_answer="fp answer",
        quantized_metrics=q_metrics,
        full_precision_metrics=fp_metrics,
        error=error,
    )


class TestComputeDegradationReport:
    """Degradation report aggregation logic."""

    def test_empty_results(self) -> None:
        report = compute_degradation_report([])
        assert report.quantized_scores == {"exact_match": 0.0, "bleu": 0.0, "rouge_l": 0.0}
        assert report.full_precision_scores == {"exact_match": 0.0, "bleu": 0.0, "rouge_l": 0.0}
        assert report.absolute_diff == {"exact_match": 0.0, "bleu": 0.0, "rouge_l": 0.0}
        assert report.relative_pct_change == {"exact_match": 0.0, "bleu": 0.0, "rouge_l": 0.0}
        assert report.per_category is None

    def test_all_errored_results(self) -> None:
        results = [
            _make_result(
                {"exact_match": 0.0, "bleu": 0.0, "rouge_l": 0.0},
                {"exact_match": 0.0, "bleu": 0.0, "rouge_l": 0.0},
                error="some error",
            ),
            _make_result(
                {"exact_match": 0.0, "bleu": 0.0, "rouge_l": 0.0},
                {"exact_match": 0.0, "bleu": 0.0, "rouge_l": 0.0},
                error="another error",
            ),
        ]
        report = compute_degradation_report(results)
        # All entries have errors, so all scores should be zero
        assert report.quantized_scores == {"exact_match": 0.0, "bleu": 0.0, "rouge_l": 0.0}
        assert report.full_precision_scores == {"exact_match": 0.0, "bleu": 0.0, "rouge_l": 0.0}
        # Errored entries are still stored
        assert len(report.entry_results) == 2

    def test_valid_results_correct_averages(self) -> None:
        results = [
            _make_result(
                {"exact_match": 1.0, "bleu": 0.8, "rouge_l": 0.9},
                {"exact_match": 1.0, "bleu": 0.9, "rouge_l": 0.95},
            ),
            _make_result(
                {"exact_match": 0.0, "bleu": 0.6, "rouge_l": 0.7},
                {"exact_match": 1.0, "bleu": 0.7, "rouge_l": 0.8},
            ),
        ]
        report = compute_degradation_report(results)

        assert report.quantized_scores["exact_match"] == pytest.approx(0.5)
        assert report.quantized_scores["bleu"] == pytest.approx(0.7)
        assert report.quantized_scores["rouge_l"] == pytest.approx(0.8)

        assert report.full_precision_scores["exact_match"] == pytest.approx(1.0)
        assert report.full_precision_scores["bleu"] == pytest.approx(0.8)
        assert report.full_precision_scores["rouge_l"] == pytest.approx(0.875)

        # absolute_diff = quantized - full_precision
        assert report.absolute_diff["exact_match"] == pytest.approx(-0.5)
        assert report.absolute_diff["bleu"] == pytest.approx(-0.1)
        assert report.absolute_diff["rouge_l"] == pytest.approx(-0.075)

    def test_identical_scores_zero_relative_change(self) -> None:
        results = [
            _make_result(
                {"exact_match": 0.5, "bleu": 0.6, "rouge_l": 0.7},
                {"exact_match": 0.5, "bleu": 0.6, "rouge_l": 0.7},
            ),
        ]
        report = compute_degradation_report(results)
        assert report.relative_pct_change["exact_match"] == pytest.approx(0.0)
        assert report.relative_pct_change["bleu"] == pytest.approx(0.0)
        assert report.relative_pct_change["rouge_l"] == pytest.approx(0.0)

    def test_per_category_breakdowns(self) -> None:
        results = [
            _make_result(
                {"exact_match": 1.0, "bleu": 0.9, "rouge_l": 0.95},
                {"exact_match": 1.0, "bleu": 0.95, "rouge_l": 0.98},
                category="VQA",
            ),
            _make_result(
                {"exact_match": 0.0, "bleu": 0.5, "rouge_l": 0.6},
                {"exact_match": 0.0, "bleu": 0.6, "rouge_l": 0.7},
                category="OCR",
            ),
            _make_result(
                {"exact_match": 1.0, "bleu": 0.8, "rouge_l": 0.85},
                {"exact_match": 1.0, "bleu": 0.85, "rouge_l": 0.9},
                category="VQA",
            ),
        ]
        report = compute_degradation_report(results)

        assert report.per_category is not None
        assert "VQA" in report.per_category
        assert "OCR" in report.per_category

        vqa = report.per_category["VQA"]
        assert vqa["quantized_scores"]["exact_match"] == pytest.approx(1.0)
        assert vqa["quantized_scores"]["bleu"] == pytest.approx(0.85)

        ocr = report.per_category["OCR"]
        assert ocr["quantized_scores"]["bleu"] == pytest.approx(0.5)
        assert ocr["full_precision_scores"]["bleu"] == pytest.approx(0.6)


# ---------------------------------------------------------------------------
# 7. Payload builders
# ---------------------------------------------------------------------------


class TestPayloadBuilders:
    """build_quantized_payload and build_full_precision_payload produce valid payloads."""

    def test_quantized_text_only(self) -> None:
        payload = build_quantized_payload("Describe this", None, {"max_tokens": 100})
        assert "messages" in payload
        assert len(payload["messages"]) == 1
        msg = payload["messages"][0]
        assert msg["role"] == "user"
        assert msg["content"] == "Describe this"
        assert payload["max_tokens"] == 100

    def test_quantized_with_image(self) -> None:
        payload = build_quantized_payload("What is this?", "abc123base64", {"max_tokens": 50})
        msg = payload["messages"][0]
        assert isinstance(msg["content"], list)
        assert len(msg["content"]) == 2
        text_block = msg["content"][0]
        image_block = msg["content"][1]
        assert text_block["type"] == "text"
        assert text_block["text"] == "What is this?"
        assert image_block["type"] == "image_url"
        assert "abc123base64" in image_block["image_url"]["url"]

    def test_full_precision_text_only(self) -> None:
        payload = build_full_precision_payload("Explain quantization", None, {"temperature": 0.5})
        assert "messages" in payload
        msg = payload["messages"][0]
        assert msg["role"] == "user"
        assert msg["content"] == "Explain quantization"
        assert payload["temperature"] == 0.5

    def test_full_precision_with_image(self) -> None:
        payload = build_full_precision_payload("Describe", "imgdata", {"max_tokens": 200})
        msg = payload["messages"][0]
        assert isinstance(msg["content"], list)
        assert len(msg["content"]) == 2
        text_block = msg["content"][0]
        image_block = msg["content"][1]
        assert text_block["type"] == "text"
        assert text_block["text"] == "Describe"
        assert image_block["type"] == "image_url"
        assert "imgdata" in image_block["image_url"]["url"]

    def test_both_payloads_preserve_prompt(self) -> None:
        prompt = "What animal is in this image?"
        image = "base64data"
        params = {"max_tokens": 100}
        q = build_quantized_payload(prompt, image, params)
        fp = build_full_precision_payload(prompt, image, params)
        # Both should contain the same prompt text
        q_text = q["messages"][0]["content"][0]["text"]
        fp_text = fp["messages"][0]["content"][0]["text"]
        assert q_text == prompt
        assert fp_text == prompt


# ---------------------------------------------------------------------------
# 8. run_benchmark with mocked endpoints
# ---------------------------------------------------------------------------


class TestRunBenchmarkMocked:
    """run_benchmark with mocked boto3 client and invoke_endpoint."""

    def _mock_invoke_response(self, generated_text: str) -> dict:
        """Build a mock SageMaker invoke_endpoint response."""
        body_content = json.dumps({
            "choices": [{"message": {"content": generated_text}}],
            "usage": {"completion_tokens": 5},
        }).encode("utf-8")
        mock_body = MagicMock()
        mock_body.read.return_value = body_content
        return {"Body": mock_body}

    @patch("benchmark_runner.boto3.client")
    @patch("comparison_utils.encode_image", return_value="fakebase64")
    def test_successful_benchmark_run(
        self, mock_encode: MagicMock, mock_boto_client: MagicMock
    ) -> None:
        mock_runtime = MagicMock()
        mock_boto_client.return_value = mock_runtime
        mock_runtime.invoke_endpoint.return_value = self._mock_invoke_response("cat")

        dataset = [
            BenchmarkEntry("test.jpg", "What animal?", "cat", "VQA"),
        ]
        config = {
            "quantized_endpoint": "q-endpoint",
            "full_precision_endpoint": "fp-endpoint",
            "aws_region": "us-east-2",
        }
        params = {"max_tokens": 100}

        results = run_benchmark(dataset, config, params)

        assert len(results) == 1
        assert results[0].error is None
        assert results[0].quantized_answer == "cat"
        assert results[0].full_precision_answer == "cat"
        assert results[0].quantized_metrics["exact_match"] == 1.0
        assert results[0].full_precision_metrics["exact_match"] == 1.0

    @patch("benchmark_runner.boto3.client")
    @patch("comparison_utils.encode_image", side_effect=FileNotFoundError("not found"))
    def test_missing_image_records_error(
        self, mock_encode: MagicMock, mock_boto_client: MagicMock
    ) -> None:
        mock_runtime = MagicMock()
        mock_boto_client.return_value = mock_runtime

        dataset = [
            BenchmarkEntry("missing.jpg", "What?", "answer", "VQA"),
        ]
        config = {
            "quantized_endpoint": "q-ep",
            "full_precision_endpoint": "fp-ep",
            "aws_region": "us-east-2",
        }

        results = run_benchmark(dataset, config, {})

        assert len(results) == 1
        assert results[0].error is not None
        assert "Image encoding error" in results[0].error

    @patch("benchmark_runner.boto3.client")
    @patch("comparison_utils.encode_image", return_value="fakebase64")
    def test_multiple_entries(
        self, mock_encode: MagicMock, mock_boto_client: MagicMock
    ) -> None:
        mock_runtime = MagicMock()
        mock_boto_client.return_value = mock_runtime
        mock_runtime.invoke_endpoint.return_value = self._mock_invoke_response("answer")

        dataset = [
            BenchmarkEntry("img1.jpg", "Q1", "answer", "VQA"),
            BenchmarkEntry("img2.jpg", "Q2", "answer", "OCR"),
            BenchmarkEntry("img3.jpg", "Q3", "different", None),
        ]
        config = {
            "quantized_endpoint": "q-ep",
            "full_precision_endpoint": "fp-ep",
            "aws_region": "us-east-2",
        }

        results = run_benchmark(dataset, config, {"max_tokens": 50})

        assert len(results) == 3
        # First two should have exact match 1.0 (both return "answer")
        assert results[0].quantized_metrics["exact_match"] == 1.0
        assert results[1].quantized_metrics["exact_match"] == 1.0
        # Third entry: generated "answer" != expected "different"
        assert results[2].quantized_metrics["exact_match"] == 0.0

    @patch("benchmark_runner.boto3.client")
    @patch("comparison_utils.encode_image", return_value="fakebase64")
    def test_endpoint_invocation_called_correctly(
        self, mock_encode: MagicMock, mock_boto_client: MagicMock
    ) -> None:
        mock_runtime = MagicMock()
        mock_boto_client.return_value = mock_runtime
        mock_runtime.invoke_endpoint.return_value = self._mock_invoke_response("ok")

        dataset = [
            BenchmarkEntry("test.jpg", "Prompt", "ok", None),
        ]
        config = {
            "quantized_endpoint": "quant-ep",
            "full_precision_endpoint": "full-ep",
            "aws_region": "us-west-2",
        }

        run_benchmark(dataset, config, {"max_tokens": 10})

        # boto3.client should be called with sagemaker-runtime
        mock_boto_client.assert_called_once_with("sagemaker-runtime", region_name="us-west-2")
        # invoke_endpoint should be called twice (once per endpoint per entry)
        assert mock_runtime.invoke_endpoint.call_count == 2
