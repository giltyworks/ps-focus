"""Copy the privacy policy and terms into the public website folder, so the published pages match this repository

Run `py tools/sync_site.py` after changing PRIVACY.md or TERMS.md, then commit and push the website folder.
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
_NUMBERED_HEADING = re.compile(r"\d+\. [A-Z][A-Z -]+")


def page(title: str, permalink: str, body: str) -> str:
    return f"---\ntitle: {title}\npermalink: {permalink}\n---\n\n{body.strip()}\n"


def privacy_page(source: str) -> str:
    return page("Privacy Policy", "/privacy/", source)


def terms_page(source: str) -> str:
    """Turn the plain-text terms shown by the installer into Markdown with headings"""
    lines = source.strip().splitlines()
    converted = ["# PS Focus Terms of Use"]
    for line in lines[1:]:
        if _NUMBERED_HEADING.fullmatch(line):
            number, heading = line.split(". ", 1)
            # A backslash keeps Markdown from treating the number as the start of a list
            converted.append(f"\n## {number}\\. {heading.capitalize()}\n")
        elif line.startswith("- ") and not converted[-1].startswith("- "):
            # Markdown needs a blank line between a paragraph and the list that follows it
            converted.extend(["", line])
        else:
            converted.append(line)
    return page("Terms of Use", "/terms/", "\n".join(converted))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("site", nargs="?", type=Path, default=ROOT / "docs", help="website folder")
    args = parser.parse_args()
    if not (args.site / "_config.yml").is_file():
        raise SystemExit(f"{args.site} is not the PS Focus website folder")
    (args.site / "privacy.md").write_text(privacy_page((ROOT / "PRIVACY.md").read_text(encoding="utf-8")), encoding="utf-8")
    (args.site / "terms.md").write_text(terms_page((ROOT / "TERMS.md").read_text(encoding="utf-8")), encoding="utf-8")
    print(f"Privacy policy and terms copied to {args.site}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
