"""Database handler per Executor."""

import os
import sys

# Add project root to path for absolute imports
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from src.app.core.database.models import Base, ExecutionSession, ExecutionStep


class ExecutorDatabase:
    def __init__(self, db_path: str):
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self._engine = create_engine(f"sqlite:///{db_path}", echo=False)
        Base.metadata.create_all(self._engine)
        self._Session = sessionmaker(bind=self._engine)

    def create_session(self, name: str, designer_db_path: str = None, designer_session_id: int = None) -> ExecutionSession:
        with self._Session() as session:
            new_session = ExecutionSession(
                name=name,
                designer_db_path=designer_db_path,
                designer_session_id=designer_session_id
            )
            session.add(new_session)
            session.commit()
            session.refresh(new_session)
            return new_session

    def add_step(self, session_id: int, step: ExecutionStep) -> ExecutionStep:
        with self._Session() as session:
            step.session_id = session_id
            session.add(step)
            session.commit()
            session.refresh(step)
            return step

    def update_step(self, session_id: int, step: ExecutionStep) -> ExecutionStep:
        """Update an existing step in the database."""
        with self._Session() as session:
            step.session_id = session_id
            session.merge(step)
            session.commit()
            return step

    def update_session_status(self, session_id: int, status: str, video_path: str = None):
        """Update execution session status and video path."""
        with self._Session() as session:
            s = session.query(ExecutionSession).filter_by(id=session_id).one_or_none()
            if s:
                s.status = status
                if video_path:
                    s.video_path = video_path
                session.commit()

    def get_session(self, session_id: int) -> ExecutionSession:
        with self._Session() as session:
            s = session.query(ExecutionSession).filter_by(id=session_id).one_or_none()
            if s:
                session.expunge(s)
            return s

    def get_steps(self, session_id: int) -> list:
        with self._Session() as session:
            steps = session.query(ExecutionStep).filter_by(session_id=session_id).order_by(ExecutionStep.step_number).all()
            for step in steps:
                session.expunge(step)
            return steps

    def get_all_sessions(self) -> list:
        """Get all execution sessions."""
        with self._Session() as session:
            sessions = session.query(ExecutionSession).all()
            for s in sessions:
                session.expunge(s)
            return sessions

    def close(self):
        self._engine.dispose()
