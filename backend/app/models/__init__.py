# Database tables (SQLModel, table=True). Import every model module here
# so init_db() creates its table.
from app.models.alert import AlertRow
from app.models.farm import FarmConfig
from app.models.finding import FindingRow
from app.models.mission import MissionRow
from app.models.plan import PlanApprovalRow

__all__ = ["AlertRow", "FarmConfig", "FindingRow", "MissionRow", "PlanApprovalRow"]
