import csv
from datetime import datetime
from datetime import date, timedelta
import calendar

def local_election_dates(year, term_years):
    """
    Calculate the election date, office start date, and term end date for local elections in Columbia County, Wisconsin.

    Args:
        year (int): Year of the election.
        term_years (int): Number of years for the elected term.

    Returns:
        tuple: Election date (datetime.date), office start date (datetime.date), term end date (datetime.date)
    """
    # Find the first Tuesday in April for the election date
    april_first = date(year, 4, 1)
    election_date = april_first + timedelta(days=(1 - april_first.weekday() + 7) % 7)

    # Calculate the fourth Monday of April for the office start date
    fourth_monday_offset = 21 + (calendar.MONDAY - april_first.weekday() + 7) % 7
    office_start_date = april_first + timedelta(days=fourth_monday_offset)

    # Calculate the term end date by adding the term length in years
    april_first_term_end = date(year + term_years, 4, 1)
    reelection_date = april_first_term_end + timedelta(days=(1 - april_first_term_end.weekday() + 7) % 7)
    fourth_monday_offset = 21 + (calendar.MONDAY - april_first_term_end.weekday() + 7) % 7
    office_end_date = april_first_term_end + timedelta(days=fourth_monday_offset)

    return election_date, office_start_date, reelection_date, office_end_date

# Example usage:
# print(local_election_dates(2024, 2))
# print(local_election_dates(2024, 3))


def get_terms(input_csv):
    """
    Reads a CSV file and returns a dictionary with information about the number
    of years for each election jurisdiction and office.

    :param input_csv: Path to the CSV file
    :return: Dictionary of the form:
        { <jurisdiction>: {
                <office>: n
            } 
        }
        where <jurisdiction> is the name of the jurisdiction,
        <office> is the name of an office within that jurisdiction,
        and n is the number of years of the term of that office.
    """

    result_dict = {}
    # try:
    with open(input_csv, 'r', encoding='utf-8-sig') as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
            jurisdiction = row['Jurisdiction']
            office = row['Office']
            term = row['Term (years)']
            result_dict[jurisdiction + "/" + office] = term
    return result_dict

# Example usage
# terms = get_terms("election_terms.csv")
# print(terms)


def get_special_names():
    special_names = {}
    with open("unusual_names.csv", mode='r', newline='', encoding='utf-8-sig') as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
            full = row['Full']
            first = row['First']
            middle = row['Middle']
            last = row['Last']
            special_names[full] = {
                'First': first,
                'Middle': middle,
                'Last': last
            }
    return special_names


def split_name(full_name, special_names):
    if full_name in special_names:
        parts = special_names[full_name]
        return parts['First'], parts['Middle'], parts['Last']

    # List of common suffixes
    suffixes = {'Jr.', 'Sr.', 'II', 'III', 'IV', 'V'}

    # Remove commas and split the name into parts
    name_parts = full_name.replace(',', '').split()

    # Check if the last part is a suffix
    if name_parts[-1] in suffixes:
        suffix = name_parts.pop()
    else:
        suffix = ''

    if len(name_parts) == 0:
        return '', '', ''

    elif len(name_parts) == 1:
        first = name_parts[0]
        middle = ''
        last = ''

    elif len(name_parts) == 2:
        first, last = name_parts
        middle = ''

    else:
        first = name_parts[0]
        last = name_parts[-1]
        middle = ' '.join(name_parts[1:-1])

    # If there's a suffix, append it to the last name
    if suffix:
        last = f"{last}, {suffix}"

    return first, middle, last

# Examples
# names = [
#     "Bob Smith",
#     "Tom A. Jones",
#     "Derek Young, Jr.",
#     "Mary Ann Lee",
#     "John Paul Smith III",
#     "Jane"
# ]

# for name in names:
#     first, middle, last = split_name(name)
#     print(f"Full Name: {name}")
#     print(f"First Name: {first}")
#     print(f"Middle Name: {middle}")
#     print(f"Last Name: {last}")
#     print('-' * 30)


def process_election_data(input_csv, output_csv):
    """
    Read election data from a CSV, calculate additional dates, and write to a new CSV file.

    Args:
        input_csv (str): Path to the input CSV file.
        output_csv (str): Path to the output CSV file.
        term_years (int): Number of years for the elected term.
    """

    terms = get_terms("election_terms.csv")

    with open(input_csv, mode='r', newline='', encoding='utf-8-sig') as infile:
        reader = csv.DictReader(infile)
        fieldnames = reader.fieldnames + ['Term (years)', 'Office Start Date', 'Re-Election Date', 'Term End Date', 'First Name', 'Middle Name', 'Last Name']

        with open(output_csv, mode='w', newline='', encoding='utf-8') as outfile:
            writer = csv.DictWriter(outfile, fieldnames=fieldnames)
            writer.writeheader()

            for row in reader:
                # Parse the election date and extract the year
                # election_date = datetime.strptime(row['Election Date'], '%Y-%m-%d').date()
                election_date = datetime.strptime(row['Election Date'], '%m/%d/%y').date()
                election_year = election_date.year
                jurisdiction = row['Jurisdiction']
                office = row['Office']
                term_years = int(terms[jurisdiction + "/" + office])
                first, middle, last = split_name(row['Candidate Name'], get_special_names())

                # Calculate the additional dates using local_election_dates
                election_date, office_start_date, reelection_date, office_end_date = local_election_dates(election_year, term_years)

                # Add the new fields to the row
                # row['Election Year'] = election_year
                row['Term (years)'] = term_years
                row['Office Start Date'] = office_start_date.isoformat()
                row['Re-Election Date'] = reelection_date.isoformat()
                row['Term End Date'] = office_end_date.isoformat()
                row['First Name'] = first
                row['Middle Name'] = middle
                row['Last Name'] = last

                # Write the updated row to the new CSV
                writer.writerow(row)


# Example usage
process_election_data('all_years_complete.csv', 'processed_election_data.csv')


