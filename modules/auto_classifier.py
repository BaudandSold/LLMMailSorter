"""
Auto Classifier module - Pattern-based email classification without using LLM.

This module handles email classification based on configured patterns, which is
much faster than using the LLM and can be used for easily recognizable emails.
"""

import re
import os
import configparser
from pathlib import Path

class AutoClassifier:
    """Handles pattern-based auto-classification of emails."""
    
    def __init__(self, display):
        """Initialize with display handler."""
        self.display = display
        self.rules = {
            'Domains': {},
            'Subjects': {},
            'Keywords': {}
        }
        self.rules_path = Path.home() / '.config' / 'proton_mail_sorter_rules.ini'
        self.load_rules()
    
    def load_rules(self):
        """Load classification rules from configuration file."""
        if not self.rules_path.exists():
            self.display.info("No auto-classification rules found. Creating example rules file.")
            self._create_default_rules()
            return
        
        try:
            config = configparser.ConfigParser()
            config.read(self.rules_path)
            
            # Load domain rules
            if 'Domains' in config:
                for key, value in config['Domains'].items():
                    self.rules['Domains'][key] = value
            
            # Load subject rules
            if 'Subjects' in config:
                for key, value in config['Subjects'].items():
                    self.rules['Subjects'][key] = value
            
            # Load keyword rules
            if 'Keywords' in config:
                for key, value in config['Keywords'].items():
                    self.rules['Keywords'][key] = value
            
            total_rules = len(self.rules['Domains']) + len(self.rules['Subjects']) + len(self.rules['Keywords'])
            self.display.success(f"Loaded {total_rules} auto-classification rules")
            
        except Exception as e:
            self.display.error(f"Error loading auto-classification rules: {e}")
    
    def _create_default_rules(self):
        """Create a default rules file with examples."""
        config = configparser.ConfigParser()
        
        config['Domains'] = {
            'newsletter@example.com': 'Newsletter',
            'billing@example.com': 'Finance',
            '*@school.edu': 'School'
        }
        
        config['Subjects'] = {
            'Your order has shipped': 'Shopping',
            'Weekly newsletter': 'Newsletter',
            'Invoice for': 'Finance',
            'Receipt for your purchase': 'Shopping'
        }
        
        config['Keywords'] = {
            'meeting agenda': 'Work',
            'family gathering': 'Family',
            'account statement': 'Finance',
            'tracking number': 'Shopping'
        }
        
        # Create directory if it doesn't exist
        self.rules_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Write default rules
        with open(self.rules_path, 'w') as configfile:
            config.write(configfile)
        
        self.display.success(f"Created example rules file at {self.rules_path}")
        self.display.info(f"Edit this file to add your own auto-classification rules")
        
        # Also load these default rules
        self.rules['Domains'] = dict(config['Domains'])
        self.rules['Subjects'] = dict(config['Subjects'])
        self.rules['Keywords'] = dict(config['Keywords'])
    
    def check_auto_classification(self, email_data):
        """Check if email matches any auto-classification rules."""
        # Check sender domain
        sender = email_data.get('from', '')
        for domain, category in self.rules['Domains'].items():
            if domain in sender:
                self.display.debug(f"Domain match: {domain} in {sender}")
                return category
            if domain.startswith('*@') and domain[1:] in sender:
                self.display.debug(f"Wildcard domain match: {domain} in {sender}")
                return category
        
        # Check subject patterns
        subject = email_data.get('subject', '')
        for pattern, category in self.rules['Subjects'].items():
            if pattern.lower() in subject.lower():
                self.display.debug(f"Subject match: '{pattern}' in '{subject}'")
                return category
        
        # Check content keywords
        body = email_data.get('body', '')
        for keyword, category in self.rules['Keywords'].items():
            if keyword.lower() in body.lower():
                self.display.debug(f"Keyword match: '{keyword}' in email body")
                return category
        
        return None  # No auto-classification match
    
    def add_rule(self, rule_type, pattern, category):
        """Add a new classification rule."""
        if rule_type not in self.rules:
            self.display.error(f"Invalid rule type: {rule_type}")
            return False
        
        # Add to in-memory rules
        self.rules[rule_type][pattern] = category
        
        # Update the rules file
        try:
            config = configparser.ConfigParser()
            
            # Read existing rules if file exists
            if self.rules_path.exists():
                config.read(self.rules_path)
            
            # Ensure all sections exist
            for section in self.rules:
                if section not in config:
                    config[section] = {}
            
            # Add new rule
            config[rule_type][pattern] = category
            
            # Write updated rules
            with open(self.rules_path, 'w') as configfile:
                config.write(configfile)
            
            self.display.success(f"Added new {rule_type} rule: {pattern} → {category}")
            return True
            
        except Exception as e:
            self.display.error(f"Error adding rule: {e}")
            return False
    
    def suggest_rules_from_history(self, email_history, min_occurrences=3):
        """Analyze email history to suggest new auto-classification rules."""
        # Count domain occurrences by category
        domain_counts = {}
        subject_pattern_counts = {}
        
        for email in email_history:
            if 'from' not in email or 'category' not in email:
                continue
                
            # Extract domain from email
            from_addr = email['from']
            domain_match = re.search(r'@[\w.-]+', from_addr)
            if domain_match:
                domain = domain_match.group(0)  # Get the matched domain
                category = email['category']
                
                # Count domain-category pairs
                if domain not in domain_counts:
                    domain_counts[domain] = {}
                if category not in domain_counts[domain]:
                    domain_counts[domain][category] = 0
                domain_counts[domain][category] += 1
            
            # Look for common subject patterns
            if 'subject' in email:
                subject = email['subject'].lower()
                category = email['category']
                
                # Check for common beginnings (first 3+ words)
                words = subject.split()
                if len(words) >= 3:
                    for i in range(3, min(len(words) + 1, 6)):  # Check patterns of 3-5 words
                        pattern = ' '.join(words[:i])
                        if len(pattern) >= 10:  # Only consider substantial patterns
                            if pattern not in subject_pattern_counts:
                                subject_pattern_counts[pattern] = {}
                            if category not in subject_pattern_counts[pattern]:
                                subject_pattern_counts[pattern][category] = 0
                            subject_pattern_counts[pattern][category] += 1
        
        # Find domains with consistent categorization
        suggested_rules = []
        
        for domain, categories in domain_counts.items():
            # Find most common category for this domain
            max_count = 0
            max_category = None
            for category, count in categories.items():
                if count > max_count:
                    max_count = count
                    max_category = category
            
            # If it occurs enough times and is dominant, suggest it
            if max_count >= min_occurrences and max_count / sum(categories.values()) >= 0.75:
                suggested_rules.append({
                    'type': 'Domains',
                    'pattern': f'*{domain}',  # Use wildcard for the domain
                    'category': max_category,
                    'confidence': max_count / sum(categories.values()),
                    'occurrences': max_count
                })
        
        # Find subject patterns with consistent categorization
        for pattern, categories in subject_pattern_counts.items():
            max_count = 0
            max_category = None
            for category, count in categories.items():
                if count > max_count:
                    max_count = count
                    max_category = category
            
            if max_count >= min_occurrences and max_count / sum(categories.values()) >= 0.8:
                suggested_rules.append({
                    'type': 'Subjects',
                    'pattern': pattern,
                    'category': max_category,
                    'confidence': max_count / sum(categories.values()),
                    'occurrences': max_count
                })
        
        # Sort by occurrences
        suggested_rules.sort(key=lambda x: x['occurrences'], reverse=True)
        
        return suggested_rules
