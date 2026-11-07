from sqlalchemy import JSON, Column
from sqlmodel import Field, SQLModel


class MissionRow(SQLModel, table=True):
    """What survives a restart (decision Q17): settings, the last phase reached, module status.

    "flying" is never stored: a flight in progress lives in memory (services/state.py), so after
    a restart the mission is back at the phase it had before that flight.
    """

    __tablename__ = "mission"

    id: str = Field(primary_key=True)
    settings: dict = Field(sa_column=Column(JSON, nullable=False))  # MissionSettings
    phase: str = "planned"
    status: dict = Field(sa_column=Column(JSON, nullable=False))  # module id → ModuleStatus
    demo: bool = False
