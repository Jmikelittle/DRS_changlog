import os
import re
import requests
import pandas as pd
from datetime import datetime
from io import StringIO

def sanitize_filename(name):
    """
    Cleans up the parsed text to create a safe, valid filename.
    """
    name = re.sub(r'[\*\#\-]', '', name).strip()
    name = re.sub(r'[\\/*?:"<>|]', '', name)
    name = name.replace(' ', '_')
    
    if not name.lower().endswith('.csv'):
        name += '.csv'
    return name

def sync_and_track_datasets(readme_path="README.md", output_dir="downloaded_datasets"):
    """
    Downloads datasets and tracks changes in one unified process.
    """
    os.makedirs(output_dir, exist_ok=True)

    # Step 1: Parse README to find dataset links
    try:
        with open(readme_path, 'r', encoding='utf-8') as file:
            lines = file.readlines()
    except FileNotFoundError:
        print(f"Error: Could not find the file '{readme_path}'.")
        return

    datasets = []
    
    for i, line in enumerate(lines):
        if 'Dataset Link:' in line:
            # Extract the URL from the line
            url_match = re.search(r'(https?://[^\s\'">\]]+)', line)
            if url_match:
                download_url = url_match.group(1)
                
                dataset_name = None
                for j in range(i - 1, -1, -1):
                    prev_line = lines[j].strip()
                    if prev_line and 'Type:' not in prev_line and 'Dataset Link:' not in prev_line and 'URL:' not in prev_line and 'Resources' not in prev_line:
                        dataset_name = prev_line
                        break
                
                if dataset_name:
                    safe_name = sanitize_filename(dataset_name)
                    datasets.append((safe_name, download_url))

    if not datasets:
        print("No datasets found in the README.")
        return

    print(f"Found {len(datasets)} dataset(s). Starting sync and tracking...\n")
    timestamp = datetime.now().strftime('%Y-%m-%d')

    # Step 2: Download, compare, and track each dataset
    for index, (filename, url) in enumerate(datasets, start=1):
        filepath = os.path.join(output_dir, filename)
        changelog_path = os.path.join(output_dir, filename.replace('.csv', '_changelog.csv'))
        
        print(f"[{index}/{len(datasets)}] Processing '{filename}'...")
        print(f"  Downloading from: {url}")
        
        try:
            # Download new dataset
            response = requests.get(url, stream=True, timeout=30)
            response.raise_for_status()
            
            new_content = response.text
            new_df = pd.read_csv(
                StringIO(new_content),
                on_bad_lines='skip',
                sep=None,
                engine='python',
                encoding='utf-8'
            ).fillna("")
            
            # Check if old version exists
            changelog_entries = []
            if os.path.exists(filepath):
                # Load old version for comparison
                old_df = pd.read_csv(filepath).fillna("")
                
                # Compare datasets
                pk = new_df.columns[0]
                merged = old_df.merge(new_df, on=pk, suffixes=('_old', '_new'), how='outer', indicator=True)
                
                for _, row in merged.iterrows():
                    entry = {
                        "date": timestamp,
                        "dataset": filename.replace('.csv', ''),
                        "id": str(row[pk]),
                        "event": "",
                        "field": "",
                        "old_value": "",
                        "new_value": ""
                    }
                    
                    if row['_merge'] == 'left_only':
                        entry["event"] = "DELETED"
                        changelog_entries.append(entry)
                    elif row['_merge'] == 'right_only':
                        entry["event"] = "ADDED"
                        changelog_entries.append(entry)
                    else:
                        # Check for value updates
                        for col in new_df.columns:
                            if col == pk:
                                continue
                            old_val = str(row[f"{col}_old"])
                            new_val = str(row[f"{col}_new"])
                            if old_val != new_val:
                                change_entry = entry.copy()
                                change_entry["event"] = "UPDATED"
                                change_entry["field"] = col
                                change_entry["old_value"] = old_val
                                change_entry["new_value"] = new_val
                                changelog_entries.append(change_entry)
                
                # Write changelog entries if any exist
                if changelog_entries:
                    changelog_df = pd.DataFrame(changelog_entries)
                    if os.path.exists(changelog_path):
                        changelog_df.to_csv(changelog_path, mode='a', header=False, index=False)
                        print(f"  -> Found {len(changelog_entries)} change(s). Updated {os.path.basename(changelog_path)}")
                    else:
                        changelog_df.to_csv(changelog_path, index=False)
                        print(f"  -> Found {len(changelog_entries)} change(s). Created {os.path.basename(changelog_path)}")
                else:
                    print(f"  -> No changes detected.")
            else:
                print(f"  -> First time tracking this dataset. Baseline saved.")
            
            # Save the new version
            new_df.to_csv(filepath, index=False)
            print(f"  -> Successfully saved to: {filepath}\n")
            
        except requests.exceptions.RequestException as e:
            print(f"  -> Failed to download. Error: {e}\n")
        except Exception as e:
            print(f"  -> Error processing dataset: {e}\n")

if __name__ == "__main__":
    sync_and_track_datasets(readme_path="README.md")
