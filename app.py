from flask import Flask, render_template, request, redirect, url_for
import psycopg2
from psycopg2.extras import RealDictCursor
import os
from dotenv import load_dotenv

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

    return render_template('election_races.html', election=election, races=races, sort_column=sort_column, sort_order=sort_order)

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
    conn.close()

    if not office:
        return "Office not found", 404

    return render_template('office_details.html', office=office)

app.jinja_env.globals.update(month_name=month_name)

if __name__ == '__main__':
    app.run(debug=True)
