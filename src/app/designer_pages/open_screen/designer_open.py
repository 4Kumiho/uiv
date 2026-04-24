import os
import sys
from kivy.uix.screenmanager import Screen
from kivy.lang import Builder
from kivy.properties import StringProperty
from kivy.uix.spinner import SpinnerOption
from kivy.factory import Factory


class StyledSpinnerOption(SpinnerOption):
    pass


Builder.load_string("""
<StyledSpinnerOption>:
    background_color: 0.12, 0.12, 0.22, 1
    background_normal: ''
    color: 0.9, 0.9, 1, 1
    font_size: '13sp'
""")

Factory.register('StyledSpinnerOption', cls=StyledSpinnerOption)

Builder.load_file(os.path.join(os.path.dirname(__file__), "designer_open.kv"))


class DesignerOpenScreen(Screen):
    SCREEN_NAME = "designer_open"
    _error_msg = StringProperty("")

    def on_enter(self):
        pass

    def go_back(self):
        self.manager.transition.direction = "right"
        self.manager.current = "main"

    def browse_designer_folder(self):
        from tkinter import filedialog, Tk
        root = Tk()
        root.withdraw()
        folder = filedialog.askdirectory(title="Seleziona cartella designer")
        root.destroy()
        if folder:
            self.ids.designer_folder_input.text = folder

    def start(self):
        designer_folder = self.ids.designer_folder_input.text.strip()

        self._error_msg = ""

        if not designer_folder:
            self._error_msg = "Manca: Cartella designer"
            return

        # Estrai nome sessione dal nome della cartella
        session_name = os.path.basename(designer_folder.rstrip(os.sep))
        db_path = os.path.join(designer_folder, f"{session_name}.db")
        screenshots_folder = os.path.join(designer_folder, "screenshots")

        # Verifica che il DB esista
        if not os.path.isfile(db_path):
            self._error_msg = f"File DB non trovato: {session_name}.db"
            return

        # Verifica che la cartella screenshots esista
        if not os.path.isdir(screenshots_folder):
            self._error_msg = "Cartella 'screenshots' non trovata"
            return

        # Carica il DB per ottenere il session_id
        try:
            db_dir = os.path.abspath(os.path.join(
                os.path.dirname(__file__), '..', '..', 'core', 'database'
            ))
            if db_dir not in sys.path:
                sys.path.insert(0, db_dir)

            from designer_db import DesignerDatabase
            db = DesignerDatabase(db_path)

            # Carica tutte le sessioni del DB
            from sqlalchemy.orm import sessionmaker
            from models import DesignerSession

            with db._Session() as session:
                sessions = session.query(DesignerSession).all()

            if not sessions:
                self._error_msg = "Nessuna sessione trovata nel DB"
                db.close()
                return

            # Prendi la prima sessione (dovrebbe essere solo una)
            session_id = sessions[0].id
            db.close()
        except Exception as e:
            self._error_msg = f"Errore lettura DB: {str(e)}"
            return

        # Passa dati alla summary screen e naviga
        summary = self.manager.get_screen("designer_summary")
        summary.load_session(session_id, db_path)

        self.manager.transition.direction = "left"
        self.manager.current = "designer_summary"
