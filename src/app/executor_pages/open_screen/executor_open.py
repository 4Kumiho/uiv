import os
from kivy.uix.screenmanager import Screen
from kivy.lang import Builder
from kivy.properties import StringProperty


Builder.load_file(os.path.join(os.path.dirname(__file__), "executor_open.kv"))


class ExecutorOpenScreen(Screen):
    SCREEN_NAME = "executor_open"
    _error_msg = StringProperty("")

    def go_back(self):
        self.manager.transition.direction = "right"
        self.manager.current = "main"

    def browse_execution_folder(self):
        from tkinter import filedialog, Tk
        root = Tk()
        root.withdraw()
        folder = filedialog.askdirectory(title="Seleziona cartella esecuzione")
        root.destroy()
        if folder:
            self.ids.execution_folder_input.text = folder

    def start(self):
        execution_folder = self.ids.execution_folder_input.text.strip()

        self._error_msg = ""

        if not execution_folder:
            self._error_msg = "Manca: Cartella esecuzione"
            return

        # Find execution DB file
        db_path = None
        try:
            for f in os.listdir(execution_folder):
                if f.endswith('.db'):
                    db_path = os.path.join(execution_folder, f)
                    break
        except Exception:
            pass

        if not db_path:
            self._error_msg = "Nessun database esecuzione trovato nella cartella"
            return

        # Load executor DB and get first session
        try:
            from src.app.core.database.executor_db import ExecutorDatabase
            from src.app.core.database.models import ExecutionSession

            db = ExecutorDatabase(db_path)

            # Get all sessions
            with db._Session() as session:
                sessions = session.query(ExecutionSession).all()

            if not sessions:
                self._error_msg = "Nessuna sessione trovata nel database"
                db.close()
                return

            # Take first session
            execution_id = sessions[0].id
            db.close()
        except Exception as e:
            self._error_msg = f"Errore lettura DB: {str(e)}"
            return

        # Load summary screen and navigate
        summary = self.manager.get_screen("executor_summary")
        summary.load_session(execution_id, db_path)

        self.manager.transition.direction = "left"
        self.manager.current = "executor_summary"
