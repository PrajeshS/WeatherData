#!/usr/bin/python3

# AmmonitOR API Client for GitHub Actions
# Based on AmmonitOR REST API example

import requests
import base64
import os
import json
from datetime import datetime, timedelta

# Configuration from GitHub Environment Variables
USERNAME = os.getenv('AM_USER')
PROJECT_KEY = os.getenv('AM_PROJECT')
GITHUB_TOKEN = os.getenv('GH_PAT')
REPO_PATH = "PrajeshS/WeatherData"
SERVER_URL = "https://or.ammonit.com"
API_BASE = f"{SERVER_URL}/api"

DEVICE_MAP = {
    "WMS 01": "G254070",
    "WMS 02": "G254073",
    "WMS 03": "G254071",
    "WMS 04": "G254072",
    "WMS 05": "G254074"
}

# SSL verification
VERIFY_SSL = True


def get_token():
    """Get authentication token from AmmonitOR"""
    url = API_BASE + "/auth-token/"
    data = {
        "username": USERNAME,
        "project_key": PROJECT_KEY,
        "app_id": "GitHubActionSync"
    }
    
    try:
        r = requests.post(url, data=data, verify=VERIFY_SSL)
        
        if r.status_code != 200:
            print(f"ERROR: Authentication failed with status {r.status_code}")
            print(f"Response: {r.text}")
            return None
            
        response_data = r.json()
        print(f"Auth response: {response_data}")
        token = response_data.get('token')
        
        if not token:
            print("ERROR: No token in response. Ensure you approved the enquiry in the portal.")
            return None
            
        return token
        
    except requests.exceptions.RequestException as e:
        print(f"ERROR: Authentication request failed: {e}")
        return None


def list_files(token, project_key, device_serial, filetype="primary"):
    """List data files for a device"""
    url = f"{API_BASE}/{project_key}/{device_serial}/files/{filetype}/"
    headers = {"Authorization": f"Token {token}"}
    
    try:
        r = requests.get(url, headers=headers, verify=VERIFY_SSL)
        
        if r.status_code != 200:
            print(f"   ! Failed to list files: {r.status_code}")
            return None
            
        return r.json()
        
    except requests.exceptions.RequestException as e:
        print(f"   ! Error listing files: {e}")
        return None


def get_file_download(token, project_key, device_serial, filename, filetype="primary"):
    """Download data file content"""
    url = f"{API_BASE}/{project_key}/{device_serial}/files/{filetype}/{filename}/"
    headers = {"Authorization": f"Token {token}"}
    
    try:
        r = requests.get(url, headers=headers, verify=VERIFY_SSL)
        
        if r.status_code != 200:
            print(f"   ! Failed to download file: {r.status_code}")
            return None
            
        response_data = r.json()
        return response_data.get('file_content')
        
    except requests.exceptions.RequestException as e:
        print(f"   ! Error downloading file: {e}")
        return None


def check_github_file(repo_path, folder, filename):
    """Check if file already exists on GitHub"""
    url = f"https://api.github.com/repos/{repo_path}/contents/{folder}/{filename}"
    headers = {"Authorization": f"token {GITHUB_TOKEN}"}
    
    try:
        r = requests.get(url, headers=headers, verify=VERIFY_SSL)
        return r.status_code == 200
        
    except requests.exceptions.RequestException as e:
        print(f"   ! Error checking GitHub: {e}")
        return False


def upload_to_github(repo_path, folder, filename, csv_content):
    """Upload file to GitHub"""
    url = f"https://api.github.com/repos/{repo_path}/contents/{folder}/{filename}"
    headers = {"Authorization": f"token {GITHUB_TOKEN}"}
    
    try:
        encoded_content = base64.b64encode(csv_content.encode()).decode()
        
        payload = {
            "message": f"Automated Sync: {filename}",
            "content": encoded_content
        }
        
        r = requests.put(url, headers=headers, json=payload, verify=VERIFY_SSL)
        
        if r.status_code in [200, 201]:
            return True
        else:
            print(f"   ! GitHub upload failed: {r.status_code}")
            return False
            
    except requests.exceptions.RequestException as e:
        print(f"   ! Error uploading to GitHub: {e}")
        return False


def run_sync():
    """Main sync function"""
    
    # Validate configuration
    if not all([USERNAME, PROJECT_KEY, GITHUB_TOKEN]):
        print("ERROR: Missing required environment variables")
        return
    
    # Get yesterday's date
    yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y%m%d')
    print(f"Targeting data for: {yesterday}")
    
    # Authenticate
    print("Authenticating with AmmonitOR...")
    token = get_token()
    
    if not token:
        print("ERROR: Failed to obtain authentication token")
        return
    
    print("✅ Authentication successful")
    
    # Process each device
    for folder, serial in DEVICE_MAP.items():
        print(f"\nChecking {folder} ({serial})...")
        
        # Get file list
        files = list_files(token, PROJECT_KEY, serial, "primary")
        
        if not files:
            print(f"   ! No files found for {serial}")
            continue
        
        # Find target file for yesterday
        target_file = next(
            (f for f in reversed(files) if f'_{yesterday}_' in f.get('original_filename', '')),
            None
        )
        
        if not target_file:
            print(f"   ! No file found for {yesterday}")
            continue
        
        filename = target_file['original_filename']
        print(f"   Found: {filename}")
        
        # Check if already on GitHub
        if check_github_file(REPO_PATH, folder, filename):
            print(f"   - Already exists on GitHub. Skipping.")
            continue
        
        # Download from AmmonitOR
        print(f"   Downloading from AmmonitOR...")
        csv_content = get_file_download(token, PROJECT_KEY, serial, filename, "primary")
        
        if not csv_content:
            print(f"   ❌ Failed to download file")
            continue
        
        # Upload to GitHub
        print(f"   Uploading to GitHub...")
        if upload_to_github(REPO_PATH, folder, filename, csv_content):
            print(f"   ✅ Successfully uploaded: {filename}")
        else:
            print(f"   ❌ Failed to upload {filename}")
    
    print("\n✅ Sync complete")


if __name__ == '__main__':
    run_sync()
