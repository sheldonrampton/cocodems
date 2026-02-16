# Database schema (imported by `create_database.py`)

This document describes the purpose of the Postgres tables created by `create_database.py`.

`create_database.py` reads Excel workbooks in `fixed_data/` and imports them into Postgres using Pandas/SQLAlchemy. Each table is written with `if_exists="replace"`, so running the script **replaces the entire contents** of the corresponding table.

## Notes

- The **authoritative column set** for each table is whatever exists in the corresponding `fixed_data/*.xlsx` sheet at import time.
- The script enforces a few column types (see below). Other columns are inferred by Pandas.
- ID columns are typically integers and are intended to be stable keys for joins.

## Entity relationship overview

At a high level:

- `jurisdictions` and `offices` define *where* a race is held and *what* the office is.
- `races` represents a specific contest (an office in a jurisdiction, often tied to an election date).
- `elections` represents an election event/date (e.g., Spring Election 2024).
- `campaigns` ties together a race with metadata used for organizing outreach.
- `individuals` stores people (typically candidates and/or officeholders, depending on how `fixed_data/individuals.xlsx` is maintained).
- `office_names` stores name normalization / aliases for offices.

## Tables

### `campaigns`

**Purpose**

A planning/operations table used to track Democratic campaign/outreach activity for a given contest.

**Key columns (known/expected)**

- `race_id` (int)
  - Foreign key to `races`.
- `jurisdiction_id` (int)
  - Foreign key to `jurisdictions`.
- `office_id` (int)
  - Foreign key to `offices`.

**Relationships**

- Many `campaigns` rows can refer to the same `race_id` depending on how campaigns are modeled.
- A `campaigns` row should generally be consistent with the referenced `race_id`’s jurisdiction/office.

**Type enforcement in `create_database.py`**

- Casts `race_id`, `jurisdiction_id`, `office_id` to `int64`.

### `elections`

**Purpose**

Represents election events/dates (e.g., Spring Election, Fall General Election), typically used to group races by cycle.

**Key columns**

Not enforced by the script. Common patterns (depending on the workbook) might include:

- an integer `id`
- an election date field
- election name/type (spring/fall/primary/general)

### `races`

**Purpose**

Represents a contest that appears on the ballot: an office being elected within a jurisdiction, usually for a particular election.

This is a core table for relating extracted election results to operational data.

**Key columns**

Not enforced by the script, but often includes:

- an integer `id`
- `race_name` (human readable label)
- foreign keys to `elections`, `jurisdictions`, and `offices`
- seat count / term length / district/branch indicators

**Related utilities**

- `fix_uniques.py` generates `races_fixed.xlsx` by adding an `office_ordinal` column to disambiguate duplicated `race_name` values. If you see duplicated race names (e.g., multiple seats or multiple districts), `office_ordinal` can be used as an additional discriminator.

### `individuals`

**Purpose**

Stores person records used by downstream tools (e.g., candidates, officeholders, campaign contacts).

**Key columns (known/expected)**

Not enforced beyond a few string casts. Likely includes:

- an integer `id`
- `first_name`, `last_name` (or a full name)
- contact fields

**Type enforcement in `create_database.py`**

The script explicitly casts the following columns to strings (if present):

- `email`
- `phone`
- `address`
- `city`
- `state`
- `zip`

This avoids issues where Excel/pandas interpret values like ZIP codes or phone numbers as numbers and strip leading zeros.

### `jurisdictions`

**Purpose**

Master list of jurisdictions used across the dataset: municipalities, towns, villages, school districts, county-level entities, etc.

This table exists to normalize jurisdiction naming and provide a stable key for joins.

**Type enforcement in `create_database.py`**

Casts the following columns to strings (if present):

- `email`
- `phone`
- `address`
- `city`
- `state`
- `zip`
- `website`

### `office_names`

**Purpose**

Office name normalization / alias table.

Use this when you need to map multiple human-readable office labels to a canonical office record (for example, differences in county report formatting across years).

**Key columns**

Not enforced by the script, but commonly includes:

- an integer `id`
- canonical office name
- alternate/alias office names

### `offices`

**Purpose**

Master list of elected offices (e.g., Mayor, Alderperson District 1, County Supervisor District 10, Circuit Court Judge Branch 3).

This table is used to normalize office naming and provide a stable key for joins.

**Type enforcement in `create_database.py`**

Casts the following columns to strings (if present):

- `email`
- `phone`
- `address`
- `city`
- `state`
- `zip`
- `website`

## Operational considerations

- Running `create_database.py` is **destructive** for the imported tables because of `if_exists="replace"`.
- The script currently prints the full Postgres connection string (`DB_URI`), which may include credentials.
