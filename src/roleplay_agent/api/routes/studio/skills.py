import re

from fastapi import APIRouter

from roleplay_agent.api.dependencies import get_skill_tools
from roleplay_agent.schema.skill import SkillSummary

router = APIRouter(prefix="/api/skills", tags=["skills"])


def _clean_description(text: str) -> str:
    # A tool's description is its docstring - line-wrapped for readability
    # in code, not for display, so collapse it to a single paragraph.
    return re.sub(r"\s+", " ", text).strip()


@router.get("", response_model=list[SkillSummary])
def list_skills():
    # Reads straight off the same registry agent.py binds tools from - a
    # newly-registered skill (see skills/registry.py) shows up here with no
    # further changes, which is the whole point of "scalable easily."
    return [
        SkillSummary(id=skill_id, description=_clean_description(tool.description))
        for skill_id, tool in get_skill_tools().items()
    ]
