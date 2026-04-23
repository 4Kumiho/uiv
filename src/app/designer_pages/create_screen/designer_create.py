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

        monitor_num = int(monitor.split()[1]) - 1

        # Minimizza la finestra Kivy
        hwnd = ctypes.windll.user32.FindWindowW(None, "UI-Validator")
        if hwnd:
            ctypes.windll.user32.ShowWindow(hwnd, 6)  # 6 = SW_MINIMIZE

        # Launch designer from core/designer/
        designer_main = os.path.abspath(os.path.join(
            os.path.dirname(__file__), '..', '..', 'core', 'designer', 'main_designer.py'
        ))

        # Create output folder structure
        project_folder = os.path.join(output_folder, name)
        os.makedirs(project_folder, exist_ok=True)

        # Log file for debugging
        log_file = os.path.join(project_folder, f"{name}_debug.log")
        with open(log_file, 'w') as f:
            f.write(f"Designer session: {name}\nMonitor: {monitor_num}\n\n")

        # Launch with output to log file
        with open(log_file, 'a') as f:
            proc = subprocess.Popen(
                [sys.executable, designer_main, name, output_folder, str(monitor_num)],
                stdout=f,
                stderr=subprocess.STDOUT
            )

        # Store project folder for background thread
        self._project_folder = project_folder

        # Background thread: wait for subprocess exit
        t = threading.Thread(target=self._wait_for_subprocess, args=(proc,), daemon=True)
        t.start()

    def _wait_for_subprocess(self, proc):
        """Runs on a background thread. Blocks until the designer subprocess exits."""
        proc.wait()

        signal_path = os.path.join(self._project_folder, "session_done.json")
        try:
            with open(signal_path, 'r') as f:
                data = json.load(f)
            session_id = data["session_id"]
            db_path = data["db_path"]
            monitor_info = data.get("monitor_info")
        except Exception:
            # Fallback if signal file missing
            Clock.schedule_once(lambda _: self._restore_and_go_back(), 0)
            return

        # Schedule on Kivy main thread
        Clock.schedule_once(lambda _: self._on_session_done(session_id, db_path, monitor_info), 0)

    def _on_session_done(self, session_id, db_path, monitor_info=None):
        """Called on the Kivy main thread after the subprocess finishes."""
        # Restore (un-minimise) the Kivy window
        hwnd = ctypes.windll.user32.FindWindowW(None, "UI-Validator")
        if hwnd:
            ctypes.windll.user32.ShowWindow(hwnd, 9)  # SW_RESTORE

            # Position window on the correct monitor
            if monitor_info and isinstance(monitor_info, dict):
                left = monitor_info.get("left", 0)
                top = monitor_info.get("top", 0)
                width = monitor_info.get("width", 1920)
                height = monitor_info.get("height", 1080)

                # Center window on the selected monitor
                window_width = 1280
                window_height = 800
                x = left + (width - window_width) // 2
                y = top + (height - window_height) // 2

                # SetWindowPos: hwnd, HWND_TOP=0, x, y, cx, cy, SWP_SHOWWINDOW=0x0040
                ctypes.windll.user32.SetWindowPos(
                    hwnd, 0, x, y, window_width, window_height, 0x0040
                )

            ctypes.windll.user32.SetForegroundWindow(hwnd)

        # Pass data to the summary screen
        summary = self.manager.get_screen("designer_summary")
        summary.load_session(session_id, db_path)

        # Navigate
        self.manager.transition.direction = "left"
        self.manager.current = "designer_summary"

    def _restore_and_go_back(self):
        """Fallback: restore window and go home."""
        hwnd = ctypes.windll.user32.FindWindowW(None, "UI-Validator")
        if hwnd:
            ctypes.windll.user32.ShowWindow(hwnd, 9)
        self.go_back()
