import requests
import base64
import os
from datetime import datetime, timedelta

# Configuration from GitHub Environment Variables
USERNAME = os.getenv('AM_USER')
PROJECT_KEY = os.getenv('AM_PROJECT')
GITHUB_TOKEN = os.getenv('GH_PAT')
REPO_PATH = "PrajeshS/WeatherData"
BASE_URL = "https://or.ammonit.com/api"

DEVICE_MAP = {
    "WMS 01": "G254070",
    "WMS 02": "G254073",
    "WMS 03": "G254071",
    "WMS 04": "G254072",
    "WMS 05": "G254074"
}

def run_sync():
    # Debug: Print what we have
    print(f"DEBUG - USERNAME: {USERNAME}")
    print(f"DEBUG - PROJECT_KEY: {PROJECT_KEY}")
    print(f"DEBUG - GITHUB_TOKEN: {'***' if GITHUB_TOKEN else 'MISSING'}")
    
    # 1. Target Yesterday's Date (YYYYMMDD)
    yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y%m%d')
    print(f"Targeting data for: {yesterday}")

    # 2. Authenticate
    url = f"{BASE_URL}/auth-token/"
    data = {"username": USERNAME, "project_key": PROJECT_KEY, "app_id": "GitHubActionSync"}
    print(f"DEBUG - Auth URL: {url}")
    print(f"DEBUG - Auth data: {data}")
    
    r = requests.post(url, data=data)
    print(f"DEBUG - Response status: {r.status_code}")
    print(f"DEBUG - Response text: {r.text}")
    print(f"DEBUG - Response headers: {r.headers}")
    
    try:
        token = r.json().get('token')
    except Exception as e:
        print(f"ERROR - Failed to parse JSON response: {e}")
        print(f"ERROR - Raw response: {r.text}")
        return
    
    if not token:
        print("Failed to authenticate with AmmonitOR. Ensure you approved the enquiry in the portal.")
        return

    auth_header = {"Authorization": f"Token {token}"}
    headers = {"Authorization": f"token {GITHUB_TOKEN}"}

    for folder, serial in DEVICE_MAP.items():
        print(f"Checking {folder} ({serial})...")

        # 3. Get file list
        list_url = f"{BASE_URL}/{PROJECT_KEY}/{serial}/files/primary/"
        files_req = requests.get(list_url, headers=auth_header)
        if files_req.status_code != 200: 
            print(f"   ! Failed to get file list: {files_req.status_code}")
            continue

        files = files_req.json()

        # 4. Find the file specifically for yesterday
        target_file = next((f for f in reversed(files) if f'_{yesterday}_' in f['original_filename']), None)

        if not target_file:
            print(f"   ! No file found yet for {yesterday}. Skipping until next hourly retry.")
            continue

        filename = target_file['original_filename']

        # 5. Check if already on GitHub
        gh_url = f"https://api.github.com/repos/{REPO_PATH}/contents/{folder}/{filename}"
        res = requests.get(gh_url, headers=headers)

        if res.status_code == 200:
            print(f"   - {filename} already exists on GitHub. Skipping.")
            continue

        # 6. Download and Upload
        dl_url = f"{BASE_URL}/{PROJECT_KEY}/{serial}/files/primary/{filename}/"
        content_res = requests.get(dl_url, headers=auth_header).json()
        csv_content = content_res.get('file_content')

        payload = {
            "message": f"Automated Sync: {filename}",
            "content": base64.b64encode(csv_content.encode()).decode(),
        }

        put_res = requests.put(gh_url, headers=headers, json=payload)
        if put_res.status_code in [200, 201]:
            print(f"   ✅ Successfully uploaded: {filename}")
        else:
            print(f"   ❌ Failed to upload {filename}: {put_res.status_code}")

if __name__ == '__main__':
    run_sync()
