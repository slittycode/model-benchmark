"""Test benchmark orchestration."""

import pytest
from pathlib import Path

from mrbench.core.benchmark import BenchmarkSuite, BenchmarkPrompt


def test_benchmark_prompt_creation():
    prompt = BenchmarkPrompt(
        id="test",
        text="Hello world",
        tags=["test"],
    )
    assert prompt.id == "test"
    assert prompt.text == "Hello world"


def test_benchmark_suite_from_yaml(tmp_path: Path):
    suite_file = tmp_path / "test.yaml"
    suite_file.write_text("""
name: Test Suite
description: A test suite

prompts:
  - id: prompt1
    text: "What is 2+2?"
    tags: [math]
  - id: prompt2
    text: "Say hello"
""")
    suite = BenchmarkSuite.from_yaml(suite_file)

    assert suite.name == "Test Suite"
    assert len(suite.prompts) == 2
    assert suite.prompts[0].id == "prompt1"
    assert suite.prompts[1].id == "prompt2"


def test_benchmark_suite_default_name(tmp_path: Path):
    suite_file = tmp_path / "mysuite.yaml"
    suite_file.write_text("""
prompts:
  - id: p1
    text: "Test"
""")
    suite = BenchmarkSuite.from_yaml(suite_file)

    assert suite.name == "mysuite"  # Uses filename
