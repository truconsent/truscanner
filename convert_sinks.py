import yaml
import json
import os
from pathlib import Path

def convert_yaml_to_json(sinks_dir):
    sinks_path = Path(sinks_dir)
    if not sinks_path.exists():
        print(f"Error: {sinks_dir} not found.")
        return

    count = 0
    for yaml_file in sinks_path.rglob("*.yaml"):
        try:
            with open(yaml_file, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f)
            
            if not data or 'sinks' not in data:
                continue
            
            json_sources = []
            
            # Determine type based on directory
            folder_name = yaml_file.parent.parent.name if yaml_file.parent.parent.name != 'sinks' else yaml_file.parent.name
            type_map = {
                "storages": "Database",
                "third_parties": "Third Party",
                "leakages": "Leakage",
                "internal_apis": "Internal API",
                "miscellaneous": "Miscellaneous Storage"
            }
            sink_type = type_map.get(folder_name, "Generic Storage")

            for sink in data['sinks']:
                source = {
                    "name": sink.get('name', yaml_file.parent.name),
                    "category": "Storage Sink",
                    "patterns": sink.get('patterns', []),
                    "tags": {
                        "id": sink.get('id', ''),
                        "type": sink_type,
                        "language": yaml_file.stem,
                        "technology": yaml_file.parent.name
                    }
                }
                # Add any other tags if present
                if 'tags' in sink and sink['tags']:
                    source['tags'].update(sink['tags'])
                
                json_sources.append(source)
            
            if json_sources:
                json_output = {"sources": json_sources}
                json_file = yaml_file.with_suffix(".json")
                with open(json_file, 'w', encoding='utf-8') as f:
                    json.dump(json_output, f, indent=4)
                
                # Delete the original YAML file
                os.remove(yaml_file)
                count += 1
                
        except Exception as e:
            print(f"Error converting {yaml_file}: {e}")

    print(f"Successfully converted {count} YAML files to JSON.")

if __name__ == "__main__":
    convert_yaml_to_json("sinks")
