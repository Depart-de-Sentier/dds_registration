# Demo data fixtures

To install test data (for local testting), use:

```
python manage.py loaddata site-local test-users test-event test-options
```

To add test registration object:

```
python manage.py loaddata test-registration
```

Admin and the first user creating with `test` password.

To quickly remove migrations and dev.time db, use:

```
rm -Rvf dds_registration/migrations/* db.sqlite3 && touch dds_registration/migrations/__init__.py
```
