# Moodle Online Users Monitor

A Python script that polls a Moodle instance for recently active users, enriches each record with their last known IP and derived classroom, then appends new entries to a Google Sheet — all on a configurable interval.

---

## Features

- Fetches users active in the last 5 minutes via the Moodle Web Services REST API
- Looks up each user's last IP address directly from the Moodle MySQL/MariaDB database
- Derives a classroom label from the IP address (based on the last octet/segment)
- Anonymises user identity using an 8-character SHA-256 hash of the user ID
- Appends only **new** users (not previously seen in the sheet) to a Google Sheet
- Prints a formatted live table to the terminal on every poll

---

## Requirements

- Python 3.8+
- A running Moodle instance with Web Services enabled
- Access to the Moodle MySQL/MariaDB database
- A Google Cloud service account with access to the target spreadsheet

### Python dependencies

Install with pip:

```bash
pip install requests mysql-connector-python gspread google-auth
```

---

## Configuration

All settings are defined at the top of the script:

| Variable | Description |
|---|---|
| `MOODLE_URL` | Base URL of your Moodle instance (e.g. `http://localhost`) |
| `TOKEN` | Moodle Web Services token |
| `INTERVAL` | Polling interval in seconds (default: `10`) |
| `ONLINE_WINDOW` | Time window in seconds to consider a user "online" (default: `300` = 5 min) |
| `DB_HOST` | MySQL host (default: `localhost`) |
| `DB_PORT` | MySQL port (default: `3306`) |
| `DB_NAME` | Moodle database name |
| `DB_USER` | Database username |
| `DB_PASSWORD` | Database password |
| `DB_PREFIX` | Moodle table prefix (default: `mdl_`) |
| `SERVICE_ACCOUNT` | Path to your Google service account JSON file |
| `SPREADSHEET_ID` | Google Sheet ID (from the URL) |
| `SHEET_NAME` | Name of the worksheet tab to write to |

---

## Setup

### 1. Enable Moodle Web Services

1. Go to **Site Administration → Plugins → Web Services → Overview** and follow the setup steps.
2. Enable the `core_user_get_users` function for your service.
3. Generate a token for a user with sufficient permissions and set it as `TOKEN`.

### 2. Google Sheets service account

1. Create a project in [Google Cloud Console](https://console.cloud.google.com/).
2. Enable the **Google Sheets API** and **Google Drive API**.
3. Create a **Service Account** and download the JSON key file.
4. Share your Google Sheet with the service account's email address (Editor access).
5. Set `SERVICE_ACCOUNT` to the path of the downloaded JSON file.

### 3. Run the script

```bash
python monitor.py
```

Press `Ctrl+C` to stop.

---

## Google Sheet output

The script writes to the configured sheet with the following columns:

| Hashed ID | Last Seen | Classroom | Snapshot Time |
|---|---|---|---|
| `a3f9c12b` | `09:42:11` | `Classroom 101` | `2025-01-15 09:42:15` |

- **Hashed ID** — First 8 characters of the SHA-256 hash of the Moodle user ID
- **Last Seen** — Time of the user's last Moodle activity (HH:MM:SS)
- **Classroom** — Derived from the last segment of the user's IP address
- **Snapshot Time** — Timestamp when the row was written

Each user is only written once per session (duplicate entries are skipped).

---

## Classroom detection

The classroom is inferred from the last segment of the user's IP:

- IPv4 `192.168.1.45` → `Classroom 45`
- IPv6 `::ffff:c0a8:012d` → uses the last colon-separated segment

You can customise the `get_classroom()` function to map IP ranges to specific room names.

---

## Notes

- The script loads already-seen hashed IDs from the sheet on startup, so restarting will not create duplicate rows.
- Full name and username are shown in the terminal only and are **never written to the sheet**, preserving user privacy.
- If the Moodle API or database is unreachable, the poll cycle is skipped and the script retries on the next interval.
