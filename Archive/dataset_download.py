import os
import re
import requests

def sanitize_filename(name):
    """
    Cleans up the parsed text to create a safe, valid filename.
    """
    # Remove markdown formatting characters like bolding or bullets
    name = re.sub(r'[\*\#\-]', '', name).strip()
    # Remove invalid characters for file paths (\ / : * ? " < > |)
    name = re.sub(r'[\\/*?:"<>|]', '', name)
    # Replace spaces with underscores for cleaner filenames
    name = name.replace(' ', '_')
    
    # Ensure it has a .csv extension
    if not name.lower().endswith('.csv'):
        name += '.csv'
        
    return name

def download_datasets_from_readme(readme_path="README.md", output_dir="downloaded_datasets"):
    """
    Parses a README file line-by-line to extract dataset names and links, 
    then downloads them.
    """
    os.makedirs(output_dir, exist_ok=True)

    try:
        with open(readme_path, 'r', encoding='utf-8') as file:
            lines = file.readlines()
    except FileNotFoundError:
        print(f"Error: Could not find the file '{readme_path}'.")
        return

    datasets = []

    # Step 1: Parse the file to find names and URLs
    for i, line in enumerate(lines):
        clean_line = line.strip()
        
        # Look for Dataset Link lines with resource IDs
        if 'Dataset Link:' in line:
            # Extract the resource ID from the URL (last part of the path)
            resource_match = re.search(r'/resource/([a-f0-9\-]+)', line)
            if resource_match:
                resource_id = resource_match.group(1)
                # Construct the download URL in the correct format
                download_url = f'https://open.canada.ca/data/datastore/dump/{resource_id}?bom=True'
                
                # Search backwards to find the dataset name (first non-empty line before Dataset Link)
                dataset_name = None
                for j in range(i - 1, -1, -1):
                    prev_line = lines[j].strip()
                    if prev_line and 'Type:' not in prev_line and 'Dataset Link:' not in prev_line and 'URL:' not in prev_line and 'Resources' not in prev_line:
                        dataset_name = prev_line
                        break
                
                if dataset_name:
                    safe_name = sanitize_filename(dataset_name)
                    datasets.append((safe_name, download_url))

    # Step 2: Download the matched datasets
    if not datasets:
        print("No matching dataset blocks were found in the README.")
        return

    print(f"Found {len(datasets)} dataset(s). Starting downloads...\n")

    for index, (filename, url) in enumerate(datasets, start=1):
        filepath = os.path.join(output_dir, filename)
        
        try:
            print(f"[{index}/{len(datasets)}] Downloading '{filename}'...")
            print(f"  URL: {url}")
            
            response = requests.get(url, stream=True, timeout=30)
            response.raise_for_status()

            # Write the file in chunks to handle large datasets safely
            with open(filepath, 'wb') as out_file:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        out_file.write(chunk)
                        
            print(f"  -> Successfully saved to: {filepath}\n")

        except requests.exceptions.RequestException as e:
            print(f"  -> Failed to download. Error: {e}\n")

if __name__ == "__main__":
    download_datasets_from_readme(readme_path="README.md")