from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import List

import setuptools


def _run(*cmd):
    wd = os.path.dirname(os.path.abspath(__file__))
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, cwd=wd)
    return p.stdout.read().decode().rstrip()


def _pep440_version_from_git() -> str:
    """Return a PEP440 compliant version derived from the git commit."""

    commit = _run("git", "rev-parse", "--short=7", "HEAD")
    if not commit:
        # Fallback for situations where git metadata is unavailable (e.g. sdist)
        return "0.0"

    # "0.0+g<commit>" follows the PEP 440 local version identifier format while
    # preserving the short commit for debugging purposes.
    return f"0.0+g{commit}"


def setup(install_requires: List[str], name: str = "dex_proxy"):
    version = _pep440_version_from_git()

    if name != "py_dex_common":
        py_dex_common_path = Path("../py_dex_common").resolve()
        install_requires.append(
            f"py_dex_common @ {py_dex_common_path.as_uri()}"
        )

    setuptools.setup(
        name=name,
        version=version,
        packages=setuptools.find_packages(),
        install_requires=install_requires,
    )
