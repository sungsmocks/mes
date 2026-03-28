from seleniumbase import SB
import csv
import base64
import io
import os
import requests
import json

# Configuration from Environment Variables (GitHub Secrets/Actions)
TARGET_URL = os.environ.get('SYNC_URL')
DATA_CSV_B64 = os.environ.get('DATA_CSV_B64')
NEXT_ROW = os.environ.get('NEXT_ROW')
PAT_TOKEN = os.environ.get('PAT_TOKEN')
DISCORD_URL = os.environ.get('DISCORD_WEBHOOK_URL')
REPO = os.environ.get('GITHUB_REPOSITORY')

def update_github_variable(name, value):
    """Updates a GitHub repository variable."""
    if not PAT_TOKEN or not REPO:
        return
    url = f"https://api.github.com/repos/{REPO}/actions/variables/{name}"
    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"token {PAT_TOKEN}",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    data = {"name": name, "value": str(value)}
    try:
        r = requests.patch(url, headers=headers, json=data)
        if r.status_code == 204:
            print("[GITHUB] OK")
        else:
            print(f"[GITHUB] FAIL ({r.status_code})")
    except Exception:
        print("[GITHUB] ERROR")

def notify_discord(email, status="success", details=""):
    """Sends a clean Discord embed notification."""
    if not DISCORD_URL:
        return
    
    # Define color and title based on status
    color = 3066993 if status == "success" else 15158332 # Green or Red
    title = "done." if status == "success" else "Failed"
    
    payload = {
        "embeds": [
            {
                "title": title,
                "color": color,
                "fields": [
                    {"name": "Email", "value": f"`{email}`", "inline": True},
                ],
                "footer": {"text": "Circoloco Automation"}
            }
        ]
    }
    
    if details:
        payload["embeds"][0]["fields"].append({"name": "Note", "value": details, "inline": False})

    try:
        requests.post(DISCORD_URL, json=payload)
    except Exception as e:
        print(f"[DISCORD] Error: {e}")

def signup_email(sb, email_addr):
    print("Running...")
    # Always open target URL to start fresh
    sb.open(TARGET_URL)
    
    # Wait for Laylo iframe and switch
    # Handle both iframe and main page cases just in case
    try:
        sb.wait_for_element('iframe[src*="laylo"]', timeout=30)
        sb.switch_to_frame('iframe[src*="laylo"]')
    except:
        print("[WARN] Iframe not found, checking if form is on main page.")
    
    # Wait for the email input and type (using current known id)
    sb.wait_for_element('[id=":r7:"]', timeout=15)
    sb.type('[id=":r7:"]', email_addr)
    
    # Submit RSVP
    sb.click('[id="laylo-rsvp-submit-button"]')
    
    # Wait for success message "Check your email"
    sb.sleep(6)
    if sb.is_element_visible('div:contains("Check your email")'):
        print("Success")
        return True
    else:
        print("Fail")
        sb.save_screenshot("fail_latest.png")
        return False

if __name__ == "__main__":
    # Determine which CSV to use: Base64 from environment or local accounts.csv
    csv_data = None
    if DATA_CSV_B64:
        try:
            print("[CSV] Using DATA_CSV_B64 from environment.")
            decoded = base64.b64decode(DATA_CSV_B64).decode('utf-8')
            csv_data = io.StringIO(decoded)
        except Exception as e:
            print(f"[ERROR] Failed to decode DATA_CSV_B64: {e}")

    if not csv_data and os.path.exists("accounts.csv"):
        print("[CSV] Using local accounts.csv.")
        with open("accounts.csv", "r") as f:
            csv_data = io.StringIO(f.read())

    if not csv_data:
        print("[ERROR] No CSV source found (DATA_CSV_B64 or accounts.csv).")
        exit(1)

    # Convert to list to allow indexing
    reader = csv.DictReader(csv_data)
    rows = list(reader)
    total_rows = len(rows)

    # Determine which row(s) to process
    idx = 0
    single_mode = False
    if NEXT_ROW is not None:
        try:
            idx = int(NEXT_ROW)
            single_mode = True
            print("Starting...")
        except ValueError:
            print(f"[WARN] Invalid NEXT_ROW '{NEXT_ROW}', starting from 0.")

    if idx >= total_rows:
        print(f"[INFO] All rows ({total_rows}) have already been processed.")
        exit(0)

    with SB(uc=True, headless=True) as sb:
        if single_mode:
            # Process single row
            email = rows[idx].get('email', '').strip()
            if email:
                # Update GitHub variable IMMEDIATELY to prevent race conditions
                # This ensures any subsequent trigger sees the next index right away.
                update_github_variable("NEXT_ROW", idx + 1)
                
                success = signup_email(sb, email)
                if success:
                    notify_discord(email, status="success")
                else:
                    notify_discord(email, status="failed", details="RSVP status unclear. Check logs/artifacts.")
                    exit(1)
        else:
            # Iterative mode for local testing
            for i, row in enumerate(rows):
                email = row.get('email', '').strip()
                if email:
                    success = signup_email(sb, email)
                    if success:
                        sb.delete_all_cookies()
                        sb.sleep(2)
                    else:
                        print(f"Failed at row {i}")
