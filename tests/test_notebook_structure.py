"""Unit tests for notebook structure validation.

Parses comparison_notebook.ipynb as JSON and validates that required
sections, cells, and code patterns exist. Also checks that all public
functions in comparison_utils and benchmark_runner have type annotations
and docstrings.
"""

from __future__ import annotations

import inspect
import json
import types
from pathlib import Path

import pytest

import benchmark_runner
import comparison_utils


# ---------------------------------------------------------------------------
# Fixture: load notebook JSON once
# ---------------------------------------------------------------------------

NOTEBOOK_PATH = Path(__file__).resolve().parent.parent / "comparison_notebook.ipynb"


@pytest.fixture(scope="module")
def notebook() -> dict:
    """Load comparison_notebook.ipynb as parsed JSON (shared across all tests)."""
    with open(NOTEBOOK_PATH, encoding="utf-8") as fh:
        return json.load(fh)


def _cell_source(cell: dict) -> str:
    """Join a cell's source lines into a single string."""
    return "".join(cell.get("source", []))


# ---------------------------------------------------------------------------
# 1. Benchmark Evaluation section exists
# ---------------------------------------------------------------------------


class TestBenchmarkEvaluationSection:
    """The notebook must contain a markdown cell with 'Benchmark Evaluation'."""

    def test_benchmark_evaluation_markdown_exists(self, notebook: dict) -> None:
        markdown_cells = [
            _cell_source(c) for c in notebook["cells"] if c["cell_type"] == "markdown"
        ]
        assert any(
            "Benchmark Evaluation" in src for src in markdown_cells
        ), "No markdown cell containing 'Benchmark Evaluation' found in the notebook"


# ---------------------------------------------------------------------------
# 2. Benchmark configuration cell exists
# ---------------------------------------------------------------------------


class TestBenchmarkConfigurationCell:
    """The notebook must contain a code cell with BENCHMARK_DATASET_PATH."""

    def test_benchmark_dataset_path_code_cell(self, notebook: dict) -> None:
        code_cells = [
            _cell_source(c) for c in notebook["cells"] if c["cell_type"] == "code"
        ]
        assert any(
            "BENCHMARK_DATASET_PATH" in src for src in code_cells
        ), "No code cell containing 'BENCHMARK_DATASET_PATH' found in the notebook"


# ---------------------------------------------------------------------------
# 3. Cost warning exists
# ---------------------------------------------------------------------------


class TestCostWarning:
    """The notebook must contain a markdown cell with 'Cost Warning'."""

    def test_cost_warning_markdown_exists(self, notebook: dict) -> None:
        markdown_cells = [
            _cell_source(c) for c in notebook["cells"] if c["cell_type"] == "markdown"
        ]
        assert any(
            "Cost Warning" in src for src in markdown_cells
        ), "No markdown cell containing 'Cost Warning' found in the notebook"


# ---------------------------------------------------------------------------
# 4. At least 5 image prompts
# ---------------------------------------------------------------------------


class TestImagePromptCount:
    """The notebook must have at least 5 code cells referencing test_images/."""

    def test_at_least_5_image_prompts(self, notebook: dict) -> None:
        image_cells = [
            c
            for c in notebook["cells"]
            if c["cell_type"] == "code" and "test_images/" in _cell_source(c)
        ]
        assert len(image_cells) >= 5, (
            f"Expected at least 5 code cells referencing 'test_images/', found {len(image_cells)}"
        )


# ---------------------------------------------------------------------------
# 5. At least 1 text-only prompt
# ---------------------------------------------------------------------------


class TestTextOnlyPrompt:
    """The notebook must have a code cell calling run_comparison with None image."""

    def test_text_only_prompt_exists(self, notebook: dict) -> None:
        code_cells = [
            _cell_source(c) for c in notebook["cells"] if c["cell_type"] == "code"
        ]
        assert any(
            "run_comparison" in src and "None" in src for src in code_cells
        ), "No code cell calling run_comparison with None as image source found"


# ---------------------------------------------------------------------------
# 6. Cleanup cell exists
# ---------------------------------------------------------------------------


class TestCleanupCell:
    """The notebook must have a code cell containing delete_endpoint."""

    def test_cleanup_cell_exists(self, notebook: dict) -> None:
        code_cells = [
            _cell_source(c) for c in notebook["cells"] if c["cell_type"] == "code"
        ]
        assert any(
            "delete_endpoint" in src for src in code_cells
        ), "No code cell containing 'delete_endpoint' found in the notebook"


# ---------------------------------------------------------------------------
# Helpers for introspection tests (7 & 8)
# ---------------------------------------------------------------------------


def _get_public_functions(module: types.ModuleType) -> list[tuple[str, types.FunctionType]]:
    """Return all public (non-underscore) functions defined in *module*."""
    return [
        (name, obj)
        for name, obj in inspect.getmembers(module, inspect.isfunction)
        if not name.startswith("_") and obj.__module__ == module.__name__
    ]


# ---------------------------------------------------------------------------
# 7. Type hints on public functions
# ---------------------------------------------------------------------------


class TestTypeHints:
    """All public functions in comparison_utils and benchmark_runner must have
    type annotations on their parameters and return types."""

    @pytest.mark.parametrize(
        "module",
        [comparison_utils, benchmark_runner],
        ids=["comparison_utils", "benchmark_runner"],
    )
    def test_all_public_functions_have_type_hints(
        self, module: types.ModuleType
    ) -> None:
        functions = _get_public_functions(module)
        assert len(functions) > 0, f"No public functions found in {module.__name__}"

        missing: list[str] = []
        for name, func in functions:
            hints = getattr(func, "__annotations__", {})
            sig = inspect.signature(func)
            for param_name, param in sig.parameters.items():
                if param_name == "self":
                    continue
                if param_name not in hints:
                    missing.append(f"{module.__name__}.{name}: parameter '{param_name}'")
            if "return" not in hints:
                missing.append(f"{module.__name__}.{name}: return type")

        assert not missing, (
            "Missing type annotations:\n" + "\n".join(f"  - {m}" for m in missing)
        )


# ---------------------------------------------------------------------------
# 8. Docstrings on public functions
# ---------------------------------------------------------------------------


class TestDocstrings:
    """All public functions in comparison_utils and benchmark_runner must have
    non-empty docstrings."""

    @pytest.mark.parametrize(
        "module",
        [comparison_utils, benchmark_runner],
        ids=["comparison_utils", "benchmark_runner"],
    )
    def test_all_public_functions_have_docstrings(
        self, module: types.ModuleType
    ) -> None:
        functions = _get_public_functions(module)
        assert len(functions) > 0, f"No public functions found in {module.__name__}"

        missing: list[str] = []
        for name, func in functions:
            doc = inspect.getdoc(func)
            if not doc or not doc.strip():
                missing.append(f"{module.__name__}.{name}")

        assert not missing, (
            "Missing or empty docstrings:\n" + "\n".join(f"  - {m}" for m in missing)
        )
