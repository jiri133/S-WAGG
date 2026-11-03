from typing import Annotated

from fastapi import Depends
from sqlmodel import Session

from app.core.db import get_session

# Use in routes: def handler(session: SessionDep): ...
SessionDep = Annotated[Session, Depends(get_session)]
