"""SQLAlchemy models per Designer."""

from datetime import datetime
from sqlalchemy import Column, Integer, String, LargeBinary, DateTime, Boolean, ForeignKey
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class DesignerSession(Base):
    __tablename__ = "designer_session"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    steps = relationship("DesignerStep", back_populates="session",
                         order_by="DesignerStep.step_number",
                         cascade="all, delete-orphan")


class DesignerStep(Base):
    __tablename__ = "designer_step"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(Integer, ForeignKey("designer_session.id"), nullable=False)
    step_number = Column(Integer, nullable=False)
    action_type = Column(String, nullable=False)  # CLICK, INPUT, DRAG, SCROLL, etc.

    screenshot = Column(LargeBinary, nullable=True)  # PNG image bytes
    screenshot_path = Column(String, nullable=True)  # Path to PNG file
    coordinates = Column(String, nullable=True)  # JSON: {"x": 100, "y": 200}

    # Element matching
    bbox = Column(String, nullable=True)  # JSON: {"x": 10, "y": 20, "w": 100, "h": 50}
    ocr_text = Column(String, nullable=True)
    features = Column(LargeBinary, nullable=True)  # ResNet18 512-dim

    # Action-specific
    input_text = Column(String, nullable=True)
    press_enter_after = Column(Boolean, default=False)

    # DRAG: 2 captures separate
    drag_end_coordinates = Column(String, nullable=True)
    drag_end_bbox = Column(String, nullable=True)
    drag_end_ocr_text = Column(String, nullable=True)
    drag_end_features = Column(LargeBinary, nullable=True)

    # Bbox crop screenshot and relative coordinates (for position-independent matching)
    bbox_screenshot = Column(LargeBinary, nullable=True)  # PNG bytes of bbox region
    coordinates_rel = Column(String, nullable=True)  # JSON: {"x": rel_x, "y": rel_y}
    drag_end_bbox_screenshot = Column(LargeBinary, nullable=True)  # PNG bytes of drag_end bbox
    drag_end_coordinates_rel = Column(String, nullable=True)  # JSON: {"x": rel_x, "y": rel_y}

    # SCROLL
    scroll_dx = Column(Integer, nullable=True)
    scroll_dy = Column(Integer, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)

    session = relationship("DesignerSession", back_populates="steps")
