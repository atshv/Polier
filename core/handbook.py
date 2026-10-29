"""The handbook shipped with the dashboard: guides and the API reference.

The pages are Markdown files in ``server/handbook/`` of the Polier package,
ordered by ``server/handbook/index.json``. They describe Polier itself, not the
project, so they are read from the package and never from the project root.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List

from core.errors import PolierError

HANDBOOK = Path("server") / "handbook"
PAGE_ID = re.compile(r"^[a-z0-9][a-z0-9-]{0,60}$")


def _title_and_summary(text: str, page_id: str) -> Dict[str, str]:
    title, summary, body = page_id, "", []
    for line in text.splitlines():
        if not body and line.startswith("# "):
            title = line[2:].strip()
            continue
        body.append(line)
    blocks = [block.strip() for block in "\n".join(body).split("\n\n") if block.strip()]
    if blocks and not blocks[0].startswith(("#", ">", "|", "```", "-", "1.")):
        summary = " ".join(blocks[0].split())
    return {"title": title, "summary": summary}


def load(package_root) -> Dict[str, Any]:
    """Every space, section and page with its Markdown text."""
    folder = Path(package_root) / HANDBOOK
    try:
        index = json.loads((folder / "index.json").read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise PolierError(f"handbook index unreadable: {exc}")
    spaces: List[Dict[str, Any]] = []
    seen = set()
    for space in index.get("spaces") or []:
        sections = []
        for section in space.get("sections") or []:
            pages = []
            for page_id in section.get("pages") or []:
                if not PAGE_ID.fullmatch(str(page_id)) or page_id in seen:
                    raise PolierError(f"handbook page id {page_id!r} is invalid or repeated")
                seen.add(page_id)
                try:
                    text = (folder / f"{page_id}.md").read_text(encoding="utf-8")
                except OSError as exc:
                    raise PolierError(f"handbook page {page_id} unreadable: {exc}")
                pages.append({"id": page_id, **_title_and_summary(text, page_id), "text": text})
            sections.append({"title": section.get("title") or "", "pages": pages})
        spaces.append({"id": space.get("id"), "title": space.get("title"),
                       "summary": space.get("summary") or "", "sections": sections})
    return {"version": index.get("version", 1), "spaces": spaces,
            "pages": len(seen)}
