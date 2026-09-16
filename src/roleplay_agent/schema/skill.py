from pydantic import BaseModel


class SkillSummary(BaseModel):
    id: str
    description: str
