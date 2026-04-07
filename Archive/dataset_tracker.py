import pandas as pd
import os
import subprocess
from io import StringIO
from datetime import datetime

def track_changes(dataset_name, new_csv_path, changelog_path="changelog.json"):
    # 1. Load the new file and the 'current' file (from the last commit)
    new_df = pd.read_csv(
        new_csv_path, 
        on_bad_lines='skip',  # Skips the lines causing the crash
        sep=None,             # Automatically detects if it's a comma or semicolon
        engine='python',      # Required when using sep=None
        encoding='utf-8-sig'  # Handles the 'BOM' character often found in GC files
    ).fillna("")
    pk = new_df.columns[0] # Assuming first column is the Primary Key (e.g., GC OrgID)
    
    # If the file doesn't exist yet (first run), just save and exit
    current_repo_path = f"downloaded_datasets/{dataset_name}.csv"
    if not os.path.exists(current_repo_path):
        new_df.to_csv(current_repo_path, index=False)
        return

    # Load the old version from git (HEAD) before the files were overwritten
    try:
        old_content = subprocess.run(
            ['git', 'show', f'HEAD:{current_repo_path}'],
            capture_output=True,
            text=True,
            check=False
        )
        if old_content.returncode == 0:
            old_df = pd.read_csv(StringIO(old_content.stdout)).fillna("")
        else:
            # File doesn't exist in git history, treat as new
            new_df.to_csv(current_repo_path, index=False)
            return
    except Exception as e:
        print(f"Error reading git history for {dataset_name}: {e}")
        new_df.to_csv(current_repo_path, index=False)
        return

    # 2. Compare DataFrames
    merged = old_df.merge(new_df, on=pk, suffixes=('_old', '_new'), how='outer', indicator=True)
    
    new_entries = []
    timestamp = datetime.now().strftime('%Y-%m-%d') # Using ISO 8601

    for _, row in merged.iterrows():
        entry = {
            "date": timestamp,
            "dataset": dataset_name,
            "id": str(row[pk]),
            "changes": []
        }

        if row['_merge'] == 'left_only':
            entry["event"] = "DELETED"
            new_entries.append(entry)
        elif row['_merge'] == 'right_only':
            entry["event"] = "ADDED"
            new_entries.append(entry)
        else:
            # Check for value updates in columns
            for col in new_df.columns:
                if col == pk: continue
                old_val = str(row[f"{col}_old"])
                new_val = str(row[f"{col}_new"])
                if old_val != new_val:
                    entry["changes"].append({
                        "field": col,
                        "old": old_val,
                        "new": new_val
                    })
            
            if entry["changes"]:
                entry["event"] = "UPDATED"
                new_entries.append(entry)

    # 3. Update the CSV Changelog
    if new_entries:
        changelog_rows = []
        for entry in new_entries:
            if entry["event"] in ["DELETED", "ADDED"]:
                changelog_rows.append({
                    "date": entry["date"],
                    "dataset": entry["dataset"],
                    "id": entry["id"],
                    "event": entry["event"],
                    "field": "",
                    "old_value": "",
                    "new_value": ""
                })
            else:  # UPDATED
                for change in entry["changes"]:
                    changelog_rows.append({
                        "date": entry["date"],
                        "dataset": entry["dataset"],
                        "id": entry["id"],
                        "event": entry["event"],
                        "field": change["field"],
                        "old_value": change["old"],
                        "new_value": change["new"]
                    })
        
        changelog_df = pd.DataFrame(changelog_rows)
        
        # Append to existing changelog or create new one
        if os.path.exists(changelog_path):
            changelog_df.to_csv(changelog_path, mode='a', header=False, index=False)
        else:
            changelog_df.to_csv(changelog_path, index=False)

    # 4. Overwrite the 'current' file so Git can track the file change itself
    new_df.to_csv(current_repo_path, index=False)

if __name__ == "__main__":
    # Automatically process all downloaded CSV files
    download_dir = "downloaded_datasets"
    if os.path.exists(download_dir):
        for filename in os.listdir(download_dir):
            if filename.endswith('.csv'):
                filepath = os.path.join(download_dir, filename)
                # Use the filename (without .csv) as the dataset name
                dataset_name = filename.replace('.csv', '')
                print(f"Tracking changes for: {dataset_name}")
                changelog_path = f"{dataset_name}_changelog.json"
                track_changes(dataset_name, filepath, changelog_path)