import os
import sys
import threading
from kivy.uix.screenmanager import Screen
from kivy.lang import Builder
from kivy.properties import StringProperty
from kivy.uix.spinner import SpinnerOption
from kivy.factory import Factory


sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from main_designer import DesignerApp


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

Builder.load_file(os.path.join(os.path.dirname(__file__), "designer_create.kv"))


class DesignerCreateScreen(Screen):
    SCREEN_NAME = "designer_create"
    _error_msg = StringProperty("")

    def on_enter(self):
        self._refresh_monitors()

    def go_back(self):
        self.manager.transition.direction = "right"
        self.manager.current = "main"

    def _refresh_monitors(self):
        try:
            from mss import mss
            with mss() as sct:
                monitors = sct.monitors[1:]
                spinner = self.ids.monitor_spinner
                spinner.values = [
                    f"Monitor {i + 1}  ({m['width']}×{m['height']})"
                    for i, m in enumerate(monitors)
                ]
                if spinner.values:
                    spinner.text = spinner.values[0]
        except Exception:
            pass

    def browse_output_folder(self):
        from tkinter import filedialog, Tk
        root = Tk()
        root.withdraw()
        folder = filedialog.askdirectory(title="Seleziona cartella salvataggio")
        root.destroy()
        if folder:
            self.ids.output_folder_input.text = folder

    def start(self):
        name = self.ids.name_input.text.strip()
        output_folder = self.ids.output_folder_input.text.strip()
        monitor = self.ids.monitor_spinner.text

        self._error_msg = ""

        if not name:
            self._error_msg = "Manca: Nome sessione"
            return
        if not output_folder:
            self._error_msg = "Manca: Cartella salvataggio"
            return
        if not monitor or monitor == "Seleziona monitor":
            self._error_msg = "Manca: Monitor da utilizzare"
            return

        db_path = os.path.join(output_folder, f"{name}.db")

        def run_designer():
            app = DesignerApp(name, db_path)
            app.start()

        thread = threading.Thread(target=run_designer, daemon=True)
        thread.start()

        self.go_back()
