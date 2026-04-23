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
