import requests
import json
import base64
import os

# Configuration from GitHub Environment Variables
USERNAME = os.getenv('AMMONITOR_USER')
PROJECT_KEY = os.getenv('AMMONITOR_PROJECT')
GITHUB_TOKEN = os.getenv('GITHUB_TOKEN')
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
    url = f"{BASE_URL}/auth-token/"
    data = {"username": USERNAME, "project_key": PROJECT_KEY, "app_id": "GitHubActionSync"}
    r = requests.post(url, data=data)
    token = r.json().get('token')
    if not token: 
        print("Failed to authenticate with AmmonitOR")
        return

    auth_header = {"Authorization": f"Token {token}"}
    
    for folder, serial in DEVICE_MAP.items():
        list_url = f"{BASE_URL}/{PROJECT_KEY}/{serial}/files/primary/"
        files_req = requests.get(list_url, headers=auth_header)
        if files_req.status_code != 200: continue
        
        files = files_req.json()
        if not files: continue
        
        filename = files[-1]['original_filename']
        dl_url = f"{BASE_URL}/{PROJECT_KEY}/{serial}/files/primary/{filename}/"
        content = requests.get(dl_url, headers=auth_header).json().get('file_content')
        
        gh_url = f"https://api.github.com/repos/{REPO_PATH}/contents/{folder}/{filename}"
        headers = {"Authorization": f"token {GITHUB_TOKEN}"}
        res = requests.get(gh_url, headers=headers)
        sha = res.json().get('sha') if res.status_code == 200 else None
        
        payload = {
            "message": f"GitHub Action Sync: {filename}",
            "content": base64.b64encode(content.encode()).decode(),
        }
        if sha: payload["sha"] = sha
        put_res = requests.put(gh_url, headers=headers, json=payload)
        print(f"Uploaded {filename} to {folder}: {put_res.status_code}")

if __name__ == '__main__':
    run_sync()
