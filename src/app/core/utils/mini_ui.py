"""Mini UI - feedback visuale durante Designer/Executor."""

import tkinter as tk
from pynput import keyboard
import threading


class MiniUI:
    def __init__(self, mode='DESIGNER', on_end_callback=None, on_input_end_callback=None):
        """
        mode: 'DESIGNER' o 'EXECUTOR'
        on_end_callback: chiamato quando premi ESC
        on_input_end_callback: chiamato quando premi F9/ENTER
        """
        self.mode = mode
        self.on_end_callback = on_end_callback
        self.on_input_end_callback = on_input_end_callback
        self.is_ready = False
        self.window = None
        self.label = None
        self.listener = None

        self._create_ui()

    def _create_ui(self):
        """Crea la finestra Mini UI."""
        self.window = tk.Tk()
        self.window.title(f"{self.mode}")
        self.window.geometry("150x50+0+0")
        self.window.attributes('-topmost', True)
        self.window.attributes('-alpha', 0.8)

        self.label = tk.Label(
            self.window,
            text=f"{self.mode}",
            fg="white",
            bg="red",  # Inizio ROSSO
            font=("Arial", 12, "bold"),
            width=15,
            height=2
        )
        self.label.pack()

        # Keyboard listener in thread separato
        self.listener = keyboard.Listener(on_press=self._on_key_press)
        self.listener.start()

    def set_ready(self):
        """Cambia colore a VERDE quando pronto."""
        if self.label:
            self.label.config(bg="green")
            self.label.config(text=f"{self.mode} ✓")
            self.is_ready = True

    def set_saving(self):
        """Torna ROSSO durante il salvataggio."""
        if self.label:
            self.label.config(bg="red")
            self.label.config(text="Saving...")
            self.is_ready = False

    def set_action(self, text=""):
        """Mostra testo durante un'azione."""
        if self.label:
            self.label.config(text=text)

    def _on_key_press(self, key):
        """Rileva ESC, F9, ENTER."""
        try:
            if key == keyboard.Key.esc:
                if self.on_end_callback:
                    self.on_end_callback()
                self.close()

            elif key == keyboard.Key.f9 or key == keyboard.Key.enter:
                if self.mode == 'DESIGNER' and self.on_input_end_callback:
                    self.on_input_end_callback()

        except AttributeError:
            pass

    def close(self):
        """Chiude la Mini UI."""
        if self.listener:
            self.listener.stop()
        if self.window:
            self.window.destroy()

    def update(self):
        """Update tkinter."""
        if self.window:
            self.window.update()
