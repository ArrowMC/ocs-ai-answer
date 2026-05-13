from pydantic import BaseModel, Field


class QueryRequest(BaseModel):
    title: str = Field(..., min_length=1, description="Question text")
    options: str | None = Field(None, description="Options separated by \\n")
    type: str | None = Field(None, description="Question type: single/multiple/judgement/completion")


class QueryData(BaseModel):
    question: str
    answer: str


class QueryResponse(BaseModel):
    code: int
    data: QueryData | None = None
    msg: str = "success"


class StatsData(BaseModel):
    total: int
    hit_count: int
    miss_count: int


class StatsResponse(BaseModel):
    code: int = 0
    data: StatsData
    msg: str = "success"
