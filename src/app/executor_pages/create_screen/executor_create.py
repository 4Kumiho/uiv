import os
import subprocess
import sys
import ctypes
import threading
import json
from kivy.uix.screenmanager import Screen
from kivy.lang import Builder
from kivy.properties import StringProperty
from kivy.uix.spinner import SpinnerOption
from kivy.factory import Factory
from kivy.clock import Clock


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

Builder.load_file(os.path.join(os.path.dirname(__file__), "executor_create.kv"))


class ExecutorCreateScreen(Screen):
    SCREEN_NAME = "executor_create"
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

    def browse_designer_folder(self):
        from tkinter import filedialog, Tk
        root = Tk()
        root.withdraw()
        folder = filedialog.askdirectory(title="Seleziona cartella designer")
        root.destroy()
        if folder:
            self.ids.designer_folder_input.text = folder

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
        designer_folder = self.ids.designer_folder_input.text.strip()
        output_folder = self.ids.output_folder_input.text.strip()
        monitor = self.ids.monitor_spinner.text

        self._error_msg = ""

        if not name:
            self._error_msg = "Manca: Nome sessione"
            return
        if not designer_folder:
            self._error_msg = "Manca: Cartella designer"
            return
        if not output_folder:
            self._error_msg = "Manca: Cartella salvataggio"
            return
        if not monitor or monitor == "Seleziona monitor":
            self._error_msg = "Manca: Monitor da eseguire"
            return

        # Find designer DB in designer_folder
        designer_db_path = None
        try:
            for f in os.listdir(designer_folder):
                if f.endswith('.db'):
                    designer_db_path = os.path.join(designer_folder, f)
                    break
        except Exception:
            pass

        if not designer_db_path:
            self._error_msg = "Nessun database designer trovato nella cartella"
            return

        monitor_num = int(monitor.split()[1]) - 1

        # Minimize Kivy window
        try:
            hwnd = ctypes.windll.user32.FindWindowW(None, "UI-Validator")
            if hwnd:
                ctypes.windll.user32.ShowWindow(hwnd, 6)  # 6 = SW_MINIMIZE
        except Exception:
            pass

        # Launch executor subprocess
        executor_main = os.path.abspath(os.path.join(
            os.path.dirname(__file__), '..', '..', 'core', 'executor', 'main_executor.py'
        ))

        proc = subprocess.Popen(
            [sys.executable, executor_main, name, designer_db_path, output_folder, str(monitor_num)]
        )

        # Store paths for background thread
        self._output_folder = output_folder
        self._session_name = name

        # Background thread: wait for subprocess and signal file
        t = threading.Thread(target=self._wait_for_subprocess, args=(proc,), daemon=True)
        t.start()

    def _wait_for_subprocess(self, proc):
        """Wait for executor subprocess and read signal file."""
        proc.wait()

        signal_path = os.path.join(self._output_folder, self._session_name, "execution_done.json")
        try:
            with open(signal_path, 'r') as f:
                data = json.load(f)
            execution_id = data.get("execution_id")
            db_path = data.get("db_path")
            status = data.get("status")
        except Exception:
            Clock.schedule_once(lambda _: self._restore_and_go_back(), 0)
            return

        # Schedule on Kivy main thread
        Clock.schedule_once(lambda _: self._on_execution_done(execution_id, db_path), 0)

    def _on_execution_done(self, execution_id, db_path):
        """Called on Kivy main thread after executor finishes."""
        # Restore window
        try:
            hwnd = ctypes.windll.user32.FindWindowW(None, "UI-Validator")
            if hwnd:
                ctypes.windll.user32.ShowWindow(hwnd, 1)  # 1 = SW_SHOW
                ctypes.windll.user32.SetForegroundWindow(hwnd)
        except Exception:
            pass

        # Pass data to summary screen
        summary = self.manager.get_screen("executor_summary")
        summary.load_session(execution_id, db_path)

        # Navigate
        self.manager.transition.direction = "left"
        self.manager.current = "executor_summary"

    def _restore_and_go_back(self):
        """Fallback: restore window and go home."""
        try:
            hwnd = ctypes.windll.user32.FindWindowW(None, "UI-Validator")
            if hwnd:
                ctypes.windll.user32.ShowWindow(hwnd, 1)
                ctypes.windll.user32.SetForegroundWindow(hwnd)
        except Exception:
            pass

        self.manager.transition.direction = "right"
        self.manager.current = "main"
