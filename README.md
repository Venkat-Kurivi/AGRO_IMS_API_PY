# AGRO Inventory API (FastAPI)

Python migration of the AGRO Inventory ASP.NET API, using domain, application, infrastructure, and API layers. CQRS request types keep read and write operations separate; SQLAlchemy repositories own persistence and stock transactions.

## Run

Create a virtual environment, install `requirements.txt`, copy `.env.example` to `.env`, and set a unique `JWT_SECRET` and `INITIAL_ADMIN_PASSWORD`. Then start the API:

```powershelluvicorn app.main:app --reload
uvicorn app.main:app --reload
```

Interactive API documentation is available at `/docs`; health check is `/health`. The initial development admin username and password default to `admin` / `admin123`; change them before exposing the service. Existing plaintext .NET passwords are not reused as hashes; the Python app creates a fresh admin credential on an empty database.

The SQLAlchemy models use the normalized relational tables in `database/AGRO_IMS_POSTGRESQL.sql`. Create the database and apply the script, then set `DATABASE_URL` in `.env`:

```powershell
createdb agro_ims
psql -d agro_ims -f database/AGRO_IMS_POSTGRESQL.sql
```

The example file shows the PostgreSQL connection URL. SQLite remains available for local tests. SQL Server connections are also supported through `mssql+pyodbc` when the Microsoft ODBC Driver is installed. Passwords are stored as hashes and the app provisions the initial administrator at startup.

The SQL script creates repeatable reference data but does not migrate live SQL Server transactions or plaintext user passwords. Export/import existing records separately and reissue or securely hash user credentials before cutover.

## API

Authenticate with `POST /api/auth/login`, then pass the returned bearer token to `/api/inventory/*`. The inventory route family preserves branch, brand, category, subcategory, customer, vendor, product, user, stock, transaction, purchase order/receipt, sale/return, and dashboard operations from the .NET controller. Mutating user records requires an Admin token.

## Verify

```powershell
pytest
```