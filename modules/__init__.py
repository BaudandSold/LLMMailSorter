"""
Module package initialization.

This file makes the modules directory a proper Python package.
It also provides version information and easy imports.
"""

__version__ = '1.0.0'

# For convenient imports
from .display import Display
from .config import Config
from .imap_client import ImapClient
from .llm_client import LlmClient
from .history import HistoryManager
