# Database tables (SQLModel, table=True). Import every model module here
# so init_db() creates its table.
from app.models.mission import MissionRow

__all__ = ["MissionRow"]
