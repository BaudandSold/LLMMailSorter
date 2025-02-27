#!/usr/bin/env python3
"""
Thunderbird Email Sorter using Local LLM
----------------------------------------
This script connects to Thunderbird's mail storage, extracts emails,
uses a local LLM to categorize them, and sorts them into folders.
"""

import os
import sys
import json
import time
import sqlite3
import mailbox
import requests
import configparser
import hashlib
import imaplib
import email
from pathlib import Path
from email.parser import BytesParser
from email.policy import default
from io import BytesIO
import argparse

# --- Configuration ---

def get_config():
    """Load configuration or create default if not exists."""
    config = configparser.ConfigParser()
    config_path = Path.home() / '.config' / 'thunderbird_llm_sorter.ini'
    
    if config_path.exists():
        config.read(config_path)
    else:
        # Default configuration
        config['Thunderbird'] = {
            'profile_path': str(Path.home() / '.thunderbird'),
            'profile_name': 'default',  # Usually a random string in practice
            'inbox_folder': 'INBOX',
        }
        config['IMAP'] = {
            'server': '127.0.0.1',
            'port': '143',
            'username': 'your_username',
            'password': 'your_password',
            'use_ssl': 'False',
            'use_starttls': 'True'  # Add STARTTLS option
        }
        config['LLM'] = {
            'api_url': 'http://localhost:1234/v1/chat/completions',
            'system_prompt': 'You are an email classifier. Categorize each email into one of these categories: Work, Personal, Finance, Shopping, Newsletter, Spam, Family, School.',
            'improvement_hints': ''
        }
        config['Categories'] = {
            'Work': 'Work',
            'Personal': 'Personal',
            'Finance': 'Finance',
            'Shopping': 'Shopping', 
            'Newsletter': 'Newsletters',
            'Spam': 'Junk',
            'Family': 'Family',
            'School': 'School'
        }
        
        # Create directory if it doesn't exist
        config_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Write default config
        with open(config_path, 'w') as configfile:
            config.write(configfile)
        
        print(f"Created default configuration at {config_path}")
        print("Please edit this file to match your Thunderbird profile and folder structure.")
    
    return config

# --- IMAP Integration ---

def connect_to_imap(config):
    """Connect to the IMAP server with support for STARTTLS."""
    server = config['IMAP']['server']
    port = int(config['IMAP']['port'])
    username = config['IMAP']['username']
    password = config['IMAP']['password']
    use_ssl = config['IMAP'].getboolean('use_ssl', False)
    use_starttls = config['IMAP'].getboolean('use_starttls', False)
    
    try:
        # Connect to the server
        if use_ssl:
            print(f"Connecting to IMAP server {server}:{port} using SSL")
            imap = imaplib.IMAP4_SSL(server, port)
        else:
            print(f"Connecting to IMAP server {server}:{port} without SSL")
            imap = imaplib.IMAP4(server, port)
            
            # If STARTTLS is enabled, call STARTTLS before logging in
            if use_starttls:
                print("Initiating STARTTLS")
                imap.starttls()
        
        # Login
        print(f"Logging in as {username}")
        imap.login(username, password)
        print(f"Connected to IMAP server {server}")
        return imap
    
    except Exception as e:
        print(f"Error connecting to IMAP server: {e}")
        return None

def get_emails_from_imap(imap, folder='INBOX', limit=10):
    """Fetch emails directly using IMAP protocol with deep search."""
    emails = []
    
    try:
        print(f"Connecting to IMAP folder: {folder}")
        
        # Select the folder
        status, messages = imap.select(folder, readonly=True)
        if status != 'OK':
            print(f"Error selecting folder {folder}: {messages}")
            return emails
        
        # Get message count
        status, data = imap.search(None, 'ALL')
        if status != 'OK':
            print(f"Error searching for messages: {data}")
            return emails
        
        # Convert the result to a list of message IDs
        message_ids = data[0].split()
        total_messages = len(message_ids)
        
        print(f"Found {total_messages} messages in folder {folder}")
        
        # If requesting more messages than exist, adjust the limit
        if limit > total_messages:
            limit = total_messages
        
        # Reverse to get newest messages first
        message_ids = message_ids[::-1]
        
        # Limit the number of messages to process
        message_ids = message_ids[:limit]
        
        print(f"Processing {len(message_ids)} messages from folder {folder}")
        
        # Fetch each message
        processed = 0
        for msg_id in message_ids:
            try:
                status, msg_data = imap.fetch(msg_id, '(RFC822)')
                if status != 'OK':
                    print(f"Error fetching message {msg_id}: {msg_data}")
                    continue
                
                # Parse the email
                msg = email.message_from_bytes(msg_data[0][1])
                
                # Extract email data
                subject = msg.get('Subject', '')
                from_addr = msg.get('From', '')
                date = msg.get('Date', '')
                
                # Get email body
                body = ""
                if msg.is_multipart():
                    for part in msg.walk():
                        if part.get_content_type() == "text/plain":
                            body = part.get_payload(decode=True)
                            if isinstance(body, bytes):
                                body = body.decode('utf-8', errors='replace')
                            break
                else:
                    body = msg.get_payload(decode=True)
                    if isinstance(body, bytes):
                        body = body.decode('utf-8', errors='replace')
                
                emails.append({
                    'key': msg_id.decode('utf-8'),  # Use message ID as the key
                    'subject': subject,
                    'from': from_addr,
                    'date': date,
                    'body': body[:1000] if body else "",  # Truncate body for LLM
                    'folder': folder
                })
                
                processed += 1
                print(f"Fetched email {processed}/{len(message_ids)}: {subject}")
            except Exception as e:
                print(f"Error processing message {msg_id}: {e}")
        
    except Exception as e:
        print(f"Error fetching emails from IMAP: {e}")
    
    return emails

def list_imap_folders(imap):
    """List all available IMAP folders."""
    folders = []
    try:
        status, folder_list = imap.list()
        if status == 'OK':
            for folder_info in folder_list:
                folder_info = folder_info.decode('utf-8')
                # Extract the folder name from the response
                if '"/"' in folder_info:
                    # Format: (FLAGS) "/" FOLDER
                    folder_name = folder_info.split('"/" ')[1].strip('"')
                else:
                    # Format: (FLAGS) FOLDER
                    folder_name = folder_info.split(') ')[1].strip('"')
                folders.append(folder_name)
            print(f"Found {len(folders)} IMAP folders")
        else:
            print(f"Error listing folders: {folder_list}")
    except Exception as e:
        print(f"Error getting folder list: {e}")
    return folders

def move_email_via_imap(imap, email_data, target_folder):
    """Move an email to a different folder using IMAP commands."""
    try:
        # Make sure we're in the right folder
        source_folder = email_data.get('folder', 'INBOX')
        status, _ = imap.select(source_folder)
        if status != 'OK':
            print(f"Error selecting folder {source_folder}")
            return False
        
        # Get the message ID
        msg_id = email_data['key']
        
        # Copy the message to the target folder
        status, data = imap.copy(msg_id, target_folder)
        if status != 'OK':
            print(f"Error copying message to {target_folder}: {data}")
            # Try creating the folder if it doesn't exist
            try:
                imap.create(target_folder)
                # Try the copy again
                status, data = imap.copy(msg_id, target_folder)
                if status != 'OK':
                    print(f"Error copying message after creating folder: {data}")
                    return False
            except Exception as e:
                print(f"Error creating folder {target_folder}: {e}")
                return False
        
        # Mark the original message for deletion
        imap.store(msg_id, '+FLAGS', '\\Deleted')
        
        # Expunge to actually delete
        imap.expunge()
        
        print(f"Successfully moved email to {target_folder}")
        return True
        
    except Exception as e:
        print(f"Error moving email: {e}")
        return False

# --- Thunderbird Integration ---

def find_thunderbird_profile(config):
    """Find the Thunderbird profile path."""
    profile_path = Path(config['Thunderbird']['profile_path'])
    profile_name = config['Thunderbird']['profile_name']
    
    # Handle default case where we need to find the actual profile
    if profile_name == 'default':
        profiles_ini = profile_path / 'profiles.ini'
        if profiles_ini.exists():
            profile_config = configparser.ConfigParser()
            profile_config.read(profiles_ini)
            
            # Get the first profile or the default profile
            for section in profile_config.sections():
                if section.startswith('Profile'):
                    profile_name = profile_config[section]['Path']
                    if profile_config[section].get('Default', '0') == '1':
                        break
    
    full_profile_path = profile_path / profile_name
    
    if not full_profile_path.exists():
        raise FileNotFoundError(f"Thunderbird profile not found at {full_profile_path}")
    
    return full_profile_path

def get_thunderbird_emails(profile_path, inbox_folder, limit=10, skip_processed=False):
    """
    Extract emails from Thunderbird's storage.
    
    Handles both local folders (mbox format) and IMAP folders (maildir-like format).
    
    Args:
        profile_path: Path to Thunderbird profile
        inbox_folder: Name of inbox folder
        limit: Maximum number of emails to return
        skip_processed: Whether to check if emails are already processed
    """
    # Don't apply a limit when extracting the emails - we'll filter later
    # This allows us to skip already processed emails and still get up to 'limit' new ones
    extraction_limit = 1000 if skip_processed else limit
    
    # First, let's check if we're dealing with an IMAP account on 127.0.0.1
    imap_path = profile_path / 'ImapMail' / '127.0.0.1'
    if imap_path.exists():
        print(f"Found IMAP directory for 127.0.0.1")
        # For this specific case, we'll directly use the IMAP directory
        return get_emails_from_imap_dir(imap_path, extraction_limit)
    
    # If not, proceed with the general case
    # Try local folders
    mail_path = profile_path / 'Mail' / 'Local Folders' / inbox_folder
    
    # Then try IMAP folders
    if not mail_path.exists():
        imap_dir = profile_path / 'ImapMail'
        if imap_dir.exists():
            # Look for server directories
            server_dirs = [d for d in imap_dir.iterdir() if d.is_dir()]
            if server_dirs:
                # Use the provided inbox_folder or default to 'INBOX'
                if inbox_folder == 'INBOX':
                    mail_path = server_dirs[0] / inbox_folder
                else:
                    mail_path = server_dirs[0]
    
    if not mail_path.exists():
        raise FileNotFoundError(f"Inbox folder not found at {mail_path}")
    
    # Check if this is an IMAP directory
    if mail_path.is_dir():
        return get_emails_from_imap_dir(mail_path, extraction_limit)
    else:
        # Try as mbox format
        return get_emails_from_mbox(mail_path, extraction_limit)

def get_emails_from_mbox(mail_path, limit=10):
    """Extract emails from an mbox file."""
    emails = []
    
    try:
        # Ensure the path exists and is a file
        if not Path(mail_path).is_file():
            print(f"Not a file: {mail_path}")
            return emails
            
        mbox = mailbox.mbox(str(mail_path))
        parser = BytesParser(policy=default)
        
        count = 0
        for key in mbox.keys():
            if count >= limit:
                break
                
            message = parser.parse(mbox.get_bytes(key))
            
            # Extract email data
            subject = message.get('Subject', '')
            from_addr = message.get('From', '')
            date = message.get('Date', '')
            
            # Get email body
            body = ""
            if message.is_multipart():
                for part in message.iter_parts():
                    if part.get_content_type() == "text/plain":
                        body = part.get_content()
                        break
            else:
                body = message.get_content()
            
            emails.append({
                'key': key,
                'subject': subject,
                'from': from_addr,
                'date': date,
                'body': body[:1000]  # Truncate body for LLM
            })
            
            count += 1
        
        print(f"Read {count} emails from mbox file {mail_path}")
    
    except Exception as e:
        print(f"Error reading mbox file {mail_path}: {e}")
    
    return emails

def get_emails_from_imap_dir(mail_path, limit=10):
    """Extract emails from an IMAP directory structure."""
    emails = []
    count = 0
    
    print(f"Searching for emails in IMAP directory: {mail_path}")
    
    # For Thunderbird IMAP format, we need to check several possible locations
    
    # Check for maildir-style storage (most common in newer Thunderbird versions)
    # This typically has cur, new, and tmp directories
    maildir_paths = []
    
    # Check if INBOX is a directory containing a maildir structure
    inbox_dir = mail_path / 'INBOX'
    if inbox_dir.exists() and inbox_dir.is_dir():
        # Look for Maildir structure
        if (inbox_dir / 'cur').exists():
            maildir_paths.append(inbox_dir / 'cur')
        if (inbox_dir / 'new').exists():
            maildir_paths.append(inbox_dir / 'new')
    
    # Also check if there's a maildir structure directly in the mail path
    if (mail_path / 'cur').exists():
        maildir_paths.append(mail_path / 'cur')
    if (mail_path / 'new').exists():
        maildir_paths.append(mail_path / 'new')
    
    # If we found maildir paths, process them
    if maildir_paths:
        print(f"Found Maildir structure, checking: {maildir_paths}")
        
        email_files = []
        for dir_path in maildir_paths:
            email_files.extend([f for f in dir_path.glob('*') if f.is_file()])
        
        print(f"Found {len(email_files)} email files in Maildir structure")
    else:
        # No maildir structure found, fall back to looking for individual message files
        email_files = []
        
        # Look for files directly in the INBOX directory
        if inbox_dir.exists() and inbox_dir.is_dir():
            email_files.extend([f for f in inbox_dir.glob('*') if f.is_file() and not f.name.endswith('.msf')])
        
        # Look for files directly in the mail path
        email_files.extend([f for f in mail_path.glob('*') if f.is_file() and not f.name.endswith('.msf')])
        
        # If we found any MSF files, look for the corresponding email files
        msf_files = list(mail_path.glob('*.msf'))
        for msf_file in msf_files:
            # The email file typically has the same name without the .msf extension
            email_file = mail_path / msf_file.name[:-4]
            if email_file.exists() and email_file.is_file():
                email_files.append(email_file)
        
        print(f"Found {len(email_files)} potential email files in standard structure")
        
    # Process the email files
    parser = BytesParser(policy=default)
    
    # Use a set to track already processed file paths in this run
    processed_file_paths = set()
    
    for file_path in email_files:
        if count >= limit:
            break
            
        # Skip if we've already processed this file in this run
        file_path_str = str(file_path)
        if file_path_str in processed_file_paths:
            continue
            
        processed_file_paths.add(file_path_str)
            
        try:
            # Check if the file is empty
            if file_path.stat().st_size == 0:
                print(f"Skipping empty file: {file_path}")
                continue
                
            with open(file_path, 'rb') as f:
                raw_data = f.read()
            
            # Skip non-email files
            if not raw_data.startswith(b'From ') and not raw_data.startswith(b'Return-Path:') and not raw_data.startswith(b'Received:'):
                if not any(header in raw_data for header in [b'Subject:', b'From:', b'To:', b'Date:']):
                    print(f"Skipping non-email file: {file_path}")
                    continue
            
            # Parse the email
            message = parser.parse(BytesIO(raw_data))
            
            # Extract email data
            subject = message.get('Subject', '')
            from_addr = message.get('From', '')
            date = message.get('Date', '')
            
            # Get email body
            body = ""
            if message.is_multipart():
                for part in message.iter_parts():
                    if part.get_content_type() == "text/plain":
                        body = part.get_content()
                        break
            else:
                try:
                    body = message.get_content()
                except:
                    body = "Could not extract email body"
            
            emails.append({
                'key': str(file_path),  # Use file path as the key
                'subject': subject,
                'from': from_addr,
                'date': date,
                'body': body[:1000] if isinstance(body, str) else str(body)[:1000]  # Truncate body for LLM
            })
            
            count += 1
            print(f"Successfully read email: {subject}")
            
        except Exception as e:
            print(f"Error reading email file {file_path}: {e}")
    
    print(f"Successfully processed {count} email files")
    
    return emails

def move_email_to_folder(profile_path, email_key, source_folder, target_folder):
    """
    Move an email using Thunderbird's command-line interface with proper folder path detection.
    """
    try:
        print(f"\nMoving email to: {target_folder}")
        
        # Based on your folder structure
        direct_folders = ["Junk", "INBOX", "Trash", "Sent", "Drafts", "Archive", "Starred", "Templates", "All Mail", "Spam"]
        sbd_folders = ["Work", "Personal", "Finance", "Shopping", "Newsletter", "Newsletters", "Family", "School"]
        
        # Determine the correct folder path based on your structure
        if target_folder in sbd_folders:
            # Folders inside Folders.sbd need the "Folders/" prefix
            full_target_folder = f"Folders/{target_folder}"
        else:
            # Direct folders don't need a prefix
            full_target_folder = target_folder
            
        print(f"Using folder path: {full_target_folder}")
        
        # Try to find thunderbird executable
        thunderbird_cmd = "thunderbird"  # Default
        
        # Check common locations
        possible_paths = [
            "/usr/bin/thunderbird",
            "/usr/local/bin/thunderbird",
            "/snap/bin/thunderbird",
            "/Applications/Thunderbird.app/Contents/MacOS/thunderbird"  # For macOS
        ]
        
        thunderbird_found = False
        for path in possible_paths:
            if os.path.exists(path):
                thunderbird_cmd = path
                thunderbird_found = True
                print(f"Found Thunderbird executable at: {path}")
                break
        
        if not thunderbird_found:
            print("Thunderbird executable not found in common locations")
            print("Will try with default 'thunderbird' command")
        
        # Use the file parameter approach that worked in previous debugging
        cmd = [
            thunderbird_cmd,
            "-mail-action", "move", 
            "-file", str(email_key), 
            "-folder", full_target_folder
        ]
        
        print(f"Running command: {' '.join(cmd)}")
        
        # Run the command
        import subprocess
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        print(f"Return code: {result.returncode}")
        if result.stdout:
            print(f"Command stdout: {result.stdout}")
        if result.stderr:
            print(f"Command stderr: {result.stderr}")
        
        if result.returncode == 0:
            print(f"Successfully moved email to {full_target_folder}")
            
            # Check if Thunderbird needs to be refreshed
            print("\nNOTE: If the email doesn't appear to be moved in Thunderbird's UI,")
            print("try refreshing the folder by clicking on it or restarting Thunderbird.")
            
            return True
        else:
            print(f"Failed to move email to {full_target_folder}")
            
            # If the first attempt failed, try with a different approach
            # Try with -message-id parameter
            print("\nTrying alternative approach with -message-id parameter...")
            cmd2 = [
                thunderbird_cmd,
                "-mail-action", "move", 
                "-message-id", str(email_key), 
                "-folder", full_target_folder
            ]
            
            print(f"Running command: {' '.join(cmd2)}")
            result2 = subprocess.run(cmd2, capture_output=True, text=True)
            
            if result2.returncode == 0:
                print(f"Successfully moved email using message-id parameter")
                return True
                
            # Print folder structure for debugging
            print("\nChecking folder existence in profile...")
            try:
                # Check ImapMail directory 
                imap_dir = profile_path / "ImapMail"
                if imap_dir.exists():
                    print(f"ImapMail directory exists: {imap_dir}")
                    for d in imap_dir.iterdir():
                        if d.is_dir():
                            print(f"Found IMAP server directory: {d}")
                            
                            # Look for folders.sbd directory
                            folders_sbd = d / "Folders.sbd"
                            if folders_sbd.exists():
                                print(f"Found Folders.sbd directory: {folders_sbd}")
                                for f in folders_sbd.iterdir():
                                    print(f"Found item in Folders.sbd: {f}")
            except Exception as e:
                print(f"Error checking folder structure: {e}")
            
            return False
    
    except Exception as e:
        print(f"Exception in move_email_to_folder: {e}")
        import traceback
        traceback.print_exc()
        return False

# --- LLM Integration ---

def classify_email_with_llm(email, llm_config):
    """Send email content to the local LLM for classification."""
    api_url = llm_config['api_url']
    system_prompt = llm_config['system_prompt']
    
    # Add any improvement hints from feedback
    if 'improvement_hints' in llm_config and llm_config['improvement_hints']:
        system_prompt = f"{system_prompt}\n\nImprovement guidance based on past corrections:\n{llm_config['improvement_hints']}"
    
    # Prepare email content for the LLM
    email_content = f"""
Subject: {email['subject']}
From: {email['from']}
Date: {email['date']}

{email['body']}
"""
    
    # Add more context to help with classification
    user_prompt = """Please categorize this email into exactly one of these categories: Work, Personal, Finance, Shopping, Newsletter, Spam, Family, School.

Be especially careful about categorizing as Spam - only use this category for unsolicited commercial messages, scams, or true junk mail.
Newsletters should be categorized as Newsletter, not as Spam.
Academic communications should be categorized as School.
Family-related emails (including those about children's activities, family medical appointments, etc.) should be categorized as Family.

Email to categorize:
"""
    
    # Prepare the request to the LLM
    payload = {
        "model": "local-model",  # This is typically ignored by LM Studio
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"{user_prompt}\n\n{email_content}"}
        ],
        "temperature": 0.1,  # Low temperature for more deterministic results
        "max_tokens": 50  # We only need a short response
    }
    
    try:
        response = requests.post(api_url, json=payload)
        response.raise_for_status()
        
        result = response.json()
        if 'choices' in result and len(result['choices']) > 0:
            category = result['choices'][0]['message']['content'].strip()
            
            # Extract just the category name if the LLM returns additional text
            valid_categories = ['Work', 'Personal', 'Finance', 'Shopping', 'Newsletter', 'Spam', 'Family', 'School']
            for valid_category in valid_categories:
                if valid_category.lower() in category.lower():
                    return valid_category
            
            # If no valid category found in response
            print(f"LLM response didn't contain a valid category: {category}")
            return "Uncategorized"
        else:
            print(f"Unexpected LLM response structure: {result}")
            return "Uncategorized"
        
    except Exception as e:
        print(f"Error calling LLM API: {e}")
        return "Error"

def move_email_via_direct_imap(config, email_data, source_folder, target_folder, dry_run=False):
    """
    Move an email using direct IMAP protocol commands rather than Thunderbird CLI.
    
    Args:
        config: Configuration containing IMAP settings
        email_data: Email data dictionary containing subject, from, date, etc.
        source_folder: Source folder name
        target_folder: Target folder name
        dry_run: If True, simulate but don't actually move
        
    Returns:
        bool: True if successful, False otherwise
    """
    if dry_run:
        print(f"[DRY RUN] Would move email from {source_folder} to {target_folder} via IMAP")
        return True
        
    try:
        subject = email_data.get('subject', '')
        from_addr = email_data.get('from', '')
        date = email_data.get('date', '')
        
        print(f"\nMoving email via direct IMAP from {source_folder} to {target_folder}")
        print(f"Email details: Subject: '{subject}', From: '{from_addr}', Date: '{date}'")
        
        # Connect to IMAP server
        imap = connect_to_imap(config)
        if not imap:
            print("Failed to connect to IMAP server")
            return False
        
        # Convert the folder names to proper IMAP paths if needed
        sbd_folders = ["Work", "Personal", "Finance", "Shopping", "Newsletter", "Newsletters", "Family", "School"]
        
        # Handle target folder path
        if target_folder in sbd_folders:
            # These folders are under Folders.sbd
            imap_target = f"Folders/{target_folder}"
        else:
            # Direct folders
            imap_target = target_folder
            
        print(f"Using IMAP target folder: {imap_target}")
        
        # Select the source folder
        print(f"Selecting source folder: {source_folder}")
        status, messages = imap.select(source_folder)
        if status != 'OK':
            print(f"Error selecting source folder {source_folder}: {messages}")
            return False
        
        # Using a simpler and safer approach for searching
        print("Searching for the email...")
        
        # Try different search strategies in order of specificity
        search_methods = [
            # Method 1: Try using header references if available
            lambda: imap.search(None, 'ALL'),
            
            # Method 2: Try a search by subject only (simplified)
            # Remove any encoded parts or special characters
            lambda: imap.search(None, f'SUBJECT "{subject.split("=?")[0]}"') if '=?' in subject else imap.search(None, f'SUBJECT "{subject.split(":")[0]}"') if ':' in subject else imap.search(None, f'SUBJECT "{subject}"')
        ]
        
        message_ids = []
        search_success = False
        
        for search_method in search_methods:
            try:
                print(f"Trying search method...")
                status, data = search_method()
                
                if status == 'OK' and data[0]:
                    message_ids = data[0].split()
                    if message_ids:
                        search_success = True
                        print(f"Found {len(message_ids)} matching messages")
                        break
            except Exception as e:
                print(f"Search method failed: {e}")
                continue
        
        if not search_success or not message_ids:
            print("Failed to find matching emails")
            imap.close()
            imap.logout()
            return False
        
        # Process all found messages (typically just one if search was specific)
        for msg_id in message_ids[:1]:  # Just take the first one for now
            try:
                print(f"Processing message ID: {msg_id}")
                
                # Verify this is the right message by fetching headers
                status, data = imap.fetch(msg_id, '(BODY.PEEK[HEADER.FIELDS (SUBJECT FROM DATE)])')
                if status == 'OK':
                    header_data = data[0][1].decode('utf-8', errors='replace')
                    print(f"Verified message headers:\n{header_data}")
                
                # Copy the message to the target folder
                print(f"Copying message to {imap_target}")
                status, data = imap.copy(msg_id, imap_target)
                if status != 'OK':
                    print(f"Error copying message to {imap_target}: {data}")
                    
                    # Try to create the folder if it doesn't exist
                    try:
                        print(f"Attempting to create folder: {imap_target}")
                        imap.create(imap_target)
                        
                        # Try the copy again
                        status, data = imap.copy(msg_id, imap_target)
                        if status != 'OK':
                            print(f"Error copying message after creating folder: {data}")
                            continue
                    except Exception as e:
                        print(f"Error creating folder {imap_target}: {e}")
                        continue
                
                # Mark the original message for deletion
                print("Marking original message for deletion")
                imap.store(msg_id, '+FLAGS', '\\Deleted')
                
                # Expunge to actually delete
                print("Expunging deleted messages")
                imap.expunge()
                
                print(f"Successfully moved email via IMAP to {imap_target}")
                imap.close()
                imap.logout()
                return True
                
            except Exception as e:
                print(f"Error processing message {msg_id}: {e}")
        
        print("Failed to move any messages")
        imap.close()
        imap.logout()
        return False
        
    except Exception as e:
        print(f"Error moving email via IMAP: {e}")
        import traceback
        traceback.print_exc()
        return False

# --- LLM Feedback System ---

def save_feedback(email_hash, original_category, corrected_category):
    """Save feedback about an incorrect classification."""
    feedback_file = Path.home() / '.config' / 'thunderbird_llm_sorter_feedback.jsonl'
    
    # Create directory if it doesn't exist
    feedback_file.parent.mkdir(parents=True, exist_ok=True)
    
    feedback_entry = {
        'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
        'email_hash': email_hash,
        'original_category': original_category,
        'corrected_category': corrected_category
    }
    
    try:
        with open(feedback_file, 'a') as f:
            f.write(json.dumps(feedback_entry) + '\n')
        print(f"Feedback saved: {original_category} → {corrected_category}")
        return True
    except Exception as e:
        print(f"Error saving feedback: {e}")
        return False

def get_feedback_prompt():
    """Get an improved system prompt based on collected feedback."""
    feedback_file = Path.home() / '.config' / 'thunderbird_llm_sorter_feedback.jsonl'
    
    if not feedback_file.exists():
        return None
        
    try:
        # Read all feedback entries
        feedback = []
        with open(feedback_file, 'r') as f:
            for line in f:
                if line.strip():
                    feedback.append(json.loads(line))
        
        # Count corrections by category
        corrections = {}
        for entry in feedback:
            orig = entry['original_category']
            corr = entry['corrected_category']
            
            if orig not in corrections:
                corrections[orig] = {}
            
            if corr not in corrections[orig]:
                corrections[orig][corr] = 0
                
            corrections[orig][corr] += 1
        
        # If we have enough feedback, generate improvement hints
        if len(feedback) >= 5:
            hints = []
            
            for orig_cat, corrections_dict in corrections.items():
                for corr_cat, count in corrections_dict.items():
                    if count >= 2:  # Only include patterns with at least 2 occurrences
                        hints.append(f"Be careful not to classify emails as '{orig_cat}' when they should be '{corr_cat}'.")
            
            if hints:
                return "\n".join(hints)
    
    except Exception as e:
        print(f"Error processing feedback: {e}")
    
    return None

def interactive_feedback_mode(emails_processed):
    """Run an interactive session to collect feedback on classifications."""
    print("\n==== Feedback Mode ====")
    print("Let's review the classifications to improve future accuracy.")
    print("For each email, indicate if the classification was correct or provide the correct category.")
    
    valid_categories = ['Work', 'Personal', 'Finance', 'Shopping', 'Newsletter', 'Spam', 'Family', 'School', 'Uncategorized']
    
    for i, email_data in enumerate(emails_processed):
        print(f"\n{i+1}. Subject: {email_data['subject']}")
        print(f"   From: {email_data['from']}")
        print(f"   Classified as: {email_data['category']}")
        
        while True:
            response = input("Is this correct? (y/n or type the correct category): ").strip()
            
            if response.lower() in ['y', 'yes']:
                # Classification was correct
                break
                
            elif response.lower() in ['n', 'no']:
                # Classification was incorrect, ask for correct category
                print("Please provide the correct category from the following options:")
                print(", ".join(valid_categories))
                
                correct_cat = input("Correct category: ").strip()
                if correct_cat in valid_categories:
                    save_feedback(email_data['hash'], email_data['category'], correct_cat)
                    break
                else:
                    print(f"Invalid category. Please choose from: {', '.join(valid_categories)}")
                    
            elif response in valid_categories:
                # User provided the correct category directly
                save_feedback(email_data['hash'], email_data['category'], response)
                break
                
            else:
                print(f"Invalid response. Please enter 'y', 'n', or one of: {', '.join(valid_categories)}")
    
    print("\nThank you for your feedback! This will help improve future classifications.")
    
    # Check if we have enough feedback to improve the prompt
    feedback_prompt = get_feedback_prompt()
    if feedback_prompt:
        print("\nBased on your feedback, the system will now be more careful about certain classifications.")
        print("You can add this guidance to your config file under [LLM]['improvement_hints']")
        print("\nSuggested improvement hints:")
        print(feedback_prompt)

# --- Email Tracking System ---

def get_email_hash(email_data):
    """Create a unique hash for an email to track if it's been processed."""
    # Combine key identifying fields for the hash
    hash_input = f"{email_data['subject']}|{email_data['from']}|{email_data['date']}"
    return hashlib.sha256(hash_input.encode()).hexdigest()

def load_processed_emails(max_history=50000):
    """
    Load the set of already processed email hashes.
    Limits the size of the history to prevent unbounded growth.
    
    Args:
        max_history: Maximum number of email hashes to keep in history
    """
    history_file = Path.home() / '.config' / 'thunderbird_llm_sorter_history.json'
    
    if history_file.exists():
        try:
            with open(history_file, 'r') as f:
                history = json.load(f)
                
            # If history is too large, trim it to the most recent entries
            if len(history) > max_history:
                print(f"Trimming email history from {len(history)} to {max_history} entries")
                history = history[-max_history:]
                
                # Save the trimmed history
                with open(history_file, 'w') as f:
                    json.dump(history, f)
                    
            return set(history)
        except Exception as e:
            print(f"Error loading email history: {e}")
            return set()
    else:
        return set()

def save_processed_email(email_hash, max_history=50000):
    """
    Save an email hash to the processed list.
    
    Args:
        email_hash: Hash of the processed email
        max_history: Maximum number of email hashes to keep in history
    """
    history_file = Path.home() / '.config' / 'thunderbird_llm_sorter_history.json'
    
    # Create directory if it doesn't exist
    history_file.parent.mkdir(parents=True, exist_ok=True)
    
    processed_emails = load_processed_emails(max_history)
    processed_emails.add(email_hash)
    
    try:
        with open(history_file, 'w') as f:
            # Convert set to a list for JSON serialization
            # Use sorted to ensure deterministic output
            json.dump(list(processed_emails)[-max_history:], f)
    except Exception as e:
        print(f"Error saving email history: {e}")

def filter_unprocessed_emails(emails, args):
    """Filter out already processed emails unless --reprocess flag is used."""
    if args.reprocess:
        print("Reprocessing all emails regardless of history")
        return emails
    
    processed_hashes = load_processed_emails(args.max_history)
    unprocessed_emails = []
    
    for email in emails:
        email_hash = get_email_hash(email)
        if email_hash not in processed_hashes:
            # Add the hash to the email data for later reference
            email['hash'] = email_hash
            unprocessed_emails.append(email)
    
    print(f"Found {len(emails)} emails, {len(unprocessed_emails)} are new")
    return unprocessed_emails

# --- Main Function ---

def main():
    parser = argparse.ArgumentParser(description='Thunderbird Email Sorter using Local LLM')
    parser.add_argument('--limit', type=int, default=10, help='Maximum number of emails to process')
    parser.add_argument('--dry-run', action='store_true', help='Dry run (no emails will be moved)')
    parser.add_argument('--config', type=str, help='Path to config file')
    parser.add_argument('--reprocess', action='store_true', help='Reprocess already processed emails')
    parser.add_argument('--max-history', type=int, default=50000, 
                        help='Maximum number of email hashes to keep in history (default: 50000)')
    parser.add_argument('--scan-all', action='store_true',
                        help='Scan all emails to find unprocessed ones (slower but more thorough)')
    parser.add_argument('--feedback', action='store_true',
                        help='Enter feedback mode after processing emails')
    parser.add_argument('--feedback-only', action='store_true',
                        help='Skip processing emails and only collect feedback on recent classifications')
    parser.add_argument('--use-thunderbird', action='store_true',
                        help='Use Thunderbird itself to move emails (not recommended)')
    parser.add_argument('--debug', action='store_true',
                        help='Enable extra debugging output')
    parser.add_argument('--use-imap', action='store_true',
                        help='Use direct IMAP commands instead of Thunderbird CLI (recommended)')
    parser.add_argument('--all-folders', action='store_true',
                        help='Process emails from all IMAP folders, not just INBOX')
    parser.add_argument('--force', action='store_true',
                        help='Force processing of emails even if they appear to be in history')
    parser.add_argument('--clear-history', action='store_true',
                        help='Clear email processing history before starting')
    args = parser.parse_args()
    
    try:
        # Clear history if requested
        if args.clear_history:
            history_file = Path.home() / '.config' / 'thunderbird_llm_sorter_history.json'
            if history_file.exists():
                print(f"Clearing email processing history at {history_file}")
                with open(history_file, 'w') as f:
                    json.dump([], f)
        
        # Load configuration
        config = get_config()
        if args.config:
            config.read(args.config)
        
        # Handle feedback-only mode
        if args.feedback_only:
            # This is a placeholder for the actual implementation
            print("Feedback-only mode is not yet implemented.")
            # Future improvement: Load recent classifications and run interactive_feedback_mode()
            return 0
        
        # Get Thunderbird profile
        profile_path = find_thunderbird_profile(config)
        inbox_folder = config['Thunderbird']['inbox_folder']
        
        print(f"Using Thunderbird profile at: {profile_path}")
        
        # Force reprocessing if requested
        if args.force:
            args.reprocess = True
        
        # If we're not reprocessing emails, we need to potentially scan more emails
        # to find enough unprocessed ones
        scan_many = not args.reprocess

        # Process emails in batches until we reach the limit
        processed_count = 0
        batch_size = min(args.limit, 100)  # Process in reasonable batches
        
        # Load processed email hashes once
        processed_hashes = set() if args.reprocess else load_processed_emails(args.max_history)
        print(f"Loaded {len(processed_hashes)} processed email hashes from history")
        
        # Scan limit increases if we're looking for unprocessed emails
        scan_limit = 500 if (scan_many or args.scan_all) else args.limit
        
        all_emails = []
        
        # For IMAP accounts
        if 'ImapMail/127.0.0.1' in str(profile_path) or args.use_imap:
            print("Using IMAP connection to fetch emails")
            # Connect to IMAP
            imap = connect_to_imap(config)
            if imap:
                # If we should check all folders
                if args.all_folders:
                    print("Checking all IMAP folders")
                    folders = list_imap_folders(imap)
                    
                    # Process each folder
                    for folder in folders:
                        # Skip folders that aren't mailboxes
                        if folder.startswith("[Gmail]/") or folder == "Outbox" or folder == "[Gmail]":
                            continue
                            
                        print(f"\nProcessing folder: {folder}")
                        folder_emails = get_emails_from_imap(imap, folder, limit=scan_limit)
                        
                        # Add folder name to each email
                        for email in folder_emails:
                            email['folder'] = folder
                            
                        all_emails.extend(folder_emails)
                        
                        # If we've found enough emails, stop
                        if len(all_emails) >= scan_limit:
                            break
                else:
                    # Just check INBOX
                    all_emails = get_emails_from_imap(imap, inbox_folder, limit=scan_limit)
                
                imap.logout()
                print(f"Found a total of {len(all_emails)} emails across all folders")
            else:
                print("Failed to connect to IMAP server, falling back to file-based approach")
                all_emails = get_thunderbird_emails(profile_path, inbox_folder, limit=scan_limit)
        else:
            # Regular case - file-based approach
            all_emails = get_thunderbird_emails(profile_path, inbox_folder, limit=scan_limit)
        
        # Filter to find unprocessed emails
        emails_to_process = []
        for email in all_emails:
            # Skip if we've already found enough emails to process
            if len(emails_to_process) >= args.limit:
                break
                
            # If reprocessing or force, include all emails
            if args.reprocess or args.force:
                email['hash'] = get_email_hash(email)
                emails_to_process.append(email)
                continue
                
            # Otherwise, check if it's been processed before
            email_hash = get_email_hash(email)
            if email_hash not in processed_hashes:
                email['hash'] = email_hash
                emails_to_process.append(email)
        
        print(f"Found {len(all_emails)} emails total")
        print(f"Selected {len(emails_to_process)} emails to process")
        
        # Keep track of processed emails for feedback
        emails_processed = []
        
        # Process each selected email
        for email in emails_to_process:
            print(f"\nProcessing email: {email['subject']}")
            print(f"From: {email['from']}")
            print(f"Date: {email['date']}")
            source_folder = email.get('folder', inbox_folder)
            print(f"Source folder: {source_folder}")
            
            # Classify email
            category = classify_email_with_llm(email, config['LLM'])
            print(f"Classified as: {category}")
            
            # Store the classification for feedback
            email['category'] = category
            emails_processed.append(email)
            
            # Get target folder for this category
            if category in config['Categories']:
                target_folder = config['Categories'][category]
            else:
                target_folder = "Uncategorized"
            
            # Move email to target folder
            if not args.dry_run:
                if args.use_imap or not args.use_thunderbird:
                    # Use direct IMAP commands (recommended)
                    success = move_email_via_direct_imap(
                        config,
                        email,  # Pass the entire email dictionary
                        source_folder,  # Use the source folder from the email
                        target_folder,
                        args.dry_run
                    )
                else:
                    # Use Thunderbird CLI approach (less reliable)
                    success = move_email_to_folder(
                        profile_path, 
                        email['key'], 
                        source_folder,  # Use the source folder from the email
                        target_folder
                    )
                    
                if success:
                    print(f"Moved to: {target_folder}")
                    # Record this email as processed
                    save_processed_email(email['hash'], args.max_history)
                else:
                    print("Failed to move email")
                    print("You may need to manually move this email or try a different approach")
            else:
                print(f"[DRY RUN] Would move from {source_folder} to {target_folder}")
                # In dry run, still record as processed for testing purposes
                if 'hash' in email:
                    save_processed_email(email['hash'], args.max_history)
        
        if len(emails_to_process) == 0:
            print("\nNo new emails to process. Try using --all-folders, --scan-all, --force, or --reprocess to find more emails.")
        
        # Handle feedback mode if requested
        if args.feedback and emails_processed:
            interactive_feedback_mode(emails_processed)
        
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0

if __name__ == "__main__":
    sys.exit(main())
