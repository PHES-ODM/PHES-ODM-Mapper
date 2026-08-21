"""Check every relative link in the project's Markdown files.

mkdocs.yml sets `validation.links.not_found: ignore`, because these documents
are also read on GitHub and link to source files under `odm_map/` and to the
root-level README and CONTRIBUTING — targets that live outside `docs_dir` and
that mkdocs cannot resolve. mkdocs cannot tell those apart from genuinely
broken links, so it validates neither.

This script does, by resolving every link against the filesystem instead of
against mkdocs' page list. Links beginning with `/` are resolved against the
repository root, which is how these documents use them (`/odm_map/pipeline_cli.py`
means the file of that name in the repository). It also checks that `#anchor`
fragments match a heading in the target document.

Run from the repository root:

    python .github/scripts/check_doc_links.py
"""

from __future__ import annotations

import re
import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# Directories that hold no authored documentation.
SKIP_DIRS = {".git", ".env", "site", "node_modules", ".pytest_cache", ".ruff_cache"}

# ](target) — bare, without a title. Titles are not used in these documents.
LINK = re.compile(r"\]\(([^)\s]+)\)")
HEADING = re.compile(r"^#{1,6}\s+(.*)$", re.MULTILINE)
FENCE = re.compile(r"^(?: {0,3})(```|~~~).*?^(?: {0,3})\1", re.MULTILINE | re.DOTALL)


def anchor_slug(heading: str) -> str:
    """Reproduce the heading -> anchor slug that mkdocs and GitHub both use.

    This is Python-Markdown's `toc` slugify: strip accents, drop everything
    that is not a word character, whitespace, or hyphen, then collapse runs of
    whitespace and hyphens into a single hyphen. Underscores survive, which is
    why `## The `_extra_` columns` anchors as `the-_extra_-columns`.
    """
    text = unicodedata.normalize("NFKD", heading).encode("ascii", "ignore").decode()
    text = re.sub(r"[^\w\s-]", "", text).strip().lower()
    return re.sub(r"[-\s]+", "-", text)


def markdown_files() -> list[Path]:
    return sorted(
        p for p in ROOT.rglob("*.md") if not SKIP_DIRS & set(p.relative_to(ROOT).parts)
    )


def main() -> int:
    files = markdown_files()
    anchors = {
        p: {anchor_slug(h) for h in HEADING.findall(FENCE.sub("", p.read_text()))}
        for p in files
    }

    problems: list[str] = []
    for path in files:
        body = FENCE.sub("", path.read_text())
        for target in LINK.findall(body):
            if target.startswith(("http://", "https://", "mailto:", "<")):
                continue

            file_part, _, anchor = target.partition("#")
            if not file_part:
                dest = path  # same-page anchor
            else:
                # A leading "/" means "from the repository root", not "from the
                # filesystem root".
                base = ROOT if file_part.startswith("/") else path.parent
                dest = (base / file_part.lstrip("/")).resolve()
                if not dest.exists():
                    problems.append(
                        f"{path.relative_to(ROOT)} -> {target} (no such file)"
                    )
                    continue

            if (
                anchor
                and dest.suffix == ".md"
                and anchor not in anchors.get(dest, set())
            ):
                problems.append(
                    f"{path.relative_to(ROOT)} -> {target} (no such heading)"
                )

    for problem in problems:
        print(f"BROKEN LINK  {problem}")

    print(f"\nChecked {len(files)} Markdown files: {len(problems)} broken link(s).")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
