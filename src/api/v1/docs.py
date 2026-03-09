"""In-app help content API — serves markdown help files from docs/help/."""

import re
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()

_HELP_DIR = Path(__file__).resolve().parents[3] / "docs" / "help"
_SECTION_RE = re.compile(r"^[a-z0-9_-]+$")


class HelpSectionResponse(BaseModel):
    section: str
    title: str
    content: str


class HelpSectionsListResponse(BaseModel):
    sections: list[str]
    count: int


def _extract_title(content: str) -> str:
    """Extract the first H1 heading from markdown content."""
    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith("# ") and not stripped.startswith("## "):
            return stripped[2:].strip()
    return ""


@router.get("/docs/sections", response_model=HelpSectionsListResponse)
async def list_help_sections() -> HelpSectionsListResponse:
    """List all available help sections."""
    if not _HELP_DIR.is_dir():
        return HelpSectionsListResponse(sections=[], count=0)
    sections = sorted(
        p.stem for p in _HELP_DIR.glob("*.md") if p.is_file()
    )
    return HelpSectionsListResponse(sections=sections, count=len(sections))


@router.get("/docs/{section}", response_model=HelpSectionResponse)
async def get_help_section(section: str) -> HelpSectionResponse:
    """Get markdown help content for a specific section."""
    if not _SECTION_RE.match(section):
        raise HTTPException(status_code=400, detail="Invalid section name")

    file_path = (_HELP_DIR / f"{section}.md").resolve()

    # Path traversal guard
    if not str(file_path).startswith(str(_HELP_DIR.resolve())):
        raise HTTPException(status_code=400, detail="Invalid section name")

    if not file_path.is_file():
        raise HTTPException(status_code=404, detail=f"Help section '{section}' not found")

    content = file_path.read_text(encoding="utf-8")
    title = _extract_title(content)

    return HelpSectionResponse(section=section, title=title, content=content)
