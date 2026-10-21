"""Shared pytest fixtures for the whole test suite."""

import os

import pytest

__all__: tuple[str, ...] = ()


# noinspection GrazieStyle
@pytest.fixture(autouse=True)
def isolated_environ(monkeypatch: pytest.MonkeyPatch) -> None:
    """
    Replaces os.environ with an empty dict for the duration of each test.

    environs.Env checks the real os.environ before falling back to a test's own throwaway
    .env file. Without this, a variable left over from one test (via monkeypatch.setenv, or a
    real env var set on the host) could shadow another test's .env value for the same key.

    :param monkeypatch: pytest's monkeypatch fixture, which restores the original os.environ
        object automatically once the test finishes.
    :return: None
    """
    monkeypatch.setattr(target=os, name="environ", value={})
