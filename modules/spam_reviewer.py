"""
Spam Reviewer module - Analyzes emails in Spam folder for false positives.

This module is responsible for:
- Retrieving emails from the Spam folder
- Evaluating whether emails are legitimate or actual spam
- Moving legitimate emails to appropriate folders
- Providing detailed reporting on rescued emails
"""

import time
import datetime

class SpamReviewer:
    """Handles spam review operations to identify false positives."""
    
    def __init__(self, config_data, display, imap, llm, history, auto_classifier):
        """Initialize with required components."""
        self.config = config_data
        self.display = display
        self.imap = imap
        self.llm = llm
        self.history = history
        self.auto_classifier = auto_classifier
        
        # Default settings
        self.confidence_threshold = 0.7
        self.spam_folder = "Spam"  # Default Proton Mail spam folder name
        self.rescue_folder = ""  # Default is empty - use categorization
        self.dry_run = False
        self.debug = False
        self.limit = 100
    
    def update_settings(self, args):
        """Update settings from command line arguments."""
        if hasattr(args, 'confidence_threshold') and args.confidence_threshold is not None:
            self.confidence_threshold = args.confidence_threshold
        
        if hasattr(args, 'rescue_folder') and args.rescue_folder:
            self.rescue_folder = args.rescue_folder
            
        if hasattr(args, 'dry_run'):
            self.dry_run = args.dry_run
            
        if hasattr(args, 'debug'):
            self.debug = args.debug
            
        if hasattr(args, 'limit') and args.limit is not None:
            self.limit = args.limit
    
    def _get_enhanced_llm(self, personal_context):
        """Create an LLM instance with enhanced spam review prompt."""
        # Enhanced system prompt specifically for spam review
        spam_review_prompt = """
You are an email classifier focusing on identifying false positives in spam detection.
Review each email carefully to determine if it's legitimate or actual spam.

Categorize each email into one of these categories:
1. Work - Work-related communications
2. Personal - Personal communications from actual contacts
3. Finance - Banking, investments, bills, receipts
4. Shopping - Order confirmations, shipping notices, product info
5. Newsletter - Subscribed newsletters and updates
6. Spam - Actual spam, scams, unsolicited marketing
7. Family - Communications from family members
8. School - Educational communications

IMPORTANT: Be very careful when classifying. If there's ANY indication the email is from a 
legitimate sender that the user might want to see, do NOT classify as Spam.
Consider the sender domain, writing style, and content. Many legitimate marketing emails
and newsletters are incorrectly flagged as spam.
"""
        # Create a copy of the LLM config with enhanced prompt
        from modules.llm_client import LlmClient
        
        spam_llm_config = dict(self.config['LLM'])
        spam_llm_config['system_prompt'] = spam_review_prompt
        
        # Return a new LLM instance
        return LlmClient(spam_llm_config, self.display)
    
    def _estimate_time_remaining(self, processed, total, elapsed_time):
        """
        Estimate the time remaining based on processed items and elapsed time.
        
        Args:
            processed: Number of items processed so far
            total: Total number of items to process
            elapsed_time: Time elapsed so far in seconds
            
        Returns:
            Formatted string with the time estimate
        """
        if processed == 0:
            return "Calculating..."
        
        items_per_second = processed / elapsed_time
        remaining_items = total - processed
        
        if items_per_second > 0:
            seconds_remaining = remaining_items / items_per_second
            
            # Format the remaining time
            if seconds_remaining < 60:
                return f"~{int(seconds_remaining)} seconds remaining"
            elif seconds_remaining < 3600:
                return f"~{int(seconds_remaining / 60)} minutes remaining"
            else:
                hours = int(seconds_remaining / 3600)
                minutes = int((seconds_remaining % 3600) / 60)
                return f"~{hours}h {minutes}m remaining"
        else:
            return "Calculating..."
    
    def review(self, personal_context=None):
        """Review the Spam folder for false positives."""
        self.display.header("Spam Review Mode")
        self.display.info(f"Reviewing {self.spam_folder} folder with confidence threshold: {self.confidence_threshold}")
        
        # Indicate if we're using binary classification mode
        if self.rescue_folder:
            self.display.info(f"Using binary classification mode (Spam/Not Spam) with rescue folder: {self.rescue_folder}")
        
        # Connect to IMAP and get emails from Spam folder only
        emails = self.imap.get_emails_from_folder(self.spam_folder, self.limit, self.debug)
        
        if len(emails) == 0:
            self.display.warning(f"No emails found in {self.spam_folder}. Nothing to review.")
            return 0
        
        self.display.success(f"Found {len(emails)} emails in {self.spam_folder} to review")
        
        # Get enhanced LLM for spam review
        spam_llm = self._get_enhanced_llm(personal_context)
        
        # Process each email
        self.display.header("Spam Review Processing")
        rescued_count = 0
        confirmed_spam_count = 0
        
        # Add timing variables
        start_time = time.time()
        last_update_time = start_time
        update_interval = 2  # Update time estimate every 2 seconds (reduced from 5)
        
        for i, email in enumerate(emails):
            # Calculate elapsed time and estimate
            current_time = time.time()
            elapsed = current_time - start_time
            
            # Show progress with time estimate - BEFORE email display to prevent overwriting
            if current_time - last_update_time > update_interval or i == 0 or i == len(emails) - 1:
                time_estimate = self._estimate_time_remaining(i, len(emails), elapsed)
                last_update_time = current_time
                
                # Show progress with time estimate
                progress_msg = f"Spam review progress - {time_estimate}"
                self.display.progress(i + 1, len(emails), progress_msg)
                
                # Small pause to ensure progress bar is visible
                time.sleep(0.2)
            else:
                # Regular progress update without time estimate
                self.display.progress(i + 1, len(emails), "Spam review progress")
            
            # Adding a newline after progress to separate from email display
            print()
            
            # Display email information AFTER progress bar
            self.display.email_box(email)
            
            # Try auto-classification first if auto-classifier is available
            auto_category = None
            auto_confidence = 0.0
            
            if self.auto_classifier:
                # Check with regular auto-classification first
                auto_category = self.auto_classifier.check_auto_classification(email)
                
                # If auto-classified as something other than Spam, it's a strong signal
                if auto_category and auto_category != "Spam":
                    auto_confidence = 0.9  # High confidence for auto-classified non-spam
            
            # If no auto-classification or it's classified as Spam, use LLM
            if not auto_category or auto_category == "Spam":
                # Use the enhanced spam review LLM
                category = spam_llm.classify_email(email, personal_context)
                confidence = 0.7  # Base confidence for LLM classification
            else:
                category = auto_category
                confidence = auto_confidence
            
            # Determine if it's spam or should be rescued
            is_spam = category == "Spam"
            
            if is_spam:
                self.display.info(f"Confirmed as Spam (confidence: {confidence:.2f})")
                confirmed_spam_count += 1
                # No action needed, it's already in Spam folder
            else:
                # If confidence exceeds threshold, rescue the email
                if confidence >= self.confidence_threshold:
                    # If rescue folder is specified, use a binary classification approach
                    if self.rescue_folder:
                        self.display.success(f"Potential false positive! Rescuing to folder: {self.rescue_folder}")
                        target_folder = self.rescue_folder
                        # Simple status for binary classification
                        self.display.status("Not Spam", target_folder)
                    else:
                        # Only use detailed categorization if no rescue folder is specified
                        self.display.success(f"Potential false positive! Classified as: {category} (confidence: {confidence:.2f})")
                        # Map category to folder
                        target_folder = self.config['Folders'].get(category, "INBOX")
                        self.display.status(category, target_folder)
                    
                    # Move the email to the target folder
                    if not self.dry_run:
                        success = self.imap.move_email(email, target_folder)
                        
                        if success:
                            self.display.success(f"Rescued email to folder: {target_folder}")
                            rescued_count += 1
                            
                            # Save to history
                            email_hash = self.history.get_email_hash(email)
                            self.history.save(email_hash)
                            
                            # Also save to full history for rule suggestions
                            if self.rescue_folder:
                                # For binary classification, just record "Not Spam"
                                email['category'] = "Not Spam"
                            else:
                                # For detailed classification, use the specific category
                                email['category'] = category
                                
                            email['folder'] = target_folder
                            self.history.save_full_history(email)
                            
                            # Add to display history
                            self.display.add_to_history(email)
                        else:
                            self.display.error(f"Failed to move email from Spam to: {target_folder}")
                    else:
                        self.display.info(f"[DRY RUN] Would rescue email to: {target_folder}")
                        # Add to display history in dry run mode too
                        if self.rescue_folder:
                            email['category'] = "Not Spam"
                        else:
                            email['category'] = category
                        email['folder'] = target_folder
                        self.display.add_to_history(email)
                else:
                    self.display.info(f"Classified as {category} but confidence ({confidence:.2f}) below threshold ({self.confidence_threshold})")
                    self.display.info("Keeping in Spam folder")
            
            # Small delay to see the update
            time.sleep(0.5)
            
            # Show progress again at the end of processing each email
            self.display.progress(i + 1, len(emails), "Spam review progress")
            print()  # Add a newline for separation
        
        # Show final timing information
        total_time = time.time() - start_time
        time_per_email = total_time / len(emails) if emails else 0
        
        # Show summary
        self.display.header("Spam Review Summary")
        self.display.success(f"Reviewed {len(emails)} emails in Spam folder")
        self.display.info(f"Rescued {rescued_count} false positives")
        self.display.info(f"Confirmed {confirmed_spam_count} as actual spam")
        self.display.info(f"Total processing time: {datetime.timedelta(seconds=int(total_time))}")
        self.display.info(f"Average time per email: {time_per_email:.2f} seconds")
        
        return rescued_count
