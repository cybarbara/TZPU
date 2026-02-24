#!/usr/bin/env python3
"""
Polls Moodle (localhost) for online users every 2 minutes.
Enriches each user with:
  - Last IP from MySQL
  - Classroom derived from IP
  - Hashed user ID (SHA256, 8 chars)
Then overwrites a Google Sheet with the latest data.
"""

import time
import hashlib
import requests
import json
import mysql.connector
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime

# ── Configuration ─────────────────────────────────────────────────────────────
MOODLE_URL       = "http://localhost"       #Adresa   
TOKEN            = "YourToken"    #Token
INTERVAL         = 10
ONLINE_WINDOW    = 300                         

# MySQL / MariaDB
DB_HOST          = "localhost"
DB_PORT          = 3306
DB_NAME          = "moodle"                    # Your Moodle database name
DB_USER          = "DatabaseUsername"                      # Your database username
DB_PASSWORD      = "DataBase password"          # Your database password
DB_PREFIX        = "mdl_"                      # Moodle table prefix

# Google Sheets
SERVICE_ACCOUNT  = "serviceAccount.json"                   # Path to your service account JSON
SPREADSHEET_ID   = "SpreadSheetID"       # The ID from your Google Sheet URL
SHEET_NAME       = "SheetName"                                              # Name of the tab to write to
# ──────────────────────────────────────────────────────────────────────────────

ENDPOINT = f"{MOODLE_URL}/webservice/rest/server.php"

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]


# ── Helper functions ───────────────────────────────────────────────────────────

def hash_user_id(user_id: int) -> str:
    return hashlib.sha256(str(user_id).encode()).hexdigest()[:8]


def get_classroom(ip: str) -> str:
    try:
        last_part = ip.split(":")[-1] if ":" in ip else ip.split(".")[-1]
        return f"Classroom {last_part}"
    except IndexError:
        return "Unknown"


def get_ip_map(user_ids: list) -> dict:
    if not user_ids:
        return {}
    try:
        conn = mysql.connector.connect(
            host=DB_HOST, port=DB_PORT, database=DB_NAME,
            user=DB_USER, password=DB_PASSWORD, connection_timeout=10,
        )
        cursor = conn.cursor()
        placeholders = ", ".join(["%s"] * len(user_ids))
        cursor.execute(
            f"SELECT id, lastip FROM {DB_PREFIX}user WHERE id IN ({placeholders})",
            user_ids,
        )
        ip_map = {row[0]: row[1] or "N/A" for row in cursor.fetchall()}
        cursor.close()
        conn.close()
        return ip_map
    except mysql.connector.Error as e:
        print(f"[DB ERROR] {e}")
        return {}


def get_online_users():
    since = int(time.time()) - ONLINE_WINDOW
    params = {
        "wstoken":            TOKEN,
        "wsfunction":         "core_user_get_users",
        "moodlewsrestformat": "json",
        "criteria[0][key]":   "lastaccess",
        "criteria[0][value]": since,
    }
    try:
        response = requests.get(ENDPOINT, params=params, timeout=30)
        response.raise_for_status()
        data = response.json()
        if isinstance(data, dict) and "exception" in data:
            print(f"[ERROR] Moodle exception: {data.get('message', data)}")
            return None
        users = data.get("users", [])
        return [u for u in users if u.get("lastaccess", 0) >= since]
    except requests.exceptions.ConnectionError:
        print("[ERROR] Could not connect to Moodle.")
    except requests.exceptions.Timeout:
        print("[ERROR] Request timed out.")
    except requests.exceptions.HTTPError as e:
        print(f"[ERROR] HTTP error: {e}")
    except json.JSONDecodeError:
        print("[ERROR] Could not parse JSON response.")
    return None


def get_sheet():
    creds = Credentials.from_service_account_file(SERVICE_ACCOUNT, scopes=SCOPES)
    client = gspread.authorize(creds)
    return client.open_by_key(SPREADSHEET_ID).worksheet(SHEET_NAME)


def load_seen_ids(sheet) -> set:
    """Load already seen hashed IDs from column A of the sheet."""
    try:
        col = sheet.col_values(1)  # column A
        # Skip header row
        return set(col[1:]) if len(col) > 1 else set()
    except Exception as e:
        print(f"[SHEET ERROR] Could not load seen IDs: {e}")
        return set()


def push_to_sheet(sheet, users: list, ip_map: dict, seen_ids: set) -> None:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    
    if not sheet.cell(1, 1).value:
        header = ["Hashed ID",  "Last Seen", "Classroom", "Snapshot Time"]
        sheet.append_row(header)

    
    rows = []
    for u in users:
        uid       = u.get("id", 0)
        hashed_id = hash_user_id(uid)

        if hashed_id in seen_ids:
            continue 
       
        lastaccess = u.get("lastaccess", 0)
        last_dt    = datetime.fromtimestamp(lastaccess).strftime("%H:%M:%S") if lastaccess else "N/A"
        ip         = ip_map.get(uid, "N/A")
        classroom  = get_classroom(ip)

        rows.append([hashed_id, last_dt,  classroom, now])
        seen_ids.add(hashed_id)

    if rows:
        sheet.append_rows(rows)
        print(f"[{now}] {len(rows)} new user(s) appended to sheet.")
    else:
        print(f"[{now}] No new users to append.")


def display_users(users: list, ip_map: dict) -> None:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"\n{'='*80}")
    print(f"  Online Users (active in last 5 min)  —  {now}")
    print(f"{'='*80}")
    if not users:
        print("  No users currently online.")
    else:
        print(f"  Total online: {len(users)}\n")
        print(f"  {'Hash':<10}  {'Full Name':<25}  {'Username':<20}  {'Last Seen':<10}  {'IP':<20}  {'Classroom'}")
        print(f"  {'-'*10}  {'-'*25}  {'-'*20}  {'-'*10}  {'-'*20}  {'-'*12}")
        for u in users:
            uid        = u.get("id", 0)
            fullname   = u.get("fullname", "Unknown")
            username   = u.get("username", "")
            lastaccess = u.get("lastaccess", 0)
            last_dt    = datetime.fromtimestamp(lastaccess).strftime("%H:%M:%S") if lastaccess else "N/A"
            ip         = ip_map.get(uid, "N/A")
            classroom  = get_classroom(ip)
            hashed_id  = hash_user_id(uid)
            print(f"  {hashed_id:<10}  {fullname:<25}  {username:<20}  {last_dt:<10}  {ip:<20}  {classroom}")
    print(f"{'='*80}")


# ── Main loop ──────────────────────────────────────────────────────────────────

def main() -> None:
    print("Moodle Online Users Monitor")
    print(f"Endpoint      : {ENDPOINT}")
    print(f"Database      : {DB_USER}@{DB_HOST}:{DB_PORT}/{DB_NAME}")
    print(f"Google Sheet  : {SPREADSHEET_ID} / {SHEET_NAME}")
    print(f"Interval      : {INTERVAL}s  (every 2 minutes)")
    print(f"Online window : last {ONLINE_WINDOW // 60} minutes")
    print("Press Ctrl+C to stop.\n")

    sheet    = get_sheet()
    seen_ids = load_seen_ids(sheet)  # load existing IDs from sheet on startup
    print(f"Loaded {len(seen_ids)} existing user(s) from sheet.\n")

    while True:
        users = get_online_users()

        if users is not None:
            user_ids = [u.get("id") for u in users if u.get("id")]
            ip_map   = get_ip_map(user_ids)
            display_users(users, ip_map)
            push_to_sheet(sheet, users, ip_map, seen_ids)
        else:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Skipping due to error.")

        time.sleep(INTERVAL)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nStopped by user.")
