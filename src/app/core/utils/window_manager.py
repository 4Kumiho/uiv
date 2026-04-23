"""Window management - minimizza/massimizza finestra principale."""

import tkinter as tk
import os
import platform


class WindowManager:
    @staticmethod
    def minimize_current_window():
        """Minimizza la finestra principale (non funziona per CLI, solo GUI)."""
        try:
            if platform.system() == "Windows":
                import ctypes
                hwnd = ctypes.windll.kernel32.GetConsoleWindow()
                if hwnd != 0:
                    ctypes.windll.user32.ShowWindow(hwnd, 6)  # 6 = SW_MINIMIZE
            elif platform.system() == "Linux":
                os.system("wmctrl -r :ACTIVE: -b add,hidden")
            elif platform.system() == "Darwin":  # macOS
                os.system("osascript -e 'tell app \"System Events\" to keystroke \"m\" using cmd key'")
        except Exception as e:
            print(f"Warning: Could not minimize window: {e}")

    @staticmethod
    def maximize_current_window():
        """Massimizza la finestra principale."""
        try:
            if platform.system() == "Windows":
                import ctypes
                hwnd = ctypes.windll.kernel32.GetConsoleWindow()
                if hwnd != 0:
                    ctypes.windll.user32.ShowWindow(hwnd, 9)  # 9 = SW_RESTORE
            elif platform.system() == "Linux":
                os.system("wmctrl -r :ACTIVE: -b remove,hidden")
        except Exception as e:
            print(f"Warning: Could not maximize window: {e}")
