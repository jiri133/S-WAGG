from sqlalchemy import JSON, Column, LargeBinary
from sqlmodel import Field, SQLModel


class FindingRow(SQLModel, table=True):
    """A finding of a mission's analysis, with the crop the model saw (decision Q17)."""

    __tablename__ = "finding"

    pk: int | None = Field(default=None, primary_key=True)  # later analyses get larger pks
    mission_id: str = Field(index=True)
    id: str = Field(index=True)
    data: dict = Field(sa_column=Column(JSON, nullable=False))  # Finding, review included
    crop: bytes = Field(sa_column=Column(LargeBinary, nullable=False))  # PNG, 24×40 gray
    created_at: str
