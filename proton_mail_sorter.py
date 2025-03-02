#!/usr/bin/env python3
"""
꧁༒☬ PROTON MAIL FOLDER SORTER ☬༒꧂
------------------------------------
Retrieves emails via IMAP with improved search capabilities,
classifies them using a local LLM, and moves them to appropriate folders.

Now with auto-classification to reduce LLM usage for faster processing.
Added spam review functionality to identify false positives in spam folder.

Run this script to start the email sorting process.
"""

import os
import sys
import argparse
import time
from pathlib import Path

# Import our modules
from modules.display import Display
from modules.config import Config
from modules.imap_client import ImapClient
from modules.llm_client import LlmClient
from modules.history import HistoryManager
from modules.auto_classifier import AutoClassifier
from modules.spam_reviewer import SpamReviewer


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description='Proton Mail Folder Sorter using Local LLM')
    parser.add_argument('--limit', type=int, default=100, 
                        help='Maximum number of emails to process (default: 100)')
    parser.add_argument('--dry-run', action='store_true', 
                        help='Dry run (no folder movement)')
    parser.add_argument('--config', type=str, 
                        help='Path to config file')
    parser.add_argument('--debug', action='store_true', 
                        help='Enable extra debugging output')
    parser.add_argument('--reprocess', action='store_true', 
                        help='Reprocess already processed emails')
    parser.add_argument('--max-history', type=int, default=5000, 
                        help='Maximum history size')
    parser.add_argument('--clear-history', action='store_true', 
                        help='Clear email processing history')
    parser.add_argument('--list-folders', action='store_true', 
                        help='List all available IMAP folders and exit')
    parser.add_argument('--disable-context', action='store_true', 
                        help='Disable personal context')
    parser.add_argument('--disable-auto', action='store_true',
                       help='Disable auto-classification (use LLM for all emails)')
    parser.add_argument('--suggest-rules', action='store_true',
                       help='Suggest new auto-classification rules based on history')
    
    # Add spam review arguments
    parser.add_argument('--review-spam', action='store_true',
                        help='Review Spam folder for false positives')
    parser.add_argument('--confidence-threshold', type=float, default=0.7,
                        help='Confidence threshold for spam reclassification (0.0-1.0)')
    parser.add_argument('--rescue-folder', type=str, default='INBOX',
                        help='Folder to move rescued emails to (default: INBOX)')
    
    return parser.parse_args()


def main():
    """Main function."""
    # Parse command line arguments
    args = parse_args()
    
    # Initialize display module
    display = Display()
    display.banner()
    
    try:
        # Load configuration
        config = Config(display, args.config)
        config_data = config.get()
        
        # Update display settings from config
        display.update_settings(config_data)
        
        # Initialize history manager
        history = HistoryManager(display)
        
        # Clear history if requested
        if args.clear_history:
            history.clear()
            display.success("Cleared email processing history")
        
        # Initialize auto-classifier
        auto_classifier = AutoClassifier(display)
        
        # Handle rule suggestion mode
        if args.suggest_rules:
            display.header("Rule Suggestion Mode")
            # Load a larger set of history
            email_history = history.load_full_history(1000)
            
            if not email_history:
                display.warning("Not enough email history found to suggest rules")
                return 0
                
            display.info(f"Analyzing {len(email_history)} emails for patterns...")
            suggested_rules = auto_classifier.suggest_rules_from_history(email_history)
            
            if not suggested_rules:
                display.warning("No clear patterns found to suggest rules")
                return 0
                
            display.subheader("Suggested Auto-Classification Rules")
            
            # Display suggested rules
            for i, rule in enumerate(suggested_rules[:10], 1):
                confidence_pct = int(rule['confidence'] * 100)
                display.info(f"{i}. {rule['type']}: '{rule['pattern']}' → {rule['category']} " +
                          f"(Confidence: {confidence_pct}%, Occurrences: {rule['occurrences']})")
            
            # Ask if user wants to add any rules
            print("\nWould you like to add any of these rules to your auto-classification?")
            print("Enter rule numbers separated by commas, or 'all' for all, or press Enter to skip: ")
            choice = input("> ").strip().lower()
            
            if choice == 'all':
                # Add all suggested rules
                for rule in suggested_rules:
                    auto_classifier.add_rule(rule['type'], rule['pattern'], rule['category'])
                display.success(f"Added {len(suggested_rules)} new auto-classification rules")
            elif choice:
                # Add selected rules
                try:
                    indices = [int(idx.strip()) - 1 for idx in choice.split(',')]
                    added = 0
                    for idx in indices:
                        if 0 <= idx < len(suggested_rules):
                            rule = suggested_rules[idx]
                            if auto_classifier.add_rule(rule['type'], rule['pattern'], rule['category']):
                                added += 1
                    display.success(f"Added {added} new auto-classification rules")
                except ValueError:
                    display.error("Invalid input. No rules added.")
            
            return 0
        
        # Initialize IMAP client
        imap = ImapClient(config_data, display)
        
        # List folders if requested and exit
        if args.list_folders:
            if imap.connect():
                folders = imap.list_folders()
                display.folder_list(folders)
                imap.disconnect()
            return 0
        
        # Load personal context
        personal_context = []
        if not args.disable_context:
            personal_context = config.load_personal_context()
        
        # Initialize LLM client
        llm = LlmClient(config_data['LLM'], display)
        
        # Check if we're in spam review mode
        if args.review_spam:
            # Initialize spam reviewer
            spam_reviewer = SpamReviewer(config_data, display, imap, llm, history, auto_classifier)
            
            # Update settings from command line arguments
            spam_reviewer.update_settings(args)
            
            # Run the spam review process
            return 1 if spam_reviewer.review(personal_context) > 0 else 0
        
        # Connect to IMAP and get emails
        display.header("Email Retrieval")
        emails = imap.get_emails(args.limit, args.debug)
        
        if len(emails) == 0:
            display.warning("No emails found. Please check your IMAP connection and folder settings.")
            return 1
        
        # Load processed email hashes if not reprocessing
        processed_hashes = set() if args.reprocess else history.load(args.max_history)
        if not args.reprocess and processed_hashes:
            display.info(f"Loaded {len(processed_hashes)} processed email hashes from history")
        
        # Process each email
        display.header("Email Processing")
        processed_count = 0
        auto_classified_count = 0
        llm_classified_count = 0
        
        for i, email in enumerate(emails):
            # Show progress
            display.progress(i + 1, len(emails), "Overall progress")
            
            # Display email information
            display.email_box(email)
            
            # Check if email was already processed
            email_hash = history.get_email_hash(email)
            if not args.reprocess and email_hash in processed_hashes:
                display.info("Email already processed, skipping")
                continue
            
            # Try auto-classification first if not disabled
            auto_category = None
            if not args.disable_auto:
                auto_category = auto_classifier.check_auto_classification(email)
            
            if auto_category:
                display.success(f"Auto-classified as: {auto_category}")
                category = auto_category
                auto_classified_count += 1
            else:
                # Fall back to LLM classification
                display.info("Using LLM for classification...")
                category = llm.classify_email(email, personal_context)
                llm_classified_count += 1
            
            # Map category to folder
            folder_path = config_data['Folders'].get(category, "Folders/Uncategorized")
            
            # Display status
            display.status(category, folder_path)
            
            # Move the email to the target folder
            if not args.dry_run:
                success = imap.move_email(email, folder_path)
                
                if success:
                    display.success(f"Successfully moved email to folder: {folder_path}")
                    history.save(email_hash, args.max_history)
                    # Also save to full history for rule suggestions
                    history.save_full_history(email)
                    processed_count += 1
                    
                    # Add to display history
                    email['category'] = category
                    email['folder'] = folder_path
                    display.add_to_history(email)
                else:
                    display.error(f"Failed to move email to folder: {folder_path}")
            else:
                display.info(f"[DRY RUN] Would move email to folder: {folder_path}")
                history.save(email_hash, args.max_history)
                # Also save to full history for rule suggestions
                history.save_full_history(email)
                processed_count += 1
                
                # Add to display history in dry run mode too
                email['category'] = category
                email['folder'] = folder_path
                display.add_to_history(email)
            
            # Small delay to see the update
            time.sleep(0.5)
        
        # Clean up
        imap.disconnect()
        
        # Show summary
        display.header("Summary")
        display.success(f"Processed {processed_count} out of {len(emails)} emails")
        if processed_count > 0:
            auto_percent = int((auto_classified_count / processed_count) * 100) if processed_count > 0 else 0
            display.info(f"Auto-classified: {auto_classified_count} ({auto_percent}%)")
            display.info(f"LLM-classified: {llm_classified_count}")
            
            # If no auto-classification happened, suggest checking rules
            if auto_classified_count == 0 and not args.disable_auto:
                display.info("Tip: No emails were auto-classified. Use --suggest-rules to create rules from your history.")
        
        # Keep the display visible at the end
        if processed_count > 0:
            input("\nPress Enter to exit...")
        
        return 0
        
    except KeyboardInterrupt:
        display.warning("\nProcess interrupted by user")
        return 130
    except Exception as e:
        display.error(f"Error: {e}")
        if args.debug:
            import traceback
            traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
