"""
History module - Manages the history of processed emails.

This module is responsible for:
- Tracking which emails have been processed
- Creating unique identifiers for emails
- Loading and saving processing history
- Maintaining detailed history for rule suggestions
"""

import json
import hashlib
from pathlib import Path

class HistoryManager:
    """Manages history of processed emails to avoid duplicates."""
    
    def __init__(self, display):
        """Initialize with display handler."""
        self.display = display
        self.history_file = Path.home() / '.config' / 'proton_mail_sorter_history.json'
        self.full_history_file = Path.home() / '.config' / 'proton_mail_sorter_full_history.json'
    
    def get_email_hash(self, email_data):
        """Create a unique hash for an email."""
        hash_input = f"{email_data['subject']}|{email_data['from']}|{email_data['date']}"
        return hashlib.sha256(hash_input.encode()).hexdigest()
    
    def load(self, max_history=5000):
        """Load the set of already processed email hashes."""
        if not self.history_file.exists():
            self.display.info("No email history file found")
            return set()
            
        try:
            with open(self.history_file, 'r') as f:
                history = json.load(f)
            
            # Trim if needed    
            if len(history) > max_history:
                self.display.info(f"Trimming email history from {len(history)} to {max_history} entries")
                history = history[-max_history:]
                self._save_list(history)
                    
            return set(history)
        except Exception as e:
            self.display.error(f"Error loading email history: {e}")
            return set()
    
    def save(self, email_hash, max_history=5000):
        """Save an email hash to the processed list."""
        self.history_file.parent.mkdir(parents=True, exist_ok=True)
        
        processed_emails = self.load(max_history)
        processed_emails.add(email_hash)
        
        try:
            self._save_list(list(processed_emails)[-max_history:])
            self.display.debug(f"Saved email to history")
            return True
        except Exception as e:
            self.display.error(f"Error saving email history: {e}")
            return False
    
    def clear(self):
        """Clear the email processing history."""
        try:
            self._save_list([])
            # Also clear full history
            self._save_full_list([])
            self.display.success("Email history cleared")
            return True
        except Exception as e:
            self.display.error(f"Error clearing email history: {e}")
            return False
    
    def _save_list(self, history_list):
        """Save the history list to file."""
        with open(self.history_file, 'w') as f:
            json.dump(history_list, f)
    
    def load_full_history(self, max_entries=1000):
        """Load detailed email history for analysis."""
        if not self.full_history_file.exists():
            self.display.info("No full email history file found")
            return []
            
        try:
            with open(self.full_history_file, 'r') as f:
                history = json.load(f)
            
            self.display.success(f"Loaded {len(history)} detailed email history entries")
            return history[:max_entries]  # Return limited number of most recent entries
        except Exception as e:
            self.display.error(f"Error loading detailed email history: {e}")
            return []
    
    def save_full_history(self, email_data):
        """Save detailed email data to history."""
        # Create minimal version with only needed fields
        history_entry = {
            'subject': email_data.get('subject', ''),
            'from': email_data.get('from', ''),
            'date': email_data.get('date', ''),
            'category': email_data.get('category', 'Unknown'),
            'folder': email_data.get('folder', '')
        }
        
        # Load existing history
        history = []
        if self.full_history_file.exists():
            try:
                with open(self.full_history_file, 'r') as f:
                    history = json.load(f)
            except:
                history = []
        
        # Add new entry to the front (most recent first)
        history.insert(0, history_entry)
        
        # Limit history size to 2000 entries
        max_history = 2000
        if len(history) > max_history:
            history = history[:max_history]
        
        # Save updated history
        try:
            self._save_full_list(history)
            return True
        except Exception as e:
            self.display.error(f"Error saving detailed email history: {e}")
            return False
    
    def _save_full_list(self, history_list):
        """Save the detailed history list to file."""
        self.full_history_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.full_history_file, 'w') as f:
            json.dump(history_list, f)
