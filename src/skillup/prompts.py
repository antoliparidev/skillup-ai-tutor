"""Prompt as code: i prompt sono file .md nella cartella prompts/, versionati con git."""

from functools import cache

from skillup.config import settings


@cache
def prompt(nome: str) -> str:
    return (settings.prompts_dir / f"{nome}.md").read_text(encoding="utf-8")