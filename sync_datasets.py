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

def get_entity_name_fields(df):
    """
    Determine which fields contain the entity names for a dataset (EN and FR variants).
    Returns a dict with 'en' and 'fr' keys, or empty dict if not found.
    Prioritize by likelihood: harmonized_name/nom_harmonise, legal_title/appellation_legale, preferred_name/nom_prefere
    """
    pairs = [
        ('harmonized_name', 'nom_harmonise'),
        ('legal_title', 'appellation_legale'),
        ('preferred_name', 'nom_prefere')
    ]
    for en_field, fr_field in pairs:
        if en_field in df.columns and fr_field in df.columns:
            return {'en': en_field, 'fr': fr_field}
        if en_field in df.columns:
            return {'en': en_field, 'fr': None}
        if fr_field in df.columns:
            return {'en': None, 'fr': fr_field}
    return {}

def update_html_with_changelogs(changelog_dir="changelogs", html_path="docs/index.html"):
    """
    Reads all changelog CSV files and updates the HTML file with embedded data.
    """
    try:
        # Get all changelog CSV files
        changelog_files = [f for f in os.listdir(changelog_dir) if f.endswith('_changelog.csv')]
        
        if not changelog_files:
            print("No changelog files found. Skipping HTML update.")
            return
        
        # Build embedded changelogs object
        embedded_data = {}
        for filename in sorted(changelog_files):
            filepath = os.path.join(changelog_dir, filename)
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    csv_content = f.read()
                embedded_data[filename] = csv_content
            except (IOError, OSError) as e:
                print(f"  -> Error reading {filename}: {e}")
                continue
        
        # Read the HTML file
        try:
            with open(html_path, 'r', encoding='utf-8') as f:
                html_content = f.read()
        except (IOError, OSError) as e:
            print(f"Error reading HTML file: {e}")
            return
        
        # Generate the new embedded data JavaScript
        js_code = "        // Embedded changelog data\n        const embeddedChangelogs = {\n"
        
        for filename, csv_content in embedded_data.items():
            # Escape special characters in CSV content for JavaScript string
            # Use backticks (template literals) to handle multi-line strings more easily
            escaped_content = csv_content.replace('\\', '\\\\').replace('`', '\\`')
            js_code += f"            '{filename}': `{escaped_content}`,\n"
        
        # Remove trailing comma from last entry
        js_code = js_code.rstrip(',\n') + '\n        };\n'
        
        # Find and replace the embedded data section
        # Look for the pattern: // Embedded changelog data ... const embeddedChangelogs = { ... };
        pattern = r'        // Embedded changelog data\s+const embeddedChangelogs = \{[^}]*\};'
        
        if re.search(pattern, html_content):
            html_content = re.sub(pattern, js_code.rstrip(), html_content)
            print(f"Updated HTML file with {len(embedded_data)} changelog(s).")
        else:
            print("Warning: Could not find embeddedChangelogs pattern in HTML. Skipping HTML update.")
            return
        
        # Write updated HTML
        try:
            with open(html_path, 'w', encoding='utf-8') as f:
                f.write(html_content)
            print(f"  -> Successfully updated {html_path}\n")
        except (IOError, OSError) as e:
            print(f"Error writing HTML file: {e}\n")
    except (IOError, OSError) as e:
        print(f"Error updating HTML with changelogs: {e}\n")


def sync_and_track_datasets(readme_path="README.md", output_dir="downloaded_datasets", changelog_dir="changelogs", html_path="docs/index.html"):
    """
    Downloads datasets and tracks changes in one unified process.
    """
    os.makedirs(output_dir, exist_ok=True)
    os.makedirs(changelog_dir, exist_ok=True)

    # Step 1: Parse README to find dataset links
    try:
        with open(readme_path, 'r', encoding='utf-8') as file:
            lines = file.readlines()
    except FileNotFoundError:
        print(f"Error: Could not find the file '{readme_path}'.")
        return

    datasets = []
    
    # Debug: print all lines with 'Dataset Link'
    print("DEBUG: All lines containing 'Dataset Link':")
    for i, line in enumerate(lines):
        if 'Dataset Link' in line:
            print(f"  Line {i+1}: {repr(line[:100])}")
    print()
    
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
                    print(f"DEBUG: Found dataset at line {i+1}: '{dataset_name}' -> {safe_name}")
                else:
                    print(f"DEBUG: No dataset name found for URL at line {i+1}: {download_url}")

    if not datasets:
        print("No datasets found in the README.")
        return

    print(f"Found {len(datasets)} dataset(s). Starting sync and tracking...\n")
    print("Datasets to process:")
    for filename, url in datasets:
        print(f"  - {filename}: {url}\n")
    timestamp = datetime.now().strftime('%Y-%m-%d')

    # Step 2: Download, compare, and track each dataset
    for index, (filename, url) in enumerate(datasets, start=1):
        filepath = os.path.join(output_dir, filename)
        changelog_path = os.path.join(changelog_dir, filename.replace('.csv', '_changelog.csv'))
        
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
            
            # Determine the entity name fields for this dataset
            entity_name_fields = get_entity_name_fields(new_df)
            
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
                        "new_value": "",
                        "entity_name_en": "",
                        "entity_name_fr": ""
                    }
                    
                    if row['_merge'] == 'left_only':
                        entry["event"] = "DELETED"
                        if entity_name_fields.get('en'):
                            entry["entity_name_en"] = str(row[f"{entity_name_fields['en']}_old"]) if f"{entity_name_fields['en']}_old" in row else str(row[entity_name_fields['en']])
                        if entity_name_fields.get('fr'):
                            entry["entity_name_fr"] = str(row[f"{entity_name_fields['fr']}_old"]) if f"{entity_name_fields['fr']}_old" in row else str(row[entity_name_fields['fr']])
                        changelog_entries.append(entry)
                    elif row['_merge'] == 'right_only':
                        entry["event"] = "ADDED"
                        if entity_name_fields.get('en'):
                            entry["entity_name_en"] = str(row[entity_name_fields['en']])
                        if entity_name_fields.get('fr'):
                            entry["entity_name_fr"] = str(row[entity_name_fields['fr']])
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
                                if entity_name_fields.get('en'):
                                    change_entry["entity_name_en"] = str(row[f"{entity_name_fields['en']}_new"])
                                if entity_name_fields.get('fr'):
                                    change_entry["entity_name_fr"] = str(row[f"{entity_name_fields['fr']}_new"])
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
                    print("  -> No changes detected.")
            else:
                print("  -> First time tracking this dataset. Baseline saved.")
            
            # Save the new version
            new_df.to_csv(filepath, index=False)
            print(f"  -> Successfully saved to: {filepath}\n")
            
        except requests.exceptions.RequestException as e:
            print(f"  -> Failed to download. Error: {e}\n")
        except (OSError, pd.errors.ParserError, KeyError, ValueError) as e:
            print(f"  -> Error processing dataset: {e}\n")
    
    # Update HTML with changelog data
    print("Updating HTML with changelog data...")
    update_html_with_changelogs(changelog_dir, html_path)

if __name__ == "__main__":
    sync_and_track_datasets(readme_path="README.md")
