from sqlmodel import Field, SQLModel


class AlertRow(SQLModel, table=True):
    """A critical alert raised by an analysis (decision Q17: results in SQLite)."""

    __tablename__ = "alert"

    mission_id: str = Field(primary_key=True)
    id: str = Field(primary_key=True)
    finding_id: str
    level: str = "critical"
    message: str
    raised_at: str
    acknowledged: bool = False
