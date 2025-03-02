# Proton Mail Folder Sorter

An intelligent email organizer that automatically classifies and moves emails to appropriate folders. Using a combination of rule-based pattern matching and AI (via a local LLM), this tool helps keep your Proton Mail inbox organized with minimal effort.

## Features

- **Smart Classification**: Uses AI to categorize emails (Work, Personal, Finance, Shopping, etc.)
- **Auto-Classification**: Pattern matching for faster classification without using the LLM for every email
- **Spam Review**: Identifies false positives in your Spam folder and rescues legitimate emails
- **Personal Context**: Accepts personal information to improve classification accuracy
- **Two-Pane Interface**: User-friendly console interface showing current email and processing history
- **Rule Suggestions**: Analyzes your email history to suggest auto-classification rules
- **Batch Processing**: Efficiently handles large mailboxes

## Installation

1. Clone this repository:
   ```bash
   git clone https://github.com/YourUsername/proton_mail_sorter.git
   cd proton_mail_sorter
   ```

2. Make sure you have the required Python packages:
   ```bash
   pip install requests
   ```

3. Make the main script executable:
   ```bash
   chmod +x proton_mail_sorter.py
   ```

## Setup

On first run, the script will create default configuration files:

```bash
./proton_mail_sorter.py
```

This creates:
- `~/.config/proton_mail_sorter.ini` - Main configuration file
- `~/.config/proton_mail_sorter_rules.ini` - Auto-classification rules
- `~/.config/proton_mail_sorter_context.txt` - Personal context information

Edit these files to add your IMAP server details and customize other settings.

### Configuration

The main configuration file (`~/.config/proton_mail_sorter.ini`) has several sections:

```ini
[IMAP]
server = mail.protonmail.ch 
port = 993
username = your_username
password = your_password
use_ssl = True
use_starttls = False

[LLM]
api_url = http://localhost:1234/v1/chat/completions
system_prompt = You are an email classifier. Categorize each email into one of these categories: Work, Personal, Finance, Shopping, Newsletter, Spam, Family, School.

[Folders]
Work = Folders/Work
Personal = Folders/Personal
Finance = Folders/Finance
Shopping = Folders/Shopping
Newsletter = Folders/Newsletter
Spam = Folders/Junk
Family = Folders/Family
School = Folders/School
```

## Running the Tool

### Basic Usage

```bash
./proton_mail_sorter.py
```

### Common Options

- **Process more emails**:
  ```bash
  ./proton_mail_sorter.py --limit 200
  ```

- **Dry run (test without moving emails)**:
  ```bash
  ./proton_mail_sorter.py --dry-run
  ```

- **List available folders**:
  ```bash
  ./proton_mail_sorter.py --list-folders
  ```

- **Debug mode**:
  ```bash
  ./proton_mail_sorter.py --debug
  ```

### Auto-Classification Rules

Suggest new rules based on your email history:
```bash
./proton_mail_sorter.py --suggest-rules
```

### Spam Review

Check your Spam folder for legitimate emails:
```bash
./proton_mail_sorter.py --review-spam
```

With options:
```bash
./proton_mail_sorter.py --review-spam --confidence-threshold 0.8 --rescue-folder "INBOX"
```

## LLM Integration

The tool requires a local LLM API that's compatible with the OpenAI chat completions format. You can use:

- [Ollama](https://ollama.ai/)
- [LM Studio](https://lmstudio.ai/)
- [LocalAI](https://localai.io/)
- Any compatible API endpoint

Configure the API URL in the settings file.

## Project Structure

```
proton_mail_sorter/
│
├── proton_mail_sorter.py     # Main script
│
├── modules/
│   ├── __init__.py           # Package initialization
│   ├── display.py            # Console display formatting
│   ├── config.py             # Configuration management
│   ├── imap_client.py        # IMAP email operations
│   ├── llm_client.py         # LLM classification
│   ├── history.py            # Processing history tracking
│   ├── auto_classifier.py    # Pattern-based classification
│   └── spam_reviewer.py      # Spam folder analysis
```

## Security Notes

- No sensitive data is stored in this codebase
- Credentials are stored locally in your config files
- Consider using app-specific passwords for added security

## Contributing

Contributions are welcome! Feel free to submit a pull request or open an issue.

## License

This project is licensed under the MIT License - see the LICENSE file for details.
