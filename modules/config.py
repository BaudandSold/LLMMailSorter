"""
Config module - Handles loading, creation and management of configuration.
"""

import os
import configparser
from pathlib import Path

class Config:
    """Handles configuration loading, creation and management."""
    
    def __init__(self, display, config_path=None):
        """Initialize with optional custom config path."""
        self.display = display
        self.config = configparser.ConfigParser()
        
        if config_path:
            self.config_path = Path(config_path)
        else:
            self.config_path = Path.home() / '.config' / 'proton_mail_sorter.ini'
        
        # Load or create config
        self.load()
    
    def load(self):
        """Load configuration or create default if not exists."""
        if self.config_path.exists():
            self.config.read(self.config_path)
            self.display.success(f"Loaded configuration from {self.config_path}")
            return True
        else:
            self.display.info("No configuration found. Creating default configuration...")
            self._create_default_config()
            return False
    
    def _create_default_config(self):
        """Create a default configuration file."""
        # Create default configuration
        self.config['IMAP'] = {
            'server': 'localhost', 
            'port': '143', 
            'username': 'your_username',
            'password': 'your_password', 
            'use_ssl': 'False', 
            'use_starttls': 'True'
        }
        
        self.config['LLM'] = {
            'api_url': 'http://localhost:1234/v1/chat/completions',
            'system_prompt': 'You are an email classifier. Categorize each email into one of these categories: Work, Personal, Finance, Shopping, Newsletter, Spam, Family, School.',
        }
        
        self.config['Folders'] = {
            'Work': 'Folders/Work', 
            'Personal': 'Folders/Personal', 
            'Finance': 'Folders/Finance',
            'Shopping': 'Folders/Shopping', 
            'Newsletter': 'Folders/Newsletter', 
            'Spam': 'Folders/Junk', 
            'Family': 'Folders/Family', 
            'School': 'Folders/School'
        }
        
        self.config['PersonalContext'] = {
            'enabled': 'True', 
            'context_file': '~/.config/proton_mail_sorter_context.txt'
        }
        
        self.config['Advanced'] = {
            'search_method': 'ALL',        # Options: ALL, UNSEEN, SINCE_DAYS
            'days_to_search': '30',        # For SINCE_DAYS search method
            'process_all_folders': 'False', # Process emails from all folders
            'folders_to_process': 'INBOX'  # Comma-separated list of folders
        }
        
        self.config['Display'] = {
            'show_banner': 'True',         # Show startup banner
            'color_output': 'True',        # Use colored output
            'debug_level': 'normal',       # Options: minimal, normal, verbose
            'use_panes': 'True'            # Use two-pane layout
        }
        
        # Create directory if it doesn't exist
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Write default config
        with open(self.config_path, 'w') as configfile:
            self.config.write(configfile)
        
        self.display.success(f"Created default configuration at {self.config_path}")
        self.display.info(f"Please edit this file with your IMAP and LLM details.")
        
        # Create example personal context file
        self._create_default_context()
    
    def _create_default_context(self):
        """Create default personal context file if it doesn't exist."""
        if 'PersonalContext' not in self.config:
            return
            
        context_file = self.config['PersonalContext'].get('context_file', '~/.config/proton_mail_sorter_context.txt')
        context_path = Path(os.path.expanduser(context_file))
        
        if context_path.exists():
            return
            
        context_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(context_path, 'w') as f:
            f.write("""# Personal Context Information
# Add information about people, organizations, and relationships
# Each line is a separate piece of information
# Format: Simply write statements like "Jack is my son"

Jack is my son
ABC Company is where I work
teachers@schoolname.edu are from my child's school
newsletters@mybank.com is my bank
""")
        self.display.info(f"Created example personal context file at {context_path}")
    
    def get(self):
        """Return the loaded configuration."""
        return self.config
    
    def load_personal_context(self):
        """Load personal context from the configured file."""
        if 'PersonalContext' not in self.config:
            return []
        
        if not self.config['PersonalContext'].getboolean('enabled', False):
            return []
        
        context_file = self.config['PersonalContext'].get('context_file', '~/.config/proton_mail_sorter_context.txt')
        context_path = Path(os.path.expanduser(context_file))
        
        if not context_path.exists():
            self.display.warning(f"Personal context file not found at {context_path}")
            return []
        
        try:
            with open(context_path, 'r') as f:
                lines = f.readlines()
            
            # Filter out comments and empty lines
            context_items = [line.strip() for line in lines 
                            if line.strip() and not line.strip().startswith('#')]
            
            self.display.success(f"Loaded {len(context_items)} personal context items")
            return context_items
        
        except Exception as e:
            self.display.error(f"Error loading personal context: {e}")
            return []
