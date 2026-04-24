"""Logging configuration with colored output."""

import logging
import sys


class ColoredFormatter(logging.Formatter):
    """Custom formatter with colored [DESIGNER] prefix."""

    # ANSI color codes
    BLUE = '\033[34m'
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

    def format(self, record):
        # Add color to [DESIGNER] prefix
        prefix = f"{self.BLUE}[DESIGNER]{self.RESET}"
        msg = super().format(record)
        # Replace [DESIGNER] with colored version
        msg = msg.replace('[DESIGNER]', prefix, 1)
        return msg


def setup_logging():
    """Configure logging with colored output."""
    # Remove existing handlers
    logging.root.handlers = []

    # Create handler with colored formatter
    handler = logging.StreamHandler(sys.stdout)
    formatter = ColoredFormatter(
        fmt='[DESIGNER] %(levelname)s - %(message)s',
        datefmt='%H:%M:%S'
    )
    handler.setFormatter(formatter)

    # Configure root logger
    logging.basicConfig(
        level=logging.DEBUG,
        handlers=[handler]
    )
