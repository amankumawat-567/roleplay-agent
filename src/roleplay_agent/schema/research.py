from pydantic import BaseModel


class ResearchResponse(BaseModel):
    research_notes: str
