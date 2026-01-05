---
description: Update Production Environment
---

1. Pull the latest code
```bash
git pull
```

2. Upgrade the database to the current head
```bash
flask db upgrade
```

3. Generate new migrations (if any schema changes were made)
```bash
flask db migrate -m "production_update"
```

4. Apply the new migrations
```bash
flask db upgrade
```

> [!TIP]
> If you encounter "Multiple head revisions", run:
> ```bash
> flask db merge heads -m "merge_heads"
> flask db upgrade
> ```

5. Restart the application service
```bash
sudo systemctl restart patient_accounting
```
