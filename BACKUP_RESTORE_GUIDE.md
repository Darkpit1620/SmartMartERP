# SmartMart ERP — Backups and safe restore practice

## Make a verified, private backup

With the server stopped if possible:

```powershell
cd "C:\Users\USER\Documents\assignment\New folder\SmartMartERP"
python smartmart_backup.py
```

The script uses SQLite's online backup API, checks database integrity, and copies files in `media/` if that folder exists. It creates a `manifest.json` with SHA-256 hashes to detect corruption or alteration. Backups are placed **outside the repository**, under your Windows Documents folder by default.

To verify an existing backup:

```powershell
python smartmart_backup.py --verify "C:\Users\USER\Documents\SmartMartERP_Backups\SmartMart_Backup_YYYYMMDD_HHMMSS_XXXXXX"
```

This checks file hashes and database integrity. It does **not** prove your Django app can restore and serve valid POS/stock transactions. For that, test restoring a copy in an isolated test project/database, then run Django checks and sample workflows. Do not restore over live data merely to test a backup.

## Security and GitHub

Backups contain personally identifiable and commercial records, possibly receipt and supplier data. Keep backups encrypted, restrict access, retain offsite copies, and never upload them or `db.sqlite3` to a public repository. `.gitignore` does not remove files already tracked: untrack any previously committed sensitive files and rotate leaked credentials.

## PostgreSQL

This script is specifically for your current **SQLite** installation. Once SmartMart ERP is migrated to PostgreSQL, use a properly configured PostgreSQL backup tool such as `pg_dump`/managed snapshots, point-in-time recovery and a documented restore test. Do not run this SQLite backup tool as if it backed up PostgreSQL.
