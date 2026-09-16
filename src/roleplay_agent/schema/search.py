from pydantic import BaseModel, ConfigDict


class SearchResultOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    session_id: str
    title: str
    snippet: str
