"""
Display module - Handles all console output formatting with style.

This module provides a two-pane layout:
- Left pane: Current and previous email being processed
- Right pane: History of processed emails
"""

import os
import shutil
import time
from datetime import datetime

class Display:
    """Handles all display-related functionality with styled console output."""
    
    # Terminal color codes
    HEADER = '\033[95m'      # Magenta
    BLUE = '\033[94m'        # Blue
    CYAN = '\033[96m'        # Cyan
    GREEN = '\033[92m'       # Green
    YELLOW = '\033[93m'      # Yellow
    RED = '\033[91m'         # Red
    ENDC = '\033[0m'         # Reset color
    BOLD = '\033[1m'         # Bold
    DIM = '\033[2m'          # Dim
    UNDERLINE = '\033[4m'    # Underline
    BLINK = '\033[5m'        # Blink
    RETRO = '\033[38;5;208m' # Retro orange
    
    # Custom color combinations
    SUCCESS = '\033[1;92m'   # Bold Green
    WARNING = '\033[1;93m'   # Bold Yellow
    ERROR = '\033[1;91m'     # Bold Red
    INFO = '\033[1;96m'      # Bold Cyan
    ACCENT = '\033[1;95m'    # Bold Magenta
    
    def __init__(self):
        """Initialize display settings with defaults."""
        self.use_color = True
        self.debug_level = "normal"
        self.show_banner = True
        
        # Get initial terminal size
        self.update_terminal_size()
        
        # Processing history
        self.email_history = []
        self.current_email = None
        self.previous_email = None
        
        # Display mode
        self.use_panes = True  # Set to False to fall back to simple output
        
        # Clear screen on startup
        os.system('cls' if os.name == 'nt' else 'clear')
    
    def update_settings(self, config):
        """Update display settings from config."""
        if config and 'Display' in config:
            self.use_color = config['Display'].getboolean('color_output', True)
            self.debug_level = config['Display'].get('debug_level', 'normal').lower()
            self.show_banner = config['Display'].getboolean('show_banner', True)
            self.use_panes = config['Display'].getboolean('use_panes', True)
    
    def update_terminal_size(self):
        """Update the stored terminal dimensions."""
        try:
            columns, lines = shutil.get_terminal_size()
            self.terminal_width = max(80, columns)
            self.terminal_height = max(24, lines)
            
            # Adjust pane widths based on terminal size
            # If terminal is too narrow, use more conservative widths
            if self.terminal_width < 100:
                self.left_pane_width = min(50, int(self.terminal_width * 0.55) - 1)
            else:
                self.left_pane_width = min(60, int(self.terminal_width * 0.6) - 1)
                
            # Ensure minimum width for right pane
            right_pane_min = 25
            right_pane_calculated = self.terminal_width - self.left_pane_width - 3
            
            if right_pane_calculated < right_pane_min:
                # If can't fit both panes properly, reduce left pane
                self.left_pane_width = self.terminal_width - right_pane_min - 3
                # If still too small, disable panes
                if self.left_pane_width < 30:
                    self.use_panes = False
                right_pane_calculated = self.terminal_width - self.left_pane_width - 3
                
            self.right_pane_width = right_pane_calculated
        except:
            # Safe fallback values
            self.terminal_width = 80
            self.terminal_height = 24
            self.left_pane_width = 45
            self.right_pane_width = 32
    
    def _colorize(self, text, color):
        """Apply color if color output is enabled."""
        if self.use_color:
            return f"{color}{text}{self.ENDC}"
        return text
    
    def _truncate_string(self, text, max_length):
        """Truncate string to maximum length with ellipsis."""
        if not text:
            return ""
        if len(text) <= max_length:
            return text
        return text[:max_length-3] + "..."
    
    def _center_string(self, text, width):
        """Center a string within a given width."""
        padding = max(0, width - len(text))
        left_padding = padding // 2
        right_padding = padding - left_padding
        return " " * left_padding + text + " " * right_padding
    
    def refresh_display(self):
        """Refresh the entire display with current data."""
        # Skip if not using panes
        if not self.use_panes:
            return
            
        # Update terminal dimensions
        self.update_terminal_size()
        
        # Clear screen
        os.system('cls' if os.name == 'nt' else 'clear')
        
        # Print banner if enabled
        if self.show_banner:
            print(self._colorize("=== PROTON MAIL SORTER ===", self.HEADER))
            print(f"Processing time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            print(self._colorize("=" * self.terminal_width, self.HEADER))
        
        # Build the two-pane layout
        self._render_layout()
    
    def _render_layout(self):
        """Render the two-pane layout."""
        # Adjust to prevent overflow 
        term_width = min(self.terminal_width, 200)  # Prevent extreme widths
        term_height = min(self.terminal_height, 50)  # Prevent extreme heights
        
        # Recalculate dimensions to ensure they fit
        self.update_terminal_size()
        
        # Top border
        print(self._colorize("╔" + "═" * self.left_pane_width + "╦" + "═" * self.right_pane_width + "╗", self.BLUE))
        
        # Headers
        left_header = self._center_string("CURRENT PROCESSING", self.left_pane_width)
        right_header = self._center_string("PROCESSING HISTORY", self.right_pane_width)
        print(self._colorize("║", self.BLUE) + self._colorize(left_header, self.BOLD) + 
              self._colorize("║", self.BLUE) + self._colorize(right_header, self.BOLD) + 
              self._colorize("║", self.BLUE))
        
        # Separator
        print(self._colorize("╠" + "═" * self.left_pane_width + "╬" + "═" * self.right_pane_width + "╣", self.BLUE))
        
        # Calculate content height (leave room for borders and headers)
        content_height = min(term_height - 8, 20)  # Reasonable max height
        
        # Render content
        for i in range(content_height):
            # Left pane content (current and previous email)
            left_content = ""
            if i == 0 and self.current_email:
                left_content = f" Current: {self.current_email.get('subject', 'Unknown')}"
            elif i == 1 and self.current_email:
                left_content = f"   From: {self.current_email.get('from', 'Unknown')}"
            elif i == 2 and self.current_email:
                left_content = f"  Class: {self.current_email.get('category', 'Processing...')}"
            elif i == 4 and self.previous_email:
                left_content = f" Previous: {self.previous_email.get('subject', 'Unknown')}"
            elif i == 5 and self.previous_email:
                left_content = f"   From: {self.previous_email.get('from', 'Unknown')}"
            elif i == 6 and self.previous_email:
                left_content = f"  Class: {self.previous_email.get('category', 'Unknown')} → {self.previous_email.get('folder', 'Unknown')}"
            
            # Right pane content (history of processed emails)
            right_content = ""
            history_index = i
            if history_index < len(self.email_history):
                hist_email = self.email_history[history_index]
                right_content = f" {hist_email.get('category', 'Unknown')} | {self._truncate_string(hist_email.get('subject', 'Unknown'), self.right_pane_width - 15)}"
            
            # Truncate content to fit panes
            left_content = self._truncate_string(left_content, self.left_pane_width - 2)
            right_content = self._truncate_string(right_content, self.right_pane_width - 2)
            
            # Pad content to fill panes
            left_content = left_content + " " * (self.left_pane_width - len(left_content))
            right_content = right_content + " " * (self.right_pane_width - len(right_content))
            
            # Print the row
            print(self._colorize("║", self.BLUE) + left_content + 
                  self._colorize("║", self.BLUE) + right_content + 
                  self._colorize("║", self.BLUE))
        
        # Bottom border
        print(self._colorize("╚" + "═" * self.left_pane_width + "╩" + "═" * self.right_pane_width + "╝", self.BLUE))
    
    def banner(self):
        """Display startup banner."""
        if not self.show_banner:
            return
        
        # Shorter banner for smaller terminals
        if self.terminal_width < 60:
            print(self._colorize("=== PROTON MAIL SORTER ===", self.HEADER))
            print(self._colorize("v1.0.0 | Two-Pane Edition", self.DIM))
            return
            
        banner = """
    ╭━━━┳━━━┳━━━┳━━━━┳━━━┳━╮╱╭╮
    ┃╭━╮┃╭━╮┃╭━╮┃╭╮╭╮┃╭━╮┃┃╰╮┃┃
    ┃╰━╯┃┃╱┃┃┃╱┃┣╯┃┃╰┫┃╱┃┃╭╮╰╯┃
    ┃╭━━┫╰━╯┃┃╱┃┃╱┃┃╱┃┃╱┃┃┃╰╮┃┃
    ┃┃╱╱┃╭━╮┃╰━╯┃╱┃┃╱┃╰━╯┃┃╱┃┃┃
    ╰╯╱╱╰╯╱╰┻━━━╯╱╰╯╱╰━━━┻╯╱╰━╯
    """
        print(self._colorize(banner, self.RETRO))
        print(f"\n{self._colorize('Email organizer with LLM-powered intelligence', self.BOLD + self.CYAN)}")
        print(f"{self._colorize('v1.0.0 | Two-Pane Edition', self.DIM)}\n")
        
        # Wait a moment to let the user see the banner
        time.sleep(0.5)
        
        # Initial display refresh
        self.refresh_display()
    
    def header(self, text, char="=", width=None):
        """Print a styled header."""
        # If in pane mode, just refresh display
        if self.use_panes:
            self.refresh_display()
            return
            
        width = width or self.terminal_width
        
        print(f"\n{self._colorize(char * width, self.ACCENT)}")
        print(f"{self._colorize(text.center(width), self.BOLD + self.BLUE)}")
        print(f"{self._colorize(char * width, self.ACCENT)}")
    
    def subheader(self, text):
        """Print a styled subheader."""
        print(f"\n{self._colorize(f'▸ {text}', self.CYAN + self.BOLD)}")
    
    def success(self, text):
        """Print a success message."""
        print(f"{self._colorize(f'✓ {text}', self.SUCCESS)}")
    
    def error(self, text):
        """Print an error message."""
        print(f"{self._colorize(f'✗ {text}', self.ERROR)}")
    
    def warning(self, text):
        """Print a warning message."""
        print(f"{self._colorize(f'⚠ {text}', self.WARNING)}")
    
    def info(self, text):
        """Print an info message."""
        print(f"{self._colorize(f'ℹ {text}', self.INFO)}")
    
    def debug(self, text, level="normal"):
        """Print a debug message if debug level is sufficient."""
        debug_levels = {"minimal": 1, "normal": 2, "verbose": 3}
        
        if debug_levels.get(self.debug_level, 0) >= debug_levels.get(level, 0):
            print(f"{self._colorize(f'  {text}', self.DIM)}")
    
    def progress(self, current, total, text="Processing", width=30):
        """
        Print a progress indicator with percentage and optional time estimate.
        
        Args:
            current: Current progress count
            total: Total items to process
            text: Description of the process being tracked
            width: Width of the progress bar
        """
        if not self.use_color:
            print(f"\r{text}: {current}/{total} ({int(100 * current / total)}%)", end='', flush=True)
            if current == total:
                print()
            return
        
        # Calculate progress    
        progress = current / total
        percent = int(100 * progress)
        
        # Create a more detailed progress bar
        bar_filled = '█' * int(width * progress)
        bar_empty = '▒' * (width - len(bar_filled))
        
        # Show process info - include time estimate if in the text
        if " - " in text and "remaining" in text:
            process_info = text
        else:
            process_info = f"{text}: {current}/{total}"
        
        # Construct the full progress line
        progress_line = f"\r{self._colorize(process_info, self.RETRO)} {self._colorize(f'[{bar_filled}{bar_empty}] {percent}%', self.BOLD)}"
        
        # Print the progress line
        print(progress_line, end='', flush=True)
        if current == total:
            print()
    
    def email_box(self, email_data):
        """Display email information and update the current processing display."""
        # Update email tracking
        if self.current_email:
            self.previous_email = self.current_email.copy()  # Make a copy to avoid reference issues
        self.current_email = email_data.copy()  # Make a copy to avoid reference issues
        
        # Refresh the display if using panes
        if self.use_panes:
            self.refresh_display()
            return
            
        # Otherwise use the traditional format
        subject = email_data.get('subject', 'No Subject')
        sender = email_data.get('from', 'Unknown Sender')
        date = email_data.get('date', 'Unknown Date')
        
        # Truncate long values
        if len(subject) > 50:
            subject = subject[:47] + "..."
        if len(sender) > 50:
            sender = sender[:47] + "..."
        
        width = min(60, self.terminal_width - 2)
        
        if not self.use_color:
            print("\n+", "-" * width, "+", sep="")
            print("| EMAIL DETAILS", " " * (width - 14), "|")
            print("+", "-" * width, "+", sep="")
            print(f"| Subject: {subject}", " " * (width - 10 - len(subject)), "|")
            print(f"| From: {sender}", " " * (width - 7 - len(sender)), "|")
            print(f"| Date: {date}", " " * (width - 7 - len(date)), "|")
            print("+", "-" * width, "+", sep="")
            return
        
        print(f"\n{self._colorize('╔' + '═' * width + '╗', self.BLUE)}")
        print(f"{self._colorize('║', self.BLUE)} {self._colorize('EMAIL DETAILS', self.BOLD)}{' ' * (width - 14)}{self._colorize('║', self.BLUE)}")
        print(f"{self._colorize('╠' + '═' * width + '╣', self.BLUE)}")
        print(f"{self._colorize('║', self.BLUE)} {self._colorize('Subject:', self.CYAN)} {subject}{' ' * (width - 9 - len(subject))}{self._colorize('║', self.BLUE)}")
        print(f"{self._colorize('║', self.BLUE)} {self._colorize('From:', self.CYAN)} {sender}{' ' * (width - 6 - len(sender))}{self._colorize('║', self.BLUE)}")
        print(f"{self._colorize('║', self.BLUE)} {self._colorize('Date:', self.CYAN)} {date}{' ' * (width - 6 - len(date))}{self._colorize('║', self.BLUE)}")
        print(f"{self._colorize('╚' + '═' * width + '╝', self.BLUE)}")
    
    def status(self, category, target_folder):
        """Display email classification status and update current email information."""
        if self.current_email:
            self.current_email['category'] = category
            self.current_email['folder'] = target_folder
        
        # Refresh display in pane mode
        if self.use_panes:
            self.refresh_display()
        else:
            # Traditional output
            print(f"\n{self._colorize('Classification:', self.BOLD)} {self._colorize(category, self.GREEN)}")
            print(f"{self._colorize('Target Folder:', self.BOLD)} {self._colorize(target_folder, self.YELLOW)}")
    
    def add_to_history(self, email_data):
        """Add a processed email to the history."""
        # Only add if it has a category
        if email_data and 'category' in email_data:
            # Create a simplified history entry
            history_entry = {
                'subject': email_data.get('subject', 'No Subject'),
                'from': email_data.get('from', 'Unknown Sender'),
                'category': email_data.get('category', 'Unknown'),
                'folder': email_data.get('folder', 'Unknown')
            }
            
            # Add to history (keep most recent on top)
            self.email_history.insert(0, history_entry)
            
            # Only keep the most recent entries
            max_history = min(100, self.terminal_height - 8)
            if len(self.email_history) > max_history:
                self.email_history = self.email_history[:max_history]
            
            # Refresh display in pane mode
            if self.use_panes:
                self.refresh_display()
    
    def folder_list(self, folders, title="Available IMAP folders:"):
        """Display a formatted list of folders."""
        # Ensure we're not in pane mode for this
        old_pane_setting = self.use_panes
        self.use_panes = False
        
        self.subheader(title)
        
        # Group folders by type
        system_folders = []
        custom_folders = []
        other_folders = []
        
        for folder in folders:
            if folder in ["INBOX", "Sent", "Trash", "Drafts", "Archive", "Spam", "All Mail", "Starred"]:
                system_folders.append(folder)
            elif folder.startswith("Folders/"):
                custom_folders.append(folder)
            else:
                other_folders.append(folder)
        
        # Print organized folder list
        if system_folders:
            print(self._colorize("\nSystem Folders:", self.BOLD))
            for i, folder in enumerate(sorted(system_folders), 1):
                print(f"  {i}. {self._colorize(folder, self.CYAN)}")
        
        if custom_folders:
            print(self._colorize("\nCustom Folders:", self.BOLD))
            for i, folder in enumerate(sorted(custom_folders), 1):
                folder_name = folder.split('/', 1)[1] if '/' in folder else folder
                print(f"  {i}. {self._colorize(folder_name, self.GREEN)} (Full path: {self._colorize(folder, self.DIM)})")
        
        if other_folders:
            print(self._colorize("\nOther Folders:", self.BOLD))
            for i, folder in enumerate(sorted(other_folders), 1):
                print(f"  {i}. {self._colorize(folder, self.YELLOW)}")
        
        # Restore previous pane setting
        self.use_panes = old_pane_setting
