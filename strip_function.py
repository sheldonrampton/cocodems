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
print(local_election_dates(2024, 2))
print(local_election_dates(2024, 3))
