# GroupMe CLI

A production-ready, user-friendly command-line client for GroupMe written in Python. It supports listing groups, reading messages, sending group messages, listing direct message chats, and sending direct messages. Designed to run smoothly inside GitHub Codespaces (or any Unix-like environment) using `typer` + `rich` for a pleasant UX.

## Features
- List all groups with IDs, names, member counts
- Read recent messages from a group with colored output
- Send messages to a group (with `--dry-run` for safety)
- List DM chats (shows last message snippet)
- Send direct messages (with `--dry-run`)
- Optional image upload helper (not exposed as a CLI command yet)
- Graceful error handling with descriptive messages
- Pagination support for fetching up to 500 recent messages

## Requirements
- Python 3.10+
- A valid GroupMe API token (get it from https://dev.groupme.com/)

## Quick Start
```bash
# Inside Codespaces or locally
cp .env.example .env
# Edit .env and set GROUPME_TOKEN

pip install -r requirements.txt

# List groups
python main.py list-groups

# Read last 50 messages from a group
python main.py read <group_id> --limit 50

# Dry-run a message (won't send)
python main.py send <group_id> "Hello from CLI" --dry-run

# Actually send a message (with confirmation prompt)
python main.py send <group_id> "Deployed new version" --confirm

# List DM chats
python main.py list-dms

# Send a direct message (dry run)
python main.py dm <user_id> "Hey there" --dry-run
```

## Environment Variables
Create a `.env` file or export variables in your shell:
```
GROUPME_TOKEN=your_token_here
```
The application loads `.env` automatically via `python-dotenv`.

## Output Examples
### List Groups
```
Groups
 ID          Name                 Members
 123456789   Project Alpha        7
 555444333   Weekend Plans        5
```

### Read Messages
```
2025-09-04 14:05:12 Alice: Deploy is live
2025-09-04 14:04:55 Bob: Great work!
```

### Dry Run Send
```
╭─ Dry Run Payload ───────────────────────────────╮
{'message': {'source_guid': '2d7d...', 'text': 'Hello from CLI', 'attachments': []}}
╰─────────────────────────────────────────────────╯
```

## Code Structure
- `main.py` – Typer CLI commands & presentation logic
- `groupme_api.py` – API abstraction (pagination, error handling, uploads)
- `.env.example` – Template for environment variables
- `requirements.txt` – Dependency list

## Design Notes
- API token is never logged.
- Pagination uses `before_id` to walk backwards until limit satisfied.
- `--dry-run` returns the payload that would be sent (no HTTP request).
- Timestamps displayed in local system time.

## Extending
Potential improvements:
- Add command for uploading an image then sending attachment.
- Add caching for group list.
- Add unit tests with mocked `requests`.
- Provide search within messages.

## Troubleshooting
| Issue | Fix |
|-------|-----|
| Missing token error | Ensure `.env` has `GROUPME_TOKEN` or export it in your shell |
| SSL / network errors | Check network connectivity; maybe retry later |
| 401 Unauthorized | Rotate / verify token on dev portal |

## License
MIT (add a `LICENSE` file if distributing publicly).

---
Feel free to fork and adapt. PRs welcome.
