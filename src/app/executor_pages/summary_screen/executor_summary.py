"""Executor Summary Screen - displays execution results with video and step list."""

import os
import sys
import json
from kivy.uix.screenmanager import Screen
from kivy.lang import Builder
from kivy.properties import StringProperty, ListProperty
from kivy.uix.button import Button

# Add project root to path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'core', 'database'))

Builder.load_file(os.path.join(os.path.dirname(__file__), "executor_summary.kv"))


class ExecutorSummaryScreen(Screen):
    SCREEN_NAME = "executor_summary"
    title = StringProperty("Execution Summary")
    session_status = StringProperty("UNKNOWN")
    status_color = ListProperty([1, 1, 1, 1])

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.execution_id = None
        self.db_path = None
        self.video_path = None
        self.executor_db = None
        self.session = None
        self.steps = None
        self._current_step = None

    def load_session(self, execution_id: int, db_path: str, video_path: str = None):
        """Load execution session and populate UI."""
        try:
            self.execution_id = execution_id
            self.db_path = db_path
            self.video_path = video_path

            # Load database
            from executor_db import ExecutorDatabase
            self.executor_db = ExecutorDatabase(db_path)

            # Get session and steps
            self.session = self.executor_db.get_session(execution_id)
            if not self.session:
                self.title = "Session not found"
                return

            self.steps = self.executor_db.get_steps(execution_id)

            # Update title and status
            self.title = f"Execution: {self.session.name}"
            self.session_status = self.session.status or "UNKNOWN"

            # Set status color
            if self.session_status == 'COMPLETED':
                self.status_color = [0.2, 0.8, 0.3, 1]  # Green
            elif self.session_status == 'FAILED':
                self.status_color = [0.9, 0.2, 0.2, 1]  # Red
            elif self.session_status == 'STOPPED':
                self.status_color = [0.9, 0.8, 0.1, 1]  # Yellow
            else:
                self.status_color = [0.7, 0.7, 0.7, 1]  # Gray

            # Update video path if not provided
            if not self.video_path and self.session.video_path:
                self.video_path = self.session.video_path

            # Populate step list
            self._populate_steps()

            # Load video
            if self.video_path and os.path.exists(self.video_path):
                self.ids.video_player.source = self.video_path

        except Exception as e:
            self.title = f"Error: {str(e)}"
            import traceback
            traceback.print_exc()

    def _populate_steps(self):
        """Populate step list with colored buttons."""
        if not self.steps:
            return

        steps_container = self.ids.steps_container
        steps_container.clear_widgets()

        for i, step in enumerate(self.steps, 1):
            # Determine color based on status
            if step.status == 'PASS':
                color = [0.2, 0.8, 0.3, 1]  # Green
                symbol = "✓"
            elif step.status == 'FAIL':
                color = [0.9, 0.2, 0.2, 1]  # Red
                symbol = "✗"
            elif step.status == 'STOPPED':
                color = [0.9, 0.8, 0.1, 1]  # Yellow
                symbol = "—"
            else:
                color = [0.5, 0.5, 0.5, 1]  # Gray
                symbol = "?"

            # Create step button
            btn = Button(
                text=f"{symbol} {i}. {step.action_type}",
                size_hint_y=None,
                height=40,
                background_color=color,
                color=[0, 0, 0, 1]
            )
            btn.step = step
            btn.bind(on_press=self._on_step_selected)
            steps_container.add_widget(btn)

    def _on_step_selected(self, btn):
        """Handle step selection."""
        step = btn.step
        self._current_step = step

        # Jump video to step timestamp
        if step.video_timestamp is not None:
            self.ids.video_player.position = step.video_timestamp

        # Update info panel
        self._update_step_info(step)

    def _update_step_info(self, step):
        """Update step information panel."""
        info_text = f"Step {step.step_number}: {step.action_type}\n"
        info_text += f"Status: {step.status or 'UNKNOWN'}\n"
        if step.match_score is not None:
            info_text += f"Match Score: {step.match_score:.2f}\n"
        if step.match_stage is not None:
            info_text += f"Match Stage: {step.match_stage}\n"
        if step.matched_bbox:
            try:
                bbox = json.loads(step.matched_bbox)
                info_text += f"Found at: x={bbox['x']}, y={bbox['y']}\n"
            except:
                pass
        if step.error_msg:
            info_text += f"Error: {step.error_msg}\n"

        self.ids.step_info.text = info_text

    def go_back(self):
        """Navigate back to main screen."""
        if self.executor_db:
            try:
                self.executor_db.close()
            except:
                pass

        self.manager.transition.direction = "right"
        self.manager.current = "main"
