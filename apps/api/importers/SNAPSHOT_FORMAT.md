# Notion snapshot format (data/import/notion_snapshot.json — git-ignored)

Keys: `fetched_at`; `clinics[{id,name}]`; `records[{id,title,date,created_time,last_edited_time,details,doctors_note,clinic_ids,medications,body_markdown}]`; `analyses[{id,name,value,reference_range,date,record_ids}]`; `medications[{id,name,dosage,start,end,notes,record_ids}]`. Ids are Notion page ids. Run: `uv run alembic upgrade head && uv run python -m importers.notion_import ../../data/import/notion_snapshot.json`. Re-runnable.
