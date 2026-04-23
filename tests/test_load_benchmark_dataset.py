"""Unit tests for load_benchmark_dataset() and related helpers."""

from __future__ import annotations

import csv
import json
import os

import pytest

from benchmark_runner import (
    BenchmarkEntry,
    get_default_dataset,
    load_benchmark_dataset,
)


# ---------------------------------------------------------------------------
# get_default_dataset stub
# ---------------------------------------------------------------------------


class TestGetDefaultDataset:
    """Tests for the get_default_dataset function."""

    def test_returns_list(self) -> None:
        result = get_default_dataset()
        assert isinstance(result, list)

    def test_returns_at_least_10_entries(self) -> None:
        """The default dataset should contain at least 10 entries."""
        result = get_default_dataset()
        assert len(result) >= 10

    def test_all_entries_are_benchmark_entry(self) -> None:
        """Every item returned should be a BenchmarkEntry instance."""
        result = get_default_dataset()
        assert all(isinstance(e, BenchmarkEntry) for e in result)

    def test_categories_include_required_types(self) -> None:
        """The default dataset should cover VQA, OCR, and image_description."""
        result = get_default_dataset()
        categories = {e.category for e in result if e.category is not None}
        assert "VQA" in categories
        assert "OCR" in categories
        assert "image_description" in categories


# ---------------------------------------------------------------------------
# Fallback behaviour
# ---------------------------------------------------------------------------


class TestFallbackToDefault:
    """Tests for fallback to get_default_dataset()."""

    def test_none_path_returns_default(self) -> None:
        result = load_benchmark_dataset(None)
        assert isinstance(result, list)
        assert len(result) > 0
        assert result == get_default_dataset()

    def test_nonexistent_file_returns_default(self) -> None:
        result = load_benchmark_dataset("does_not_exist.csv")
        assert isinstance(result, list)
        assert len(result) > 0
        assert result == get_default_dataset()


# ---------------------------------------------------------------------------
# Unsupported format
# ---------------------------------------------------------------------------


def _write_csv(path: str, rows: list[dict[str, str]], fieldnames: list[str]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


class TestUnsupportedFormat:
    """Tests for unsupported file extensions."""

    def test_unsupported_extension_raises(self, tmp_path: object, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(tmp_path)
        p = tmp_path / "data.xyz"  # type: ignore[operator]
        p.write_text("hello")  # type: ignore[union-attr]
        with pytest.raises(ValueError, match=r"Unsupported file format '\.xyz'"):
            load_benchmark_dataset("data.xyz")

    def test_unsupported_extension_txt(self, tmp_path: object, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(tmp_path)
        p = tmp_path / "data.txt"  # type: ignore[operator]
        p.write_text("hello")  # type: ignore[union-attr]
        with pytest.raises(ValueError, match=r"Unsupported file format '\.txt'"):
            load_benchmark_dataset("data.txt")


# ---------------------------------------------------------------------------
# CSV loading
# ---------------------------------------------------------------------------


class TestLoadCSV:
    """Tests for CSV dataset loading."""

    def test_valid_csv_without_category(self, tmp_path: object, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(tmp_path)
        rows = [
            {"image_path": "img.jpg", "prompt": "What?", "expected_answer": "cat"},
        ]
        _write_csv("data.csv", rows, ["image_path", "prompt", "expected_answer"])
        entries = load_benchmark_dataset("data.csv")
        assert len(entries) == 1
        assert entries[0].image_path == "img.jpg"
        assert entries[0].prompt == "What?"
        assert entries[0].expected_answer == "cat"
        assert entries[0].category is None

    def test_valid_csv_with_category(self, tmp_path: object, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(tmp_path)
        rows = [
            {
                "image_path": "img.jpg",
                "prompt": "What?",
                "expected_answer": "cat",
                "category": "VQA",
            },
        ]
        _write_csv(
            "data.csv", rows, ["image_path", "prompt", "expected_answer", "category"]
        )
        entries = load_benchmark_dataset("data.csv")
        assert len(entries) == 1
        assert entries[0].category == "VQA"

    def test_csv_multiple_rows(self, tmp_path: object, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(tmp_path)
        rows = [
            {"image_path": f"img{i}.jpg", "prompt": f"Q{i}", "expected_answer": f"A{i}"}
            for i in range(5)
        ]
        _write_csv("data.csv", rows, ["image_path", "prompt", "expected_answer"])
        entries = load_benchmark_dataset("data.csv")
        assert len(entries) == 5

    def test_csv_missing_columns_raises(self, tmp_path: object, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(tmp_path)
        with open("data.csv", "w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=["image_path"])
            writer.writeheader()
            writer.writerow({"image_path": "img.jpg"})
        with pytest.raises(ValueError, match="Missing required columns"):
            load_benchmark_dataset("data.csv")

    def test_csv_missing_single_column(self, tmp_path: object, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(tmp_path)
        with open("data.csv", "w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=["image_path", "prompt"])
            writer.writeheader()
            writer.writerow({"image_path": "img.jpg", "prompt": "Q"})
        with pytest.raises(ValueError, match="expected_answer"):
            load_benchmark_dataset("data.csv")

    def test_csv_empty_category_becomes_none(self, tmp_path: object, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(tmp_path)
        rows = [
            {
                "image_path": "img.jpg",
                "prompt": "What?",
                "expected_answer": "cat",
                "category": "",
            },
        ]
        _write_csv(
            "data.csv", rows, ["image_path", "prompt", "expected_answer", "category"]
        )
        entries = load_benchmark_dataset("data.csv")
        assert entries[0].category is None


# ---------------------------------------------------------------------------
# JSON loading
# ---------------------------------------------------------------------------


class TestLoadJSON:
    """Tests for JSON dataset loading."""

    def test_valid_json_without_category(self, tmp_path: object, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(tmp_path)
        data = [
            {"image_path": "img.jpg", "prompt": "What?", "expected_answer": "cat"},
        ]
        with open("data.json", "w", encoding="utf-8") as fh:
            json.dump(data, fh)
        entries = load_benchmark_dataset("data.json")
        assert len(entries) == 1
        assert entries[0].image_path == "img.jpg"
        assert entries[0].category is None

    def test_valid_json_with_category(self, tmp_path: object, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(tmp_path)
        data = [
            {
                "image_path": "img.jpg",
                "prompt": "What?",
                "expected_answer": "cat",
                "category": "OCR",
            },
        ]
        with open("data.json", "w", encoding="utf-8") as fh:
            json.dump(data, fh)
        entries = load_benchmark_dataset("data.json")
        assert entries[0].category == "OCR"

    def test_json_multiple_entries(self, tmp_path: object, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(tmp_path)
        data = [
            {"image_path": f"img{i}.jpg", "prompt": f"Q{i}", "expected_answer": f"A{i}"}
            for i in range(3)
        ]
        with open("data.json", "w", encoding="utf-8") as fh:
            json.dump(data, fh)
        entries = load_benchmark_dataset("data.json")
        assert len(entries) == 3

    def test_json_empty_list(self, tmp_path: object, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(tmp_path)
        with open("data.json", "w", encoding="utf-8") as fh:
            json.dump([], fh)
        entries = load_benchmark_dataset("data.json")
        assert entries == []

    def test_json_not_a_list_raises(self, tmp_path: object, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(tmp_path)
        with open("data.json", "w", encoding="utf-8") as fh:
            json.dump({"image_path": "img.jpg"}, fh)
        with pytest.raises(ValueError, match="must be a list"):
            load_benchmark_dataset("data.json")

    def test_json_missing_keys_raises(self, tmp_path: object, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(tmp_path)
        data = [{"image_path": "img.jpg"}]
        with open("data.json", "w", encoding="utf-8") as fh:
            json.dump(data, fh)
        with pytest.raises(ValueError, match="Missing required columns"):
            load_benchmark_dataset("data.json")


# ---------------------------------------------------------------------------
# Security: path validation
# ---------------------------------------------------------------------------


class TestPathSecurity:
    """Tests for file path security validation."""

    def test_absolute_path_outside_cwd_raises(self) -> None:
        with pytest.raises(ValueError, match="resolves outside the working directory"):
            load_benchmark_dataset("/etc/passwd")

    def test_traversal_path_raises(self) -> None:
        with pytest.raises(ValueError, match="resolves outside the working directory"):
            load_benchmark_dataset("../../etc/passwd")


# ---------------------------------------------------------------------------
# Return type validation
# ---------------------------------------------------------------------------


class TestReturnTypes:
    """Tests that returned objects are proper BenchmarkEntry instances."""

    def test_csv_returns_benchmark_entries(self, tmp_path: object, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(tmp_path)
        rows = [
            {"image_path": "img.jpg", "prompt": "Q", "expected_answer": "A"},
        ]
        _write_csv("data.csv", rows, ["image_path", "prompt", "expected_answer"])
        entries = load_benchmark_dataset("data.csv")
        assert all(isinstance(e, BenchmarkEntry) for e in entries)

    def test_json_returns_benchmark_entries(self, tmp_path: object, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(tmp_path)
        data = [{"image_path": "img.jpg", "prompt": "Q", "expected_answer": "A"}]
        with open("data.json", "w", encoding="utf-8") as fh:
            json.dump(data, fh)
        entries = load_benchmark_dataset("data.json")
        assert all(isinstance(e, BenchmarkEntry) for e in entries)
