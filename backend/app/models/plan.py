from sqlalchemy import JSON, Column
from sqlmodel import Field, SQLModel


class PlanApprovalRow(SQLModel, table=True):
    """A plan the engineer approved: frozen, and its crew hours are taken for other missions."""

    __tablename__ = "plan_approval"

    mission_id: str = Field(primary_key=True)
    data: dict = Field(sa_column=Column(JSON, nullable=False))  # Plan, as approved
    approved_at: str
