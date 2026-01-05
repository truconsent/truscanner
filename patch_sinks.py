import json
import os
from pathlib import Path

def patch_sinks(sinks_dir):
    sinks_path = Path(sinks_dir)
    if not sinks_path.exists():
        print(f"Error: {sinks_dir} not found.")
        return

    type_map = {
        "storages": "Database",
        "third_parties": "Third Party",
        "leakages": "Leakage",
        "internal_apis": "Internal API",
        "miscellaneous": "Miscellaneous Storage"
    }

    count = 0
    for json_file in sinks_path.rglob("*.json"):
        try:
            # Skip the ones I manually created if they are already correct
            # Actually, just process all for consistency
            
            with open(json_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            modified = False
            # Determine type based on directory
            # e.g. sinks/storages/postgres/javascript.json -> folder_name is 'storages'
            # We need to find the parent folder that is directly under 'sinks'
            parts = json_file.parts
            try:
                sinks_idx = parts.index('sinks')
                if len(parts) > sinks_idx + 1:
                    folder_name = parts[sinks_idx + 1]
                    # If it's a file directly in 'sinks', folder_name will be the filename
                    # but rglob("*.json") will include files in sinks/ folder
                    if folder_name.endswith('.json'):
                        # Top level file, use a default or keep existing
                        sink_type = "Database" # Default for my manual ones
                    else:
                        sink_type = type_map.get(folder_name, "Generic Storage")
                else:
                    sink_type = "Database"
            except ValueError:
                sink_type = "Database"

            for source in data.get("sources", []):
                if "tags" not in source:
                    source["tags"] = {}
                
                # Update type if it's missing or generic
                if source["tags"].get("type") in [None, "Generic Storage", "Browser Storage", "Cookie Storage", "File System", "Mobile Storage"]:
                    # Keep my specific ones if they relate to my manual files
                    if json_file.name in ["database.json", "cookies.json", "web_storage.json", "file_io.json", "app_storage.json"]:
                        continue
                    
                    source["tags"]["type"] = sink_type
                    modified = True
            
            if modified:
                with open(json_file, 'w', encoding='utf-8') as f:
                    json.dump(data, f, indent=4)
                count += 1
                
        except Exception as e:
            print(f"Error patching {json_file}: {e}")

    print(f"Successfully patched {count} sink JSON files.")

if __name__ == "__main__":
    patch_sinks("sinks")
