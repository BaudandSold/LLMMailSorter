"""
LLM Client module - Handles interaction with the local LLM for email classification.

This module is responsible for:
- Connecting to a local LLM API
- Formatting email data for classification
- Processing LLM responses
"""

import requests
import re

class LlmClient:
    """Handles interaction with the local LLM for email classification."""
    
    def __init__(self, config, display):
        """Initialize with LLM configuration and display handler."""
        self.config = config
        self.display = display
        self.api_url = config.get('api_url', 'http://localhost:1234/v1/chat/completions')
        self.system_prompt = config.get('system_prompt', 'You are an email classifier.')
    
    def classify_email(self, email, personal_context=None):
        """Send email content to the local LLM for classification with personal context."""
        self.display.subheader("LLM Classification")
        
        # Enhance the system prompt with personal context if available
        if personal_context and len(personal_context) > 0:
            context_text = "\n".join(personal_context)
            enhanced_system_prompt = f"{self.system_prompt}\n\nHere is some personal context to help you better classify emails:\n{context_text}\n\nUse this context to better understand the significance of senders and email contents."
        else:
            enhanced_system_prompt = self.system_prompt
        
        # Extract sender's email address
        from_addr = email['from']
        email_address = re.search(r'<([^>]+)>', from_addr)
        email_address = email_address.group(1) if email_address else from_addr.strip() if '@' in from_addr else ""
        
        # Prepare email content for the LLM
        email_content = f"""
Subject: {email['subject']}
From: {from_addr}
From Email: {email_address}
Date: {email['date']}

{email['body']}
"""
        
        user_prompt = """Please categorize this email into exactly one of these categories: Work, Personal, Finance, Shopping, Newsletter, Spam, Family, School."""
        
        # Prepare the request to the LLM
        payload = {
            "model": "local-model",
            "messages": [
                {"role": "system", "content": enhanced_system_prompt},
                {"role": "user", "content": f"{user_prompt}\n\n{email_content}"}
            ],
            "temperature": 0.1,
            "max_tokens": 50
        }
        
        try:
            self.display.info(f"Sending request to LLM at {self.api_url}")
            response = requests.post(self.api_url, json=payload)
            response.raise_for_status()
            
            result = response.json()
            if 'choices' in result and len(result['choices']) > 0:
                category = result['choices'][0]['message']['content'].strip()
                
                # Extract just the category name if the LLM returns additional text
                valid_categories = ['Work', 'Personal', 'Finance', 'Shopping', 'Newsletter', 'Spam', 'Family', 'School']
                for valid_category in valid_categories:
                    if valid_category.lower() in category.lower():
                        self.display.success(f"LLM classified email as: {valid_category}")
                        return valid_category
                
                self.display.warning(f"LLM returned unrecognized category: {category}")
                return "Uncategorized"
            else:
                self.display.error(f"Unexpected LLM response structure")
                return "Uncategorized"
            
        except requests.exceptions.ConnectionError:
            self.display.error(f"Connection error. Is the LLM server running at {self.api_url}?")
            return "Error"
        except Exception as e:
            self.display.error(f"Error calling LLM API: {e}")
            return "Error"
