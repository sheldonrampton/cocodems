from flask import Flask, render_template, request, redirect, url_for, send_file
import psycopg2
from psycopg2.extras import RealDictCursor
import os
from dotenv import load_dotenv
from datetime import datetime
from datetime import date, timedelta
import calendar
import subprocess
import tempfile
import shutil
import csv
import io
import re

_shared_dotenv_path = os.getenv(
    "COCODEMS_ENV_FILE",
    os.path.expanduser("~/.config/cocodems_elections/.env"),
)
if os.path.exists(_shared_dotenv_path):
    load_dotenv(dotenv_path=_shared_dotenv_path, override=True)
else:
    load_dotenv(override=True)

app = Flask(__name__)

# Sheldon's comment: I'm using environment variables to store the database credentials
# Database configuration (replace with your own credentials)
DATABASE = {
    'dbname': os.getenv('DB_NAME'),
    'user': os.getenv('DB_USER'),
    'password': os.getenv('DB_PASSWORD'),
    'host': os.getenv('DB_HOST'),
    'port': os.getenv('DB_PORT')
}

def get_db_connection():
    """Establish connection to the PostgreSQL database."""
    conn = psycopg2.connect(**DATABASE)
    return conn


def _admin_token_is_valid(req) -> bool:
    expected = os.getenv('ADMIN_TOKEN')
    if not expected:
        return False

    supplied = (
        (req.headers.get('X-Admin-Token') or '').strip()
        or (req.args.get('token') or '').strip()
        or (req.form.get('admin_token') or '').strip()
    )
    return bool(supplied) and supplied == expected


def _pg_env() -> dict:
    env = os.environ.copy()
    if DATABASE.get('password'):
        env['PGPASSWORD'] = str(DATABASE['password'])
    if os.getenv('PGSSLMODE'):
        env['PGSSLMODE'] = os.getenv('PGSSLMODE')
    return env


def _preferred_bin(explicit_env_var: str, default_name: str, brew_opt_path: str) -> str:
    override = (os.getenv(explicit_env_var) or '').strip()
    if override:
        return override

    # Prefer a version-matched Homebrew client if present.
    if os.path.exists(brew_opt_path):
        return brew_opt_path

    found = shutil.which(default_name)
    return found or default_name


_BACKUP_TABLES = [
    'public.campaigns',
    'public.elections',
    'public.individuals',
    'public.jurisdictions',
    'public.office_names',
    'public.offices',
    'public.races',
]


@app.route('/admin')
def admin():
    """Render the admin page."""
    return render_template('admin.html')


@app.route('/enhance_individuals', methods=['POST'])
def enhance_individuals():
    if not _admin_token_is_valid(request):
        return "Forbidden", 403

    conn = get_db_connection()
    updated = 0
    skipped_no_campaign = 0
    skipped_infer_failed = 0

    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(
                """
                SELECT contact_id
                FROM individuals
                WHERE city IS NULL OR city = '';
                """
            )
            individuals = cursor.fetchall()

            for ind in individuals:
                contact_id = ind['contact_id']
                cursor.execute(
                    """
                    SELECT jurisdiction
                    FROM campaigns
                    WHERE contact_id = %s
                    ORDER BY election_date DESC NULLS LAST
                    LIMIT 1;
                    """,
                    (contact_id,),
                )
                crow = cursor.fetchone()
                if not crow:
                    skipped_no_campaign += 1
                    continue

                jurisdiction = (crow.get('jurisdiction') or '').strip()
                if not jurisdiction:
                    skipped_no_campaign += 1
                    continue

                inferred = _infer_city_from_jurisdiction(jurisdiction)
                city = inferred or jurisdiction
                if not city:
                    skipped_infer_failed += 1
                    continue

                cursor.execute(
                    """
                    UPDATE individuals
                    SET city = %s
                    WHERE contact_id = %s;
                    """,
                    (city, contact_id),
                )
                if cursor.rowcount:
                    updated += 1

        conn.commit()
    except Exception as e:
        conn.rollback()
        conn.close()
        return f"Error enhancing individuals: {e}", 500

    conn.close()

    message = (
        f"Enhance individuals complete. Updated: {updated}. "
        f"Skipped (no campaign/jurisdiction): {skipped_no_campaign}. "
        f"Skipped (could not infer): {skipped_infer_failed}."
    )
    return render_template('admin.html', message=message)


@app.route('/admin/backup', methods=['POST'])
def admin_backup():
    """Create a SQL backup and return it as a download."""
    if not _admin_token_is_valid(request):
        return "Forbidden", 403

    with tempfile.NamedTemporaryFile(prefix='cocodems_backup_', suffix='.sql', delete=False) as tf:
        backup_path = tf.name

    try:
        pg_dump_bin = _preferred_bin('PG_DUMP_BIN', 'pg_dump', '/opt/homebrew/opt/postgresql@16/bin/pg_dump')
        cmd = [
            pg_dump_bin,
            '-h', str(DATABASE.get('host') or ''),
            '-p', str(DATABASE.get('port') or ''),
            '-U', str(DATABASE.get('user') or ''),
            '-d', str(DATABASE.get('dbname') or ''),
            '--no-owner',
            '--no-privileges',
            '--clean',
            '--if-exists',
            '-f', backup_path,
        ]
        for t in _BACKUP_TABLES:
            cmd.extend(['--table', t])
        subprocess.run(cmd, check=True, env=_pg_env(), capture_output=True, text=True)

        download_name = f"{DATABASE.get('dbname') or 'database'}_backup.sql"
        return send_file(backup_path, as_attachment=True, download_name=download_name)
    except subprocess.CalledProcessError as e:
        try:
            os.unlink(backup_path)
        except Exception:
            pass
        detail = (e.stderr or e.stdout or str(e)).strip()
        return f"Error creating backup: {detail}", 500
    except Exception as e:
        try:
            os.unlink(backup_path)
        except Exception:
            pass
        return f"Error creating backup: {e}", 500


@app.route('/admin/reload', methods=['POST'])
def admin_reload():
    """Reload the database from an uploaded SQL dump (destructive)."""
    if not _admin_token_is_valid(request):
        return "Forbidden", 403

    backup_file = request.files.get('backup_file')
    if not backup_file:
        return render_template('admin.html', error='Backup file is required.'), 400

    with tempfile.NamedTemporaryFile(prefix='cocodems_restore_', suffix='.sql', delete=False) as tf:
        restore_path = tf.name
        backup_file.save(restore_path)

    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            for t in _BACKUP_TABLES:
                cursor.execute(f'DROP TABLE IF EXISTS {t} CASCADE;')
        conn.commit()
    except Exception as e:
        conn.rollback()
        conn.close()
        try:
            os.unlink(restore_path)
        except Exception:
            pass
        return f"Error preparing database for reload: {e}", 500
    conn.close()

    try:
        psql_bin = _preferred_bin('PSQL_BIN', 'psql', '/opt/homebrew/opt/postgresql@16/bin/psql')
        cmd = [
            psql_bin,
            '-h', str(DATABASE.get('host') or ''),
            '-p', str(DATABASE.get('port') or ''),
            '-U', str(DATABASE.get('user') or ''),
            '-d', str(DATABASE.get('dbname') or ''),
            '-v', 'ON_ERROR_STOP=1',
            '-f', restore_path,
        ]
        subprocess.run(cmd, check=True, env=_pg_env(), capture_output=True, text=True)
    except subprocess.CalledProcessError as e:
        try:
            os.unlink(restore_path)
        except Exception:
            pass
        detail = (e.stderr or e.stdout or str(e)).strip()
        return f"Error reloading database: {detail}", 500
    except Exception as e:
        try:
            os.unlink(restore_path)
        except Exception:
            pass
        return f"Error reloading database: {e}", 500

    try:
        os.unlink(restore_path)
    except Exception:
        pass

    return render_template('admin.html', message='Database reload complete.')


def _infer_city_from_jurisdiction(jurisdiction: str | None) -> str | None:
    if not jurisdiction:
        return None
    j = jurisdiction.strip()
    if not j:
        return None

    for prefix in ['City of ', 'Town of ', 'Village of ']:
        if j.startswith(prefix):
            city = j[len(prefix):].strip()
            return city or None

    m = re.match(r'^(.*?)(?:\s+(?:Area|Community))?\s+School District\s*$', j)
    if m:
        city = (m.group(1) or '').strip()
        return city or None

    m = re.match(r'^(.*?)\s+District\s+Schools\s*$', j)
    if m:
        city = (m.group(1) or '').strip()
        return city or None

    m = re.match(r'^School District of\s+(.*?)(?:\s+-\s+Area\s+.*)?\s*$', j)
    if m:
        city = (m.group(1) or '').strip()
        return city or None

    return None


@app.route('/admin/clean_candidates', methods=['POST'])
def admin_clean_candidates():
    if not _admin_token_is_valid(request):
        return "Forbidden", 403

    candidates_file = request.files.get('candidates_file')
    if not candidates_file:
        return render_template('admin.html', error='Candidates CSV file is required.'), 400

    raw = candidates_file.read()
    try:
        text = raw.decode('utf-8-sig')
    except Exception:
        text = raw.decode('utf-8', errors='replace')

    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        return render_template('admin.html', error='Candidates CSV appears to have no header.'), 400

    normalized_fieldnames = [f.strip() for f in reader.fieldnames]

    required = ['First Name', 'Middle Name', 'Last Name', 'Contact ID', 'Jurisdiction']
    missing = [c for c in required if c not in normalized_fieldnames]
    if missing:
        return render_template('admin.html', error=f"Candidates CSV missing required columns: {', '.join(missing)}"), 400

    field_map = {f.strip(): f for f in reader.fieldnames}

    conn = get_db_connection()
    inserted_cache: dict[tuple[str, str, str], int] = {}
    out_rows: list[dict] = []

    try:
        with conn.cursor() as cursor:
            for row in reader:
                if row is None:
                    continue

                contact_id_key = field_map['Contact ID']
                first_key = field_map['First Name']
                middle_key = field_map['Middle Name']
                last_key = field_map['Last Name']
                jurisdiction_key = field_map['Jurisdiction']

                existing_contact = (row.get(contact_id_key) or '').strip()
                if existing_contact:
                    out_rows.append(row)
                    continue

                first_name = (row.get(first_key) or '').strip() or None
                middle_name = (row.get(middle_key) or '').strip()
                last_name = (row.get(last_key) or '').strip() or None

                if not first_name or not last_name:
                    out_rows.append(row)
                    continue

                cache_key = (
                    first_name.lower(),
                    middle_name.lower(),
                    last_name.lower(),
                )

                if cache_key in inserted_cache:
                    row[contact_id_key] = str(inserted_cache[cache_key])
                    out_rows.append(row)
                    continue

                middle_part = f" {middle_name}" if middle_name else ""
                full_name = f"{last_name}, {first_name}{middle_part}".strip()

                jurisdiction = (row.get(jurisdiction_key) or '').strip() or None
                city = _infer_city_from_jurisdiction(jurisdiction) or (jurisdiction or '')

                cursor.execute(
                    """
                    INSERT INTO individuals (
                        first_name, middle_name, last_name, full_name,
                        email, phone, address, city, state, zip,
                        candidate_status, party_affiliation, democratic_alignment, area, notes
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING contact_id;
                    """,
                    (
                        first_name,
                        middle_name,
                        last_name,
                        full_name,
                        '',
                        '',
                        '',
                        city,
                        'WI',
                        '',
                        '',
                        '',
                        '',
                        '',
                        '',
                    ),
                )
                new_contact_id = cursor.fetchone()[0]
                inserted_cache[cache_key] = int(new_contact_id)
                row[contact_id_key] = str(new_contact_id)
                out_rows.append(row)

        conn.commit()
    except Exception as e:
        conn.rollback()
        conn.close()
        return f"Error cleaning candidates: {e}", 500

    conn.close()

    out_buf = io.StringIO(newline='')
    writer = csv.DictWriter(out_buf, fieldnames=reader.fieldnames)
    writer.writeheader()
    writer.writerows(out_rows)
    out_bytes = out_buf.getvalue().encode('utf-8')

    return send_file(
        io.BytesIO(out_bytes),
        as_attachment=True,
        download_name='candidates_cleaned.csv',
        mimetype='text/csv',
    )

@app.route('/')
def index():
    """Redirect root URL to elections page."""
    return redirect(url_for('elections'))

@app.route('/elections')
def elections():
    """Render the elections page."""
    sort_column = request.args.get('sort', 'election_name')
    sort_order = request.args.get('order', 'asc')
    
    if sort_column not in ['election_name', 'election_date']:
        sort_column = 'election_name'
    if sort_order not in ['asc', 'desc']:
        sort_order = 'asc'

    conn = get_db_connection()
    with conn.cursor(cursor_factory=RealDictCursor) as cursor:
        cursor.execute(f"""
            SELECT election_id, election_name, TO_CHAR(election_date, 'MM/DD/YYYY') as election_date
            FROM elections
            ORDER BY {sort_column} {sort_order};
        """)
        elections_data = cursor.fetchall()
    conn.close()

    return render_template(
        'elections.html',
        elections=elections_data,
        sort_column=sort_column,
        sort_order=sort_order
    )

@app.route('/election/add', methods=['GET', 'POST'])
def add_election():
    """Render and handle the add election form."""
    if request.method == 'POST':
        election_name = (request.form.get('election_name') or '').strip() or None
        election_date_str = (request.form.get('election_date') or '').strip()

        if not election_date_str:
            return "Election date is required", 400

        try:
            election_date = datetime.strptime(election_date_str, '%Y-%m-%d').date()
        except ValueError:
            return "Invalid election date", 400

        election_id = int(election_date.strftime('%Y%m%d'))

        conn = get_db_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO elections (election_id, election_name, election_date)
                    VALUES (%s, %s, %s);
                    """,
                    (election_id, election_name, election_date),
                )
            conn.commit()
        except Exception as e:
            conn.rollback()
            conn.close()
            pgcode = getattr(e, 'pgcode', None)
            if pgcode == '23505':
                return render_template(
                    'add_election.html',
                    error=f"An election for {election_date.strftime('%Y-%m-%d')} already exists.",
                    election_name=election_name or '',
                    election_date=election_date.strftime('%Y-%m-%d'),
                ), 400
            return f"Error adding election: {e}", 500

        conn.close()
        return redirect(url_for('elections'))

    return render_template('add_election.html')

@app.route('/election_races/<int:election_id>')
def election_races(election_id):
    """Render the election detail page for specific election races."""
    sort_column = request.args.get('sort', 'race_name')
    sort_order = request.args.get('order', 'asc')
    
    if sort_column not in ['race_name', 'seats', 'total_votes', 'term_years']:
        sort_column = 'race_name'
    if sort_order not in ['asc', 'desc']:
        sort_order = 'asc'

    conn = get_db_connection()
    with conn.cursor(cursor_factory=RealDictCursor) as cursor:
        cursor.execute("""
            SELECT election_name, TO_CHAR(election_date, 'MM/DD/YYYY') as election_date
            FROM elections
            WHERE election_id = %s;
        """, (election_id,))
        election = cursor.fetchone()

        cursor.execute(f"""
            SELECT race_id, race_name, seats, total_votes, term_years
            FROM races
            WHERE election_id = %s
            ORDER BY {sort_column} {sort_order};
        """, (election_id,))
        races = cursor.fetchall()

        for race in races:
            cursor.execute("""
                SELECT candidate_name, contact_id
                FROM campaigns
                WHERE race_id = %s AND elected = 1;
            """, (race['race_id'],))
            winners = cursor.fetchall()
            race['winners'] = winners

    conn.close()

    if not election:
        return "Election not found", 404

    return render_template('election_races.html', election=election, races=races, election_id=election_id, sort_column=sort_column, sort_order=sort_order)


@app.route('/election_races/<int:election_id>/upload_races', methods=['POST'])
def upload_election_races(election_id):
    if not _admin_token_is_valid(request):
        return "Forbidden", 403

    races_file = request.files.get('races_file')
    if not races_file:
        return "Races CSV file is required", 400

    raw = races_file.read()
    try:
        text = raw.decode('utf-8-sig')
    except Exception:
        text = raw.decode('utf-8', errors='replace')

    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        return "Races CSV appears to have no header", 400

    normalized_fieldnames = [f.strip() for f in reader.fieldnames]
    required = [
        'Jurisdiction',
        'Office',
        'Votes Received',
        'Percent Received',
        'Total Votes',
        'Race Ordinal ID',
        'Elected',
        'Election Date',
        'Term (years)',
        'Office Start Date',
        'Re-Election Date',
        'Term End Date',
        'First Name',
        'Middle Name',
        'Last Name',
        'Contact ID',
    ]
    missing = [c for c in required if c not in normalized_fieldnames]
    if missing:
        return f"Races CSV missing required columns: {', '.join(missing)}", 400

    field_map = {f.strip(): f for f in reader.fieldnames}
    rows = [r for r in reader if r]
    if not rows:
        return "Races CSV contains no rows", 400

    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(
                """
                SELECT election_date::date AS election_date
                FROM elections
                WHERE election_id = %s;
                """,
                (election_id,),
            )
            election = cursor.fetchone()
            if not election:
                conn.close()
                return "Election not found", 404

            election_year = int(election['election_date'].year)

            groups: dict[str, list[dict]] = {}
            for row in rows:
                key = (row.get(field_map['Race Ordinal ID']) or '').strip()
                if not key:
                    continue
                groups.setdefault(key, []).append(row)

            for ordinal_id, g_rows in groups.items():
                sample = g_rows[0]
                jurisdiction = (sample.get(field_map['Jurisdiction']) or '').strip()
                office_name = (sample.get(field_map['Office']) or '').strip()
                if not jurisdiction or not office_name:
                    continue

                total_votes_raw = (sample.get(field_map['Total Votes']) or '').strip()
                term_years_raw = (sample.get(field_map['Term (years)']) or '').strip()
                try:
                    total_votes = int(float(total_votes_raw)) if total_votes_raw else 0
                except Exception:
                    total_votes = 0
                try:
                    term_years = int(float(term_years_raw)) if term_years_raw else 0
                except Exception:
                    term_years = 0

                seats = 0
                elected_key = field_map['Elected']
                for r in g_rows:
                    elected_val = (r.get(elected_key) or '').strip()
                    if elected_val in {'1', 'true', 'True', 'YES', 'Yes'}:
                        seats += 1

                cursor.execute(
                    """
                    SELECT jurisdiction_id
                    FROM jurisdictions
                    WHERE jurisdiction_name = %s
                    LIMIT 1;
                    """,
                    (jurisdiction,),
                )
                jrow = cursor.fetchone()
                if not jrow:
                    raise ValueError(f"Jurisdiction not found: {jurisdiction}")
                jurisdiction_id = int(jrow['jurisdiction_id'])

                cursor.execute(
                    """
                    SELECT office_name_id
                    FROM offices
                    WHERE office_name = %s
                    LIMIT 1;
                    """,
                    (office_name,),
                )
                orow = cursor.fetchone()
                if not orow:
                    raise ValueError(f"Office not found in offices table: {office_name}")
                office_name_id = int(orow['office_name_id'])

                office_id = int(jurisdiction_id * 100 + office_name_id)
                race_id = int(election_id * 10000000 + office_id)

                race_name = f"{election_year} {jurisdiction}/{office_name}"

                term_start_date = _fourth_monday_in_april(election_year)
                reelection_date = _first_tuesday_in_april(election_year + (term_years or 0))
                term_end_date = _fourth_monday_in_april(election_year + (term_years or 0))

                cursor.execute(
                    """
                    DELETE FROM campaigns
                    WHERE race_id = %s;
                    """,
                    (race_id,),
                )

                cursor.execute(
                    """
                    UPDATE races
                    SET
                        race_name = %s,
                        jurisdiction = %s,
                        jurisdiction_id = %s,
                        office_name = %s,
                        office_name_id = %s,
                        office_id = %s,
                        election_id = %s,
                        seats = %s,
                        total_votes = %s,
                        term_years = %s,
                        term_start_date = %s,
                        reelection_date = %s,
                        term_end_date = %s
                    WHERE race_id = %s;
                    """,
                    (
                        race_name,
                        jurisdiction,
                        jurisdiction_id,
                        office_name,
                        office_name_id,
                        office_id,
                        election_id,
                        seats,
                        total_votes,
                        term_years,
                        term_start_date,
                        reelection_date,
                        term_end_date,
                        race_id,
                    ),
                )
                if cursor.rowcount == 0:
                    cursor.execute(
                        """
                        INSERT INTO races (
                            race_id,
                            race_name,
                            jurisdiction,
                            jurisdiction_id,
                            office_name,
                            office_name_id,
                            office_id,
                            election_id,
                            seats,
                            total_votes,
                            term_years,
                            term_start_date,
                            reelection_date,
                            term_end_date
                        )
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s);
                        """,
                        (
                            race_id,
                            race_name,
                            jurisdiction,
                            jurisdiction_id,
                            office_name,
                            office_name_id,
                            office_id,
                            election_id,
                            seats,
                            total_votes,
                            term_years,
                            term_start_date,
                            reelection_date,
                            term_end_date,
                        ),
                    )

                for r in g_rows:
                    first_name = (r.get(field_map['First Name']) or '').strip()
                    middle_name = (r.get(field_map['Middle Name']) or '').strip()
                    last_name = (r.get(field_map['Last Name']) or '').strip()
                    contact_id_raw = (r.get(field_map['Contact ID']) or '').strip()

                    if not first_name or not last_name or not contact_id_raw:
                        continue

                    candidate_name = f"{first_name} {middle_name + ' ' if middle_name else ''}{last_name}".strip()
                    campaign_name = f"{candidate_name} for {jurisdiction}/{office_name} {election_year}".strip()

                    votes_received = _parse_int_field(r.get(field_map['Votes Received']), default=0)
                    percent_received = _parse_float_field(r.get(field_map['Percent Received']), default=0.0)
                    total_votes_row = _parse_int_field(r.get(field_map['Total Votes']), default=total_votes)
                    elected_val = (r.get(field_map['Elected']) or '').strip()
                    elected = 1 if elected_val in {'1', 'true', 'True', 'YES', 'Yes'} else 0

                    election_date = _parse_date_mdy(r.get(field_map['Election Date']))
                    office_start_date = _parse_date_mdy(r.get(field_map['Office Start Date']))
                    reelection_date_row = _parse_date_mdy(r.get(field_map['Re-Election Date']))
                    term_end_date_row = _parse_date_mdy(r.get(field_map['Term End Date']))

                    term_years_row = _parse_int_field(r.get(field_map['Term (years)']), default=term_years)

                    cursor.execute(
                        """
                        INSERT INTO campaigns (
                            campaign_name,
                            race_id,
                            candidate_name,
                            contact_id,
                            jurisdiction,
                            jurisdiction_id,
                            office_name,
                            office_name_id,
                            office_id,
                            votes_received,
                            percent_received,
                            total_votes,
                            elected,
                            election_date,
                            term_years,
                            term_start_date,
                            reelection_date,
                            term_end_date
                        )
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s);
                        """,
                        (
                            campaign_name,
                            race_id,
                            candidate_name,
                            int(contact_id_raw),
                            jurisdiction,
                            jurisdiction_id,
                            office_name,
                            office_name_id,
                            office_id,
                            votes_received,
                            percent_received,
                            total_votes_row,
                            elected,
                            election_date,
                            term_years_row,
                            office_start_date,
                            reelection_date_row,
                            term_end_date_row,
                        ),
                    )

        conn.commit()
    except Exception as e:
        conn.rollback()
        conn.close()
        return f"Error uploading races: {e}", 500

    conn.close()
    return redirect(url_for('election_races', election_id=election_id))


def _first_tuesday_in_april(year: int) -> date:
    april_first = date(year, 4, 1)
    days_until_tuesday = (calendar.TUESDAY - april_first.weekday() + 7) % 7
    return april_first + timedelta(days=days_until_tuesday)


def _fourth_monday_in_april(year: int) -> date:
    april_first = date(year, 4, 1)
    fourth_monday_offset = 21 + (calendar.MONDAY - april_first.weekday() + 7) % 7
    return april_first + timedelta(days=fourth_monday_offset)


def _parse_int_field(val: str | None, default: int = 0) -> int:
    s = (val or '').strip()
    if not s:
        return default
    try:
        return int(s)
    except Exception:
        return int(float(s))


def _parse_float_field(val: str | None, default: float = 0.0) -> float:
    s = (val or '').strip()
    if not s:
        return default
    return float(s)


def _parse_date_mdy(val: str | None) -> date | None:
    s = (val or '').strip()
    if not s:
        return None
    for fmt in ('%m/%d/%y', '%m/%d/%Y'):
        try:
            return datetime.strptime(s, fmt).date()
        except Exception:
            pass
    raise ValueError(f"Invalid date: {s}")


@app.route('/add_race/<int:election_id>', methods=['GET', 'POST'])
def add_race(election_id):
    """Render and handle the add race form."""
    conn = get_db_connection()
    with conn.cursor(cursor_factory=RealDictCursor) as cursor:
        cursor.execute(
            """
            SELECT election_name, election_date::date AS election_date
            FROM elections
            WHERE election_id = %s;
            """,
            (election_id,),
        )
        election = cursor.fetchone()

        cursor.execute(
            """
            SELECT DISTINCT office_full_name
            FROM offices
            WHERE office_full_name IS NOT NULL AND office_full_name <> ''
            ORDER BY office_full_name;
            """
        )
        office_full_names = cursor.fetchall()

    conn.close()

    if not election:
        return "Election not found", 404

    if request.method == 'POST':
        selected_office_full_name = (request.form.get('office_full_name') or '').strip()
        if not selected_office_full_name:
            return render_template(
                'add_race.html',
                election={
                    'election_name': election['election_name'],
                    'election_date': election['election_date'].strftime('%m/%d/%Y'),
                },
                office_full_names=office_full_names,
                selected_office_full_name=selected_office_full_name,
                error='Office is required.',
            ), 400

        election_year = election['election_date'].year

        conn = get_db_connection()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute(
                    """
                    SELECT
                        office_full_name,
                        jurisdiction,
                        jurisdiction_id,
                        office_name,
                        office_name_id,
                        office_id,
                        term_years,
                        MIN(seats) AS seats
                    FROM offices
                    WHERE office_full_name = %s
                    GROUP BY
                        office_full_name,
                        jurisdiction,
                        jurisdiction_id,
                        office_name,
                        office_name_id,
                        office_id,
                        term_years
                    ORDER BY MIN(seats) ASC
                    LIMIT 1;
                    """,
                    (selected_office_full_name,),
                )
                office = cursor.fetchone()

                if not office:
                    conn.rollback()
                    conn.close()
                    return render_template(
                        'add_race.html',
                        election={
                            'election_name': election['election_name'],
                            'election_date': election['election_date'].strftime('%m/%d/%Y'),
                        },
                        office_full_names=office_full_names,
                        selected_office_full_name=selected_office_full_name,
                        error='Office not found.',
                    ), 400

                seats = int(office['seats']) if office['seats'] is not None else None
                term_years = int(office['term_years']) if office['term_years'] is not None else None
                if seats is None or term_years is None:
                    conn.rollback()
                    conn.close()
                    return render_template(
                        'add_race.html',
                        election={
                            'election_name': election['election_name'],
                            'election_date': election['election_date'].strftime('%m/%d/%Y'),
                        },
                        office_full_names=office_full_names,
                        selected_office_full_name=selected_office_full_name,
                        error='Office is missing seats and/or term years.',
                    ), 400

                race_name = f"{election_year} {office['office_full_name']}"

                term_start_date = _fourth_monday_in_april(election_year)
                reelection_date = _first_tuesday_in_april(election_year + term_years)
                term_end_date = _fourth_monday_in_april(election_year + term_years)

                race_id = int(election_id * 10000000 + int(office['office_id']))

                cursor.execute(
                    """
                    INSERT INTO races (
                        race_id,
                        race_name,
                        jurisdiction,
                        jurisdiction_id,
                        office_name,
                        office_name_id,
                        office_id,
                        election_id,
                        seats,
                        total_votes,
                        term_years,
                        term_start_date,
                        reelection_date,
                        term_end_date
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s);
                    """,
                    (
                        race_id,
                        race_name,
                        office['jurisdiction'],
                        office['jurisdiction_id'],
                        office['office_name'],
                        office['office_name_id'],
                        office['office_id'],
                        election_id,
                        seats,
                        0,
                        term_years,
                        term_start_date,
                        reelection_date,
                        term_end_date,
                    ),
                )

            conn.commit()
        except Exception as e:
            conn.rollback()
            conn.close()
            pgcode = getattr(e, 'pgcode', None)
            if pgcode == '23505':
                return render_template(
                    'add_race.html',
                    election={
                        'election_name': election['election_name'],
                        'election_date': election['election_date'].strftime('%m/%d/%Y'),
                    },
                    office_full_names=office_full_names,
                    selected_office_full_name=selected_office_full_name,
                    error='A race with that ID already exists for this election/office.',
                ), 400
            return f"Error adding race: {e}", 500

        conn.close()
        return redirect(url_for('election_races', election_id=election_id))

    return render_template(
        'add_race.html',
        election={
            'election_name': election['election_name'],
            'election_date': election['election_date'].strftime('%m/%d/%Y'),
        },
        office_full_names=office_full_names,
        selected_office_full_name='',
    )

@app.route('/race_details/<int:race_id>')
def race_details(race_id):
    """Render the race detail page for a specific race."""
    conn = get_db_connection()
    with conn.cursor(cursor_factory=RealDictCursor) as cursor:
        cursor.execute("""
            SELECT race_name, jurisdiction, office_name, seats, total_votes, term_years, 
                   TO_CHAR(term_start_date, 'MM/DD/YYYY') as term_start_date,
                   TO_CHAR(reelection_date, 'MM/DD/YYYY') as reelection_date,
                   TO_CHAR(term_end_date, 'MM/DD/YYYY') as term_end_date
            FROM races
            WHERE race_id = %s;
        """, (race_id,))
        race = cursor.fetchone()

        cursor.execute("""
            SELECT campaign_name, votes_received, percent_received, total_votes, elected, contact_id
            FROM campaigns
            WHERE race_id = %s;
        """, (race_id,))
        campaigns = cursor.fetchall()
    conn.close()

    if not race:
        return "Race not found", 404

    return render_template('race_details.html', race=race, campaigns=campaigns)

@app.route('/individual/<int:contact_id>')
def individual(contact_id):
    """Render the individual candidate detail page."""
    conn = get_db_connection()
    with conn.cursor(cursor_factory=RealDictCursor) as cursor:
        cursor.execute("""
            SELECT first_name, middle_name, last_name, email, phone, address, city, zip, state, 
                   candidate_status, party_affiliation, democratic_alignment, area, notes, contact_id
            FROM individuals
            WHERE contact_id = %s;
        """, (contact_id,))
        individual = cursor.fetchone()

        cursor.execute("""
            SELECT campaign_name, votes_received, percent_received, total_votes, elected, 
                   TO_CHAR(election_date, 'MM/DD/YYYY') as election_date,
                   TO_CHAR(term_start_date, 'MM/DD/YYYY') as term_start_date,
                   TO_CHAR(reelection_date, 'MM/DD/YYYY') as reelection_date,
                   TO_CHAR(term_end_date, 'MM/DD/YYYY') as term_end_date,
                   race_id, election_date as election_sort_date
            FROM campaigns
            WHERE contact_id = %s
            ORDER BY election_sort_date;
        """, (contact_id,))
        campaigns = cursor.fetchall()
    conn.close()

    if not individual:
        return "Individual not found", 404

    return render_template('individual.html', individual=individual, campaigns=campaigns)

@app.route('/individual/add', methods=['GET', 'POST'])
def add_individual():
    """Render and handle the add individual form."""
    if request.method == 'POST':
        data = request.form

        first_name = (data.get('first_name') or '').strip() or None
        middle_name = (data.get('middle_name') or '').strip() or None
        last_name = (data.get('last_name') or '').strip() or None

        name_parts = [p for p in [first_name, middle_name, last_name] if p]
        full_name = ' '.join(name_parts) if name_parts else None

        email = (data.get('email') or '').strip() or None
        phone = (data.get('phone') or '').strip() or None
        address = (data.get('address') or '').strip() or None
        city = (data.get('city') or '').strip() or None
        state = (data.get('state') or '').strip() or 'WI'
        zip_code = (data.get('zip') or '').strip() or None

        candidate_status = (data.get('candidate_status') or '').strip() or None
        party_affiliation = (data.get('party_affiliation') or '').strip() or None
        democratic_alignment = (data.get('democratic_alignment') or '').strip() or None
        area = (data.get('area') or '').strip() or None
        notes = (data.get('notes') or '').strip() or None

        conn = get_db_connection()
        try:
            with conn.cursor() as cursor:
                try:
                    cursor.execute(
                        """
                        INSERT INTO individuals (
                            first_name, middle_name, last_name, full_name,
                            email, phone, address, city, state, zip,
                            candidate_status, party_affiliation, democratic_alignment, area, notes
                        )
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        RETURNING contact_id;
                        """,
                        (
                            first_name, middle_name, last_name, full_name,
                            email, phone, address, city, state, zip_code,
                            candidate_status, party_affiliation, democratic_alignment, area, notes,
                        ),
                    )
                    contact_id = cursor.fetchone()[0]
                except Exception:
                    cursor.execute("LOCK TABLE individuals IN EXCLUSIVE MODE;")
                    cursor.execute("SELECT COALESCE(MAX(contact_id), 0) + 1 FROM individuals;")
                    contact_id = cursor.fetchone()[0]

                    cursor.execute(
                        """
                        INSERT INTO individuals (
                            contact_id, first_name, middle_name, last_name, full_name,
                            email, phone, address, city, state, zip,
                            candidate_status, party_affiliation, democratic_alignment, area, notes
                        )
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s);
                        """,
                        (
                            contact_id, first_name, middle_name, last_name, full_name,
                            email, phone, address, city, state, zip_code,
                            candidate_status, party_affiliation, democratic_alignment, area, notes,
                        ),
                    )

            conn.commit()
        except Exception as e:
            conn.rollback()
            conn.close()
            return f"Error adding individual: {e}", 500

        conn.close()
        return redirect(url_for('individual', contact_id=contact_id))

    return render_template('add_individual.html', default_state='WI')

@app.route('/update/individual/<int:contact_id>', methods=['GET', 'POST'])
def update_individual(contact_id):
    """Render the update form for an individual candidate."""
    conn = get_db_connection()
    if request.method == 'POST':
        # Update the individual's information in the database
        data = request.form
        with conn.cursor() as cursor:
            cursor.execute("""
                UPDATE individuals
                SET first_name = %s, middle_name = %s, last_name = %s, email = %s, phone = %s, 
                    address = %s, city = %s, zip = %s, state = %s, candidate_status = %s, 
                    party_affiliation = %s, democratic_alignment = %s, area = %s, notes = %s
                WHERE contact_id = %s;
            """, (
                data.get('first_name') or None, data.get('middle_name') or None, data.get('last_name') or None, 
                data.get('email') or None, data.get('phone') or None, data.get('address') or None, 
                data.get('city') or None, data.get('zip') or None, data.get('state') or None, 
                data.get('candidate_status') or None, data.get('party_affiliation') or None, 
                data.get('democratic_alignment') or None, data.get('area') or None, data.get('notes') or None, 
                contact_id
            ))
        conn.commit()
        conn.close()
        return redirect(url_for('individual', contact_id=contact_id))
    else:
        # Fetch the individual's current information to pre-fill the form
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute("""
                SELECT first_name, middle_name, last_name, email, phone, address, city, zip, state, 
                       candidate_status, party_affiliation, democratic_alignment, area, notes
                FROM individuals
                WHERE contact_id = %s;
            """, (contact_id,))
            individual = cursor.fetchone()
        conn.close()

        if not individual:
            return "Individual not found", 404

        return render_template('update_individual.html', individual=individual)

@app.route('/people')
def people():
    """Render the people page."""
    sort_column = request.args.get('sort', 'full_name')
    sort_order = request.args.get('order', 'asc')

    sort_map = {
        'full_name': 'i.full_name',
        'current_jurisdiction': 'coalesce(c.current_jurisdiction, \'\')',
        'current_office': 'coalesce(c.current_office, \'\')',
        'party_affiliation': 'coalesce(i.party_affiliation, \'\')',
        'candidate_status': 'coalesce(i.candidate_status, \'\')',
    }
    if sort_column not in sort_map:
        sort_column = 'full_name'
    if sort_order not in ['asc', 'desc']:
        sort_order = 'asc'

    conn = get_db_connection()
    with conn.cursor(cursor_factory=RealDictCursor) as cursor:
        cursor.execute(f"""
            WITH current_service AS (
                SELECT
                    contact_id,
                    string_agg(DISTINCT jurisdiction, ', ' ORDER BY jurisdiction) AS current_jurisdiction,
                    string_agg(DISTINCT office_name, ', ' ORDER BY office_name) AS current_office
                FROM campaigns
                WHERE elected = 1
                  AND term_start_date IS NOT NULL
                  AND term_end_date IS NOT NULL
                  AND CURRENT_DATE >= term_start_date::date
                  AND CURRENT_DATE <= term_end_date::date
                GROUP BY contact_id
            )
            SELECT
                i.contact_id,
                i.full_name,
                i.party_affiliation,
                i.candidate_status,
                c.current_jurisdiction,
                c.current_office
            FROM individuals i
            LEFT JOIN current_service c ON c.contact_id = i.contact_id
            ORDER BY {sort_map[sort_column]} {sort_order};
        """)
        peoples_data = cursor.fetchall()
    conn.close()

    return render_template(
        'peoples.html',
        peoples=peoples_data,
        sort_column=sort_column,
        sort_order=sort_order,
    )

@app.route('/peoples')
def peoples_redirect():
    return redirect(url_for('people'))

@app.route('/jurisdictions')
def jurisdictions():
    """Render the jurisdictions page."""
    sort_column = request.args.get('sort', 'jurisdiction_name')
    sort_order = request.args.get('order', 'asc')
    
    if sort_column not in ['jurisdiction_name', 'jurisdiction_type']:
        sort_column = 'jurisdiction_name'
    if sort_order not in ['asc', 'desc']:
        sort_order = 'asc'

    conn = get_db_connection()
    with conn.cursor(cursor_factory=RealDictCursor) as cursor:
        cursor.execute(f"""
            SELECT jurisdiction_id, jurisdiction_name, jurisdiction_type
            FROM jurisdictions
            ORDER BY {sort_column} {sort_order};
        """)
        jurisdictions_data = cursor.fetchall()
    conn.close()

    return render_template(
        'jurisdictions.html',
        jurisdictions=jurisdictions_data,
        sort_column=sort_column,
        sort_order=sort_order
    )

@app.route('/jurisdiction/details/<int:jurisdiction_id>')
def jurisdiction_details(jurisdiction_id):
    """Render the jurisdiction detail page."""
    conn = get_db_connection()
    with conn.cursor(cursor_factory=RealDictCursor) as cursor:
        cursor.execute("""
            SELECT jurisdiction_name, jurisdiction_type, email, phone, address, city, state, zip, website
            FROM jurisdictions
            WHERE jurisdiction_id = %s;
        """, (jurisdiction_id,))
        jurisdiction = cursor.fetchone()

        cursor.execute("""
            SELECT office_name, office_id, seats
            FROM offices
            WHERE jurisdiction_id = %s
            ORDER BY office_name;
        """, (jurisdiction_id,))
        offices = cursor.fetchall()

        for office in offices:
            cursor.execute("""
                SELECT candidate_name, contact_id
                FROM campaigns
                WHERE office_id = %s AND elected = 1
                ORDER BY election_date DESC
                LIMIT %s;
            """, (office['office_id'], office['seats']))
            officeholders = cursor.fetchall()
            office['current_officeholders'] = officeholders

    conn.close()

    if not jurisdiction:
        return "Jurisdiction not found", 404

    return render_template('jurisdiction_details.html', jurisdiction=jurisdiction, offices=offices)

@app.route('/offices')
def offices():
    """Render the offices page."""
    conn = get_db_connection()
    with conn.cursor(cursor_factory=RealDictCursor) as cursor:
        cursor.execute("""
            SELECT jurisdiction, jurisdiction_id, office_name, office_id, seats, term_years, term_start_month, election_month
            FROM offices
            ORDER BY jurisdiction, office_name;
        """)
        offices_data = cursor.fetchall()
    conn.close()

    return render_template('offices.html', offices=offices_data)

def month_name(month_number):
    """Convert month number to month name."""
    months = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]
    return months[month_number - 1] if 1 <= month_number <= 12 else ""

@app.route('/googlecc3d64f28e62a7a5.html')
def google_verification():
    """Serve the Google verification file."""
    return render_template('googlecc3d64f28e62a7a5.html')

@app.route('/office/details/<int:office_id>')
def office_details(office_id):
    """Render the office detail page."""
    conn = get_db_connection()
    with conn.cursor(cursor_factory=RealDictCursor) as cursor:
        cursor.execute("""
            SELECT office_full_name, office_name, seats, term_years, term_start_month, election_month, email, phone, address, city, state, zip, website
            FROM offices
            WHERE office_id = %s;
        """, (office_id,))
        office = cursor.fetchone()

        cursor.execute(
            """
            SELECT candidate_name, contact_id, election_date
            FROM campaigns
            WHERE office_id = %s
              AND elected = 1
              AND election_date = (
                  SELECT MAX(election_date)
                  FROM campaigns
                  WHERE office_id = %s AND elected = 1
              )
            ORDER BY votes_received DESC NULLS LAST, campaign_id DESC;
            """,
            (office_id, office_id),
        )
        officeholders = cursor.fetchall()

        cursor.execute(
            """
            SELECT
                r.race_id,
                r.race_name,
                e.election_date::date AS election_date
            FROM races r
            LEFT JOIN elections e ON e.election_id = r.election_id
            WHERE r.office_id = %s
            ORDER BY election_date ASC NULLS LAST, r.race_name ASC;
            """,
            (office_id,),
        )
        races = cursor.fetchall()
    conn.close()

    if not office:
        return "Office not found", 404

    return render_template('office_details.html', office=office, officeholders=officeholders, races=races)

app.jinja_env.globals.update(month_name=month_name)

if __name__ == '__main__':
    app.run(debug=True, port=int(os.getenv('PORT', '5000')))
