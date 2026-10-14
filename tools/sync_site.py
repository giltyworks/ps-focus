"""Copy the privacy policy, the terms and the level table into the public website folder, so the published pages and
the demo match this repository

Run `py tools/sync_site.py` after changing PRIVACY.md, TERMS.md or the level curve, then commit and push the website
folder.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app_config import LEVEL_HOURS  # noqa: E402

_NUMBERED_HEADING = re.compile(r"\d+\. [A-Z][A-Z -]+")
_DEMO_LEVEL_LINE = re.compile(r"^(\s*)const LEVEL_HOURS = \[.*\];$", re.MULTILINE)
DEMO_SCRIPT = Path("assets") / "demo" / "demo.js"


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


def demo_level_hours() -> str:
    """The app's hours for each level as a JavaScript list, rounded to a few seconds, which no level boundary feels"""
    return "[" + ", ".join(f"{hours:.3f}".rstrip("0").rstrip(".") for hours in LEVEL_HOURS) + "]"


def demo_with_levels(source: str) -> str:
    """The demo's script with its level table replaced by the app's, so the website shows the level the app would"""
    replaced, count = _DEMO_LEVEL_LINE.subn(lambda match: f"{match.group(1)}const LEVEL_HOURS = {demo_level_hours()};", source)
    if count != 1:
        raise SystemExit("The demo script has no single LEVEL_HOURS line to update")
    return replaced


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("site", nargs="?", type=Path, default=ROOT / "docs", help="website folder")
    args = parser.parse_args()
    if not (args.site / "_config.yml").is_file():
        raise SystemExit(f"{args.site} is not the PS Focus website folder")
    (args.site / "privacy.md").write_text(privacy_page((ROOT / "PRIVACY.md").read_text(encoding="utf-8")), encoding="utf-8")
    (args.site / "terms.md").write_text(terms_page((ROOT / "TERMS.md").read_text(encoding="utf-8")), encoding="utf-8")
    demo_script = args.site / DEMO_SCRIPT
    demo_script.write_text(demo_with_levels(demo_script.read_text(encoding="utf-8")), encoding="utf-8")
    print(f"Privacy policy, terms and level table copied to {args.site}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
