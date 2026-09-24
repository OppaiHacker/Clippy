import argparse
import sys
from pathlib import Path
from backend.app.config import settings
from backend.app.database import get_sync_db
from backend.app.services.ingest import ingest_clip
from backend.app.services.trash import trash_missing

def scan_clips():
    clips_dir = settings.clips_dir
    if not clips_dir.exists():
        print(f"Clips directory does not exist: {clips_dir}")
        return

    mp4_files = sorted(list(clips_dir.glob("*.mp4")))
    print(f"Found {len(mp4_files)} mp4 clips in {clips_dir}")

    with get_sync_db() as db:
        for idx, file_path in enumerate(mp4_files, 1):
            print(f"[{idx}/{len(mp4_files)}] Ingesting {file_path.name}...")
            try:
                clip = ingest_clip(file_path, db)
                print(f"  ✓ ID {clip.id}: {clip.game or 'No Game'} ({clip.duration_s:.1f}s, {len(clip.audio_tracks)} tracks)")
            except Exception as e:
                # without a rollback the session stays poisoned and every following clip fails
                db.rollback()
                print(f"  ✗ Error ingesting {file_path.name}: {e}", file=sys.stderr)

        trashed = trash_missing(db)
        if trashed:
            print(f"Moved {trashed} clip(s) with missing files to trash")

    print("Scan finished!")

def main():
    parser = argparse.ArgumentParser(description="Clippy CLI")
    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser("scan", help="Scan clips directory and ingest new/updated clips")

    args = parser.parse_args()
    if args.command == "scan":
        scan_clips()
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
