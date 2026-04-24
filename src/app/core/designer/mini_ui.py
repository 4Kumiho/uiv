"""Mini UI - Recording HUD (dark theme, runs in separate thread)."""

import tkinter as tk
import sys
from threading import Thread
from pynput import keyboard

_BG      = "#1a1a2e"
_FG      = "#e0e0e0"
_RED     = "#e74c3c"
_ORANGE  = "#f39c12"
_GREEN   = "#27ae60"



class MiniUI:
    def __init__(self, mode='DESIGNER', on_end_callback=None, on_input_end_callback=None, monitor_info=None):
        """
        mode: 'DESIGNER' o 'EXECUTOR'
        on_end_callback: chiamato quando premi ESC
        on_input_end_callback: chiamato quando premi F9/ENTER
        monitor_info: dict con left, top, width, height del monitor
        """
        self.mode = mode
        self.on_end_callback = on_end_callback
        self.on_input_end_callback = on_input_end_callback
        self.monitor_info = monitor_info
        self.is_ready = False

        self.window = None
        self.status_label = None
        self.step_var = None
        self.f9_button = None
        self.listener = None
        self._running = False
        self._thread = None
        self._color = _RED

        self._start_window_thread()

    def _start_window_thread(self):
        """Avvia la finestra in un thread separato."""
        self._running = True
        self._thread = Thread(target=self._run_window, daemon=True)
        self._thread.start()

    def _run_window(self):
        """Crea e avvia la finestra tkinter con mainloop()."""
        self.window = tk.Tk()
        self.window.overrideredirect(True)
        self.window.attributes('-topmost', True)
        self.window.attributes('-alpha', 0.92)
        self.window.configure(bg=_BG)

        # Posizionamento: bottom-left angolo con offset minimo
        w, h = 180, 28
        if self.monitor_info:
            x = self.monitor_info['left']
            y = self.monitor_info['top'] + self.monitor_info['height'] - h
        else:
            x, y = 0, 0
        self.window.geometry(f"{w}x{h}+{x}+{y}")

        # Single row with all elements
        main_row = tk.Frame(self.window, bg=_BG)
        main_row.pack(fill="both", padx=2, pady=0)

        # All elements on same row
        tk.Label(main_row, text="●", fg=_ORANGE, bg=_BG,
                 font=("Segoe UI", 9, "bold")).pack(side="left")

        self.status_label = tk.Label(main_row, text="REC", fg=_FG, bg=_BG,
                                     font=("Segoe UI", 8, "bold"))
        self.status_label.pack(side="left", padx=(2, 0))

        self.step_var = tk.StringVar(value="Step 1")
        tk.Label(main_row, textvariable=self.step_var, fg=_FG, bg=_BG,
                 font=("Segoe UI", 8)).pack(side="left", padx=(2, 0))

        # Spacer
        tk.Label(main_row, text="", bg=_BG, width=4).pack(side="left")

        # F9 button
        self.f9_button = tk.Button(
            main_row, text="F9",
            bg=_ORANGE, fg="#fff",
            activebackground="#d68910", activeforeground="#fff",
            relief="flat", bd=0, padx=3, pady=1,
            font=("Segoe UI", 8, "bold"),
            command=self._on_f9_click,
        )
        self.f9_button.pack(side="left")

        # Keyboard listener
        self.listener = keyboard.Listener(on_press=self._on_key_press)
        self.listener.start()

        # Avvia mainloop
        self.window.mainloop()

    def set_ready(self):
        """Cambia colore a VERDE quando pronto."""
        if not self.window:
            return
        self.window.after(0, lambda: self._do_set_ready())

    def _do_set_ready(self):
        """Esegui set_ready sul tkinter thread."""
        if self.status_label and self.f9_button:
            self.status_label.config(fg=_GREEN)
            self.f9_button.config(bg=_GREEN, activebackground="#229954")
            self._color = _GREEN
            self.is_ready = True

    def set_loading(self):
        """Cambia colore a ARANCIONE durante il caricamento dei modelli."""
        if not self.window:
            return
        self.window.after(0, lambda: self._do_set_loading())

    def _do_set_loading(self):
        """Esegui set_loading sul tkinter thread."""
        if self.status_label and self.f9_button:
            self.status_label.config(fg=_ORANGE)
            self.f9_button.config(bg=_ORANGE, activebackground="#d68910")
            self._color = _ORANGE
            self.is_ready = False

    def set_saving(self):
        """Torna ROSSO durante il salvataggio."""
        if not self.window:
            return
        self.window.after(0, lambda: self._do_set_saving())

    def _do_set_saving(self):
        """Esegui set_saving sul tkinter thread."""
        if self.status_label and self.f9_button:
            self.status_label.config(fg=_RED)
            self.f9_button.config(bg=_RED, activebackground="#c0392b")
            self._color = _RED
            self.is_ready = False

    def set_step(self, n: int):
        """Aggiorna il numero dello step."""
        if not self.window:
            return
        self.window.after(0, lambda: self._do_set_step(n))

    def _do_set_step(self, n: int):
        """Esegui set_step sul tkinter thread."""
        if self.step_var:
            self.step_var.set(f"Step {n}")

    def _on_f9_click(self):
        """Callback quando clicchi F9 button."""
        if self.on_input_end_callback:
            self.on_input_end_callback()

    def _on_key_press(self, key):
        """Rileva ESC, F9, ENTER."""
        try:
            if key == keyboard.Key.esc:
                print("[MiniUI] ESC detected", file=sys.stderr, flush=True)
                if self.on_end_callback:
                    self.on_end_callback()
                self.close()

            elif key == keyboard.Key.f9 or key == keyboard.Key.enter:
                print("[MiniUI] F9/ENTER detected", file=sys.stderr, flush=True)
                if self.on_input_end_callback:
                    self.on_input_end_callback()

        except AttributeError:
            pass

    def close(self):
        """Chiude la Mini UI."""
        self._running = False
        if self.listener:
            self.listener.stop()
        if self.window:
            try:
                self.window.after(0, lambda: self.window.quit())
            except RuntimeError:
                # Window already destroyed or event loop closed
                pass

    def update(self):
        """Update tkinter (no-op since mainloop runs in thread)."""
        pass
