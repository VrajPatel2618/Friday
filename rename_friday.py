import os
import re

dir_path = r"c:\Users\Lenovo\Downloads\Model"

for root, dirs, files in os.walk(dir_path):
    if '__pycache__' in root or '.git' in root or 'screenshots' in root or 'known_faces' in root:
        continue
    for file in files:
        if file.endswith(('.py', '.md', '.txt', '.bat', '.json')):
            filepath = os.path.join(root, file)
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    content = f.read()
            except Exception as e:
                print(f"Could not read {file}")
                continue
            
            new_content = re.sub(r'\bJARVIS\b', 'FRIDAY', content)
            new_content = re.sub(r'\bJarvis\b', 'Friday', new_content)
            new_content = re.sub(r'\bjarvis\b', 'friday', new_content)
            
            if new_content != content:
                with open(filepath, 'w', encoding='utf-8') as f:
                    f.write(new_content)
                print(f"Updated {file}")

# rename json file
old_json = os.path.join(dir_path, 'jarvis_memory.json')
new_json = os.path.join(dir_path, 'friday_memory.json')
if os.path.exists(old_json):
    os.rename(old_json, new_json)
    print("Renamed jarvis_memory.json to friday_memory.json")
