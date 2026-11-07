from collections.abc import Generator

from sqlmodel import Session, SQLModel, create_engine

from app.core.config import settings

database_url = settings.database_url.get_secret_value()
connect_args = {"check_same_thread": False} if database_url.startswith("sqlite") else {}
engine = create_engine(database_url, connect_args=connect_args)


def init_db() -> None:
    # Import models so SQLModel registers their tables before create_all.
    import app.models  # noqa: F401

    SQLModel.metadata.create_all(engine)


def get_session() -> Generator[Session, None, None]:
    with Session(engine) as session:
        yield session
