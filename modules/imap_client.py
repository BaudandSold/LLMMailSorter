"""
IMAP Client module - Handles email retrieval and folder operations.

This module is responsible for:
- Connecting to IMAP servers
- Retrieving emails from folders
- Moving emails between folders
- Listing available folders
"""

import time
import imaplib
import email
import re
from datetime import datetime, timedelta

class ImapClient:
    """Handles IMAP connection and email operations."""
    
    def __init__(self, config, display):
        """Initialize with configuration and display handler."""
        self.config = config
        self.display = display
        self.connection = None
    
    def connect(self):
        """Connect to IMAP server and return success status."""
        server = self.config['IMAP']['server']
        port = int(self.config['IMAP'].get('port', 143))
        username = self.config['IMAP']['username']
        password = self.config['IMAP']['password']
        use_ssl = self.config['IMAP'].getboolean('use_ssl', False)
        use_starttls = self.config['IMAP'].getboolean('use_starttls', False)
        
        self.display.subheader("IMAP Connection")
        self.display.info(f"Connecting to {server}:{port} as {username}")
        
        try:
            # Connect to the server
            connection_start = time.time()
            
            if use_ssl:
                self.display.info("Using SSL encryption")
                self.connection = imaplib.IMAP4_SSL(server, port)
            else:
                self.connection = imaplib.IMAP4(server, port)
                if use_starttls:
                    self.display.info("Using STARTTLS encryption")
                    self.connection.starttls()
            
            # Login
            self.connection.login(username, password)
            connection_time = time.time() - connection_start
            
            self.display.success(f"Connected to IMAP server in {connection_time:.2f}s")
            return True
        except imaplib.IMAP4.error as e:
            self.display.error(f"IMAP authentication failed: {e}")
        except ConnectionRefusedError:
            self.display.error(f"Connection refused by {server}:{port}")
        except Exception as e:
            self.display.error(f"Error connecting to IMAP server: {e}")
        
        return False
    
    def disconnect(self):
        """Safely disconnect from IMAP server."""
        if self.connection:
            try:
                self.connection.logout()
                self.display.debug("Disconnected from IMAP server")
            except:
                pass
            finally:
                self.connection = None
    
    def list_folders(self):
        """List all folders in the IMAP account."""
        if not self.connection:
            if not self.connect():
                return []
        
        folders = []
        try:
            status, folder_list = self.connection.list()
            if status == 'OK':
                for folder_info in folder_list:
                    folder_info = folder_info.decode('utf-8')
                    if '"/"' in folder_info:
                        folder_name = folder_info.split('"/" ')[1].strip('"')
                    else:
                        folder_name = folder_info.split(') ')[1].strip('"')
                    folders.append(folder_name)
            else:
                self.display.error(f"Error listing folders: {folder_list}")
        except Exception as e:
            self.display.error(f"Error getting folder list: {e}")
        
        return folders
    
    def _get_search_criteria(self):
        """Get the appropriate search criteria based on configuration."""
        if 'Advanced' not in self.config:
            return 'ALL'
            
        search_method = self.config['Advanced'].get('search_method', 'ALL').upper()
        
        if search_method == 'UNSEEN':
            return 'UNSEEN'
        elif search_method == 'SINCE_DAYS':
            days = int(self.config['Advanced'].get('days_to_search', '30'))
            date_since = (datetime.now() - timedelta(days=days)).strftime("%d-%b-%Y")
            return f'SINCE {date_since}'
        else:  # Default to ALL
            return 'ALL'
    
    def get_emails_from_folder(self, folder, limit=100, debug=False):
        """Fetch emails from a specific IMAP folder with improved search capabilities."""
        if not self.connection:
            if not self.connect():
                return []
        
        emails = []
        
        try:
            self.display.subheader(f"Processing Folder: {folder}")
            status, messages = self.connection.select(folder, readonly=True)
            if status != 'OK':
                self.display.error(f"Error selecting folder {folder}: {messages}")
                return emails
            
            # Try different search approaches to maximize email retrieval
            search_methods = [
                self._get_search_criteria(),  # Try configured search first
                'ALL',                        # Fallback to ALL
                'FLAGGED',                    # Try other search criteria
                '(OR SEEN UNSEEN)'            # This should match everything
            ]
            
            message_ids = []
            self.display.info("Searching for messages...")
            
            for search_method in search_methods:
                if message_ids:
                    break  # Stop if we already found messages
                    
                try:
                    status, data = self.connection.search(None, search_method)
                    if status == 'OK' and data[0]:
                        message_ids = data[0].split()
                        self.display.success(f"Found {len(message_ids)} messages using '{search_method}'")
                        break
                except Exception as e:
                    if debug:
                        self.display.warning(f"Search error with '{search_method}': {e}")
            
            if not message_ids:
                self.display.warning(f"No messages found in {folder} after trying multiple search methods")
                return emails
                
            # Retrieve in batches to avoid timeouts with large mailboxes
            batch_size = 20
            total_messages = len(message_ids)
            
            # Reverse to get newest messages first and limit
            message_ids = message_ids[::-1]
            if limit < total_messages:
                message_ids = message_ids[:limit]
                total_to_process = limit
            else:
                total_to_process = total_messages
                
            self.display.info(f"Preparing to process {total_to_process} messages from {folder}")
            
            # Progress tracker
            processed = 0
            successful = 0
            
            # Process in batches
            for i in range(0, len(message_ids), batch_size):
                batch = message_ids[i:i + batch_size]
                
                # Show batch progress
                batch_num = i//batch_size + 1
                total_batches = (len(message_ids)-1)//batch_size + 1
                self.display.info(f"Batch {batch_num}/{total_batches} ({len(batch)} messages)")
                
                for j, msg_id in enumerate(batch):
                    try:
                        # Update progress
                        processed += 1
                        self.display.progress(processed, total_to_process, "Fetching emails")
                        
                        # Get only the headers first for efficiency
                        status, header_data = self.connection.fetch(msg_id, '(BODY.PEEK[HEADER])')
                        if status != 'OK':
                            continue
                        
                        header_msg = email.message_from_bytes(header_data[0][1])
                        message_id = header_msg.get('Message-ID', '')
                        subject = header_msg.get('Subject', '')
                        from_addr = header_msg.get('From', '')
                        date = header_msg.get('Date', '')
                        
                        # Get the body content
                        status, msg_data = self.connection.fetch(msg_id, '(RFC822)')
                        if status != 'OK':
                            continue
                        
                        # Parse the email
                        msg = email.message_from_bytes(msg_data[0][1])
                        
                        # Extract email body
                        body = ""
                        if msg.is_multipart():
                            for part in msg.walk():
                                if part.get_content_type() == "text/plain":
                                    body_bytes = part.get_payload(decode=True)
                                    if body_bytes:
                                        body = body_bytes.decode('utf-8', errors='replace')
                                    break
                        else:
                            body_bytes = msg.get_payload(decode=True)
                            if body_bytes:
                                body = body_bytes.decode('utf-8', errors='replace')
                        
                        emails.append({
                            'imap_id': msg_id.decode('utf-8'),
                            'message_id': message_id,
                            'subject': subject,
                            'from': from_addr,
                            'date': date,
                            'body': body[:1000] if body else "",  # Truncate body for LLM
                            'folder': folder  # Add source folder
                        })
                        
                        successful += 1
                        if debug:
                            self.display.debug(f"Fetched: {subject}")
                    except Exception as e:
                        if debug:
                            self.display.error(f"Error processing message: {e}")
            
            self.display.success(f"\nSuccessfully retrieved {successful} of {processed} emails from {folder}")
            
        except Exception as e:
            self.display.error(f"Error accessing folder {folder}: {e}")
        
        return emails
    
    def get_emails(self, limit=100, debug=False):
        """Fetch emails from multiple IMAP folders efficiently."""
        if not self.connection:
            if not self.connect():
                return []
        
        all_emails = []
        
        try:
            # Determine which folders to process
            process_all = self.config['Advanced'].getboolean('process_all_folders', False) if 'Advanced' in self.config else False
            
            if process_all:
                self.display.info("Processing all IMAP folders")
                folders = self.list_folders()
                # Filter out special folders
                folders = [f for f in folders if f not in ['Trash', 'Sent', 'Drafts', 'Spam', 'Junk']]
            else:
                folders_str = self.config['Advanced'].get('folders_to_process', 'INBOX') if 'Advanced' in self.config else 'INBOX'
                folders = [f.strip() for f in folders_str.split(',')]
                self.display.info(f"Processing folders: {', '.join(folders)}")
            
            # Process each folder with prioritized retrieval
            remaining_limit = limit
            for folder in folders:
                if remaining_limit <= 0:
                    break
                    
                folder_emails = self.get_emails_from_folder(folder, remaining_limit, debug)
                all_emails.extend(folder_emails)
                
                # Adjust remaining limit
                remaining_limit = limit - len(all_emails)
                if remaining_limit > 0 and folder_emails:
                    self.display.info(f"Need {remaining_limit} more emails to reach limit of {limit}")
                
            self.display.success(f"Retrieved a total of {len(all_emails)} emails")
            
        except Exception as e:
            self.display.error(f"Error in email retrieval: {e}")
        
        return all_emails
    
    def move_email(self, email_data, target_folder):
        """Move an email to a different folder using IMAP commands."""
        if not self.connection:
            if not self.connect():
                return False
        
        self.display.subheader(f"Moving Email to Folder: {target_folder}")
        
        try:
            # Check if the target folder exists and create if needed
            status, folder_list = self.connection.list()
            if status != 'OK':
                self.display.error("Failed to list folders")
                return False
                
            # Parse folder list
            existing_folders = []
            for folder_info in folder_list:
                folder_info = folder_info.decode('utf-8')
                if '"/"' in folder_info:
                    folder_name = folder_info.split('"/" ')[1].strip('"')
                else:
                    folder_name = folder_info.split(') ')[1].strip('"')
                existing_folders.append(folder_name.lower())
            
            # Create folder if it doesn't exist
            if target_folder.lower() not in existing_folders:
                self.display.info(f"Creating folder: {target_folder}")
                if '/' in target_folder:
                    parent = target_folder.split('/')[0]
                    if parent.lower() not in existing_folders:
                        try:
                            self.connection.create(parent)
                            self.display.success(f"Created parent folder: {parent}")
                        except:
                            self.display.warning(f"Couldn't create parent folder: {parent}")
                
                try:
                    self.connection.create(target_folder)
                    self.display.success(f"Created folder: {target_folder}")
                except:
                    self.display.warning(f"Couldn't create folder: {target_folder}")
            
            # Get source folder
            source_folder = email_data.get('folder', 'INBOX')
            status, _ = self.connection.select(source_folder, readonly=False)
            if status != 'OK':
                self.display.error(f"Error selecting folder {source_folder}")
                return False
            
            # Search for the email
            found = False
            msg_id = None
            
            # Try with IMAP ID first
            if 'imap_id' in email_data:
                status, data = self.connection.search(None, email_data['imap_id'])
                if status == 'OK' and data[0]:
                    msg_id = data[0].split()[0]
                    found = True
            
            # Try with Message-ID
            if not found and 'message_id' in email_data:
                msg_id_clean = email_data['message_id'].strip('<>').strip()
                status, data = self.connection.search(None, f'HEADER "Message-ID" "{msg_id_clean}"')
                if status == 'OK' and data[0]:
                    msg_id = data[0].split()[0]
                    found = True
            
            # Try with subject as last resort
            if not found and 'subject' in email_data:
                status, data = self.connection.search(None, f'SUBJECT "{email_data["subject"]}"')
                if status == 'OK' and data[0]:
                    msg_id = data[0].split()[0]
                    found = True
            
            if not found or not msg_id:
                self.display.error(f"Could not find the email in {source_folder}")
                return False
            
            # Copy to target, then delete from source
            status, _ = self.connection.copy(msg_id, target_folder)
            if status != 'OK':
                self.display.error(f"Failed to copy email to {target_folder}")
                return False
            
            # Mark for deletion and expunge
            self.connection.store(msg_id, '+FLAGS', '\\Deleted')
            self.connection.expunge()
            
            self.display.success(f"Successfully moved email to {target_folder}")
            return True
            
        except Exception as e:
            self.display.error(f"Error moving email: {e}")
            return False
