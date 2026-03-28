from seleniumbase import SB
import csv
import base64
import io

TARGET_URL = "https://circolocoibiza.com/event/warsaw"
ACCOUNTS_FILE = "accounts.csv"

def signup_email(sb, email_addr):
    print(f"\n Processing")
    sb.open(TARGET_URL)
    
    # Wait for Laylo iframe and switch
    # Increased wait time for slow loading
    sb.wait_for_element('iframe[src*="laylo"]', timeout=30)
    sb.switch_to_frame('iframe[src*="laylo"]')
    
    # Fill email
    # Check for the input field to be clickable
    sb.wait_for_element('[id=":r7:"]', timeout=15)
    sb.type('[id=":r7:"]', email_addr)
    
    # Submit RSVP
    sb.click('[id="laylo-rsvp-submit-button"]')
    
    # Check for success message "Check your email"
    sb.sleep(5)
    if sb.is_element_visible('div:contains("Check your email")'):
        print(f"[DONE]")
        return True
    else:
        return False

if __name__ == "__main__":
    with SB(uc=True, headless=True) as sb: 
        try:
            with open(ACCOUNTS_FILE, "rb") as f:
                content = f.read()
                # Attempt to decode as base64 first; if it fails, read as plain text
                try:
                    # Some base64 strings might have padding issues or not be base64 at all
                    decoded = base64.b64decode(content).decode('utf-8')
                    csv_data = io.StringIO(decoded)
                except Exception:
                    csv_data = io.StringIO(content.decode('utf-8'))
                
                reader = csv.DictReader(csv_data)
                for row in reader:
                    email = row.get('email', '').strip()
                    if email:
                        signup_email(sb, email)
                        # Clear state before next iteration
                        sb.delete_all_cookies()
                        sb.sleep(2)
        except Exception as e:
            print(f"ERROR processing signups: {e}")