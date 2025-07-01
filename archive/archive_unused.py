import os
import shutil
from pathlib import Path

# Set this to your actual project folder
base_path = Path(__file__).resolve().parent
archive_path = base_path / "archive"
archive_path.mkdir(exist_ok=True)

# Define individual files to archive
files_to_archive = [
    "get-pip.py",
    "patch_test.py",
    "ollama.log",
    "batch_test_results.json",
    "validators_backup.py",
    "test_validators_backup.py"
]

# Define filename patterns to archive
patterns_to_archive = [
    "prompts_duplicate_*.json"
]

# Move explicitly listed files
for fname in files_to_archive:
    src = base_path / fname
    if src.exists():
        print(f"Archiving {fname}")
        shutil.move(str(src), str(archive_path / src.name))

# Move files matching wildcard patterns
for pattern in patterns_to_archive:
    for match in base_path.glob(pattern):
        print(f"Archiving {match.name}")
        shutil.move(str(match), str(archive_path / match.name))

print("✅ Archive complete. All specified files moved to /archive/")
