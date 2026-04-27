"""Logging configuration with colored output."""

import logging
import sys


class ColoredFormatter(logging.Formatter):
    """Custom formatter with colored [DESIGNER] or [EXECUTOR] prefix."""

    # ANSI color codes
    BLUE = '\033[34m'
    GREEN = '\033[32m'
    CYAN = '\033[36m'
    RESET = '\033[0m'

    # Log level colors
    COLORS = {
        'DEBUG': CYAN,
        'INFO': BLUE,
        'WARNING': '\033[33m',  # Yellow
        'ERROR': '\033[31m',    # Red
        'CRITICAL': '\033[35m', # Magenta
    }

    def __init__(self, fmt=None, datefmt=None, mode='DESIGNER'):
        super().__init__(fmt, datefmt)
        self.mode = mode
        self.prefix_placeholder = f"[{mode}]"

    def format(self, record):
        # Choose color based on mode
        color = self.GREEN if self.mode == 'EXECUTOR' else self.BLUE
        prefix = f"{color}[{self.mode}]{self.RESET}"
        msg = super().format(record)
        # Replace placeholder with colored version
        msg = msg.replace(self.prefix_placeholder, prefix, 1)
        return msg


def setup_logging(mode='DESIGNER'):
    """Configure logging with colored output.

    Args:
        mode: 'DESIGNER' or 'EXECUTOR'
    """
    # Remove existing handlers
    logging.root.handlers = []

    # Create handler with colored formatter
    handler = logging.StreamHandler(sys.stdout)
    formatter = ColoredFormatter(
        fmt=f'[{mode}] %(message)s',
        datefmt='%H:%M:%S',
        mode=mode
    )
    handler.setFormatter(formatter)

    # Configure root logger
    logging.basicConfig(
        level=logging.INFO,
        handlers=[handler]
    )
