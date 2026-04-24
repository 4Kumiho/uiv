"""Database handler per Designer."""

import os
import sys

# Add project root to path for absolute imports
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from src.app.core.database.models import Base, DesignerSession, DesignerStep


class DesignerDatabase:
    def __init__(self, db_path: str):
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self._engine = create_engine(f"sqlite:///{db_path}", echo=False)
        Base.metadata.create_all(self._engine)
        self._Session = sessionmaker(bind=self._engine)

    def create_session(self, name: str) -> DesignerSession:
        with self._Session() as session:
            new_session = DesignerSession(name=name)
            session.add(new_session)
            session.commit()
            session.refresh(new_session)
            return new_session

    def add_step(self, session_id: int, step: DesignerStep):
        with self._Session() as session:
            step.session_id = session_id
            session.add(step)
            session.commit()
            session.refresh(step)
            return step

    def update_step(self, session_id: int, step: DesignerStep):
        """Update an existing step in the database."""
        with self._Session() as session:
            step.session_id = session_id
            session.merge(step)
            session.commit()
            return step

    def get_session(self, session_id: int) -> DesignerSession:
        with self._Session() as session:
            s = session.query(DesignerSession).filter_by(id=session_id).one_or_none()
            if s:
                session.expunge(s)
            return s

    def get_steps(self, session_id: int) -> list:
        with self._Session() as session:
            steps = session.query(DesignerStep).filter_by(session_id=session_id).order_by(DesignerStep.step_number).all()
            for step in steps:
                session.expunge(step)
            return steps

    def close(self):
        self._engine.dispose()
