import os
import re
import csv

# Function to process election data

def clean_candidate_name(name):
    # Remove trailing periods and spaces from the candidate name
    name = name.strip()
    if name.endswith('.'):
        name = name[:-1]
    while name.endswith('.  '):
        name = name[:-3]
    return name.strip()


def strip_up_to_nonpartisan(input_text):
    target_string = "(NONPARTISAN)"
    lines = input_text.strip().split('\n')

    # Find the index of the line containing the target string (case insensitive)
    start_index = 0
    for i, line in enumerate(lines):
        if target_string.lower() in line.lower():
            start_index = i + 1  # Include the target line itself
            break
    return "\n".join(lines[start_index:]).strip(), start_index


def get_jurisdictions(file_path):
    """
    Reads a CSV file and returns a dictionary where the keys are organization names
    of jurisdictions and the values are organization IDs.

    :param file_path: Path to the CSV file
    :return: Dictionary with organization names as keys and IDs as values
    """
    result_dict = {}
    # try:
    with open(file_path, 'r', encoding='utf-8-sig') as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
            organization_name = row['Organization Name']
            organization_id = row['ID']
            result_dict[organization_name] = organization_id
    return result_dict


def get_alders(file_path):
    """
    Reads a CSV file and returns a dictionary where the keys are the names of
    alderpersons and the values are the cities where they server.

    :param file_path: Path to the CSV file
    :return: Dictionary with alderperson names as keys and city names as values
    """
    result_dict = {}
    # try:
    with open(file_path, 'r', encoding='utf-8-sig') as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
            name = row['Name']
            city = row['City']
            result_dict[name] = city
    return result_dict


def get_candidate_standard_names(file_path):
    """
    Reads a CSV file and returns a dictionary where the keys are candidate names
    and the values are standardized versions of those names.

    :param file_path: Path to the CSV file
    :return: Dictionary with names as keys and standardized names as values
    """
    result_dict = {}
    # try:
    with open(file_path, 'r', encoding='utf-8-sig') as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
            alt_name = row['Alt Name']
            standardized_name = row['Standardized Name']
            result_dict[alt_name] = standardized_name
    return result_dict


def fix_case(text, fix_all = False):
    # Words to keep in lowercase unless they are the first word
    lowercase_exceptions = {"of", "in", "the", "on", "at", "for", "and", "or", "but", "to", "a", "an"}

    # Check if the text is all caps
    if text.isupper() or fix_all:
        words = text.split()
        result = []

        for i, word in enumerate(words):
            # Convert the first word or words not in exceptions to title case
            if i == 0 or word.lower() not in lowercase_exceptions:
                result.append(word.capitalize())
            else:
                result.append(word.lower())

        return " ".join(result)
    else:
        return(text)


def parse_race_name(race_name):
    """
    Parses a race name string and returns a dictionary with the office title and jurisdiction.

    :param race_name: The race name string to parse.
    :return: A dictionary with keys 'office' and 'jurisdiction'.
    """
    # List of possible jurisdiction types
    jurisdiction_types = ["City of", "Town of", "Village of", "School District"]

    # Handle school board races a little differently than other jurisdictions.
    if "School Board Member" in race_name:
        parts = race_name.split("School Board Member", 1)
        office = "School Board Member"
        jurisdiction = f"{parts[1].strip()}"
        return {"office": office, "jurisdiction": jurisdiction}
    else:
        # Iterate over jurisdiction types to find a match
        for jurisdiction_type in jurisdiction_types:
            if jurisdiction_type in race_name:
                parts = race_name.split(jurisdiction_type, 1)
                office = parts[0].strip()
                jurisdiction = f"{jurisdiction_type} {parts[1].strip()}"
                return {"office": office, "jurisdiction": jurisdiction}

    # If no jurisdiction type is found, return the whole string as the office
    return {"office": race_name.strip(), "jurisdiction": ""}


def process_election_data(input_file, output_file):
    with open(input_file, 'r') as file:
        raw_data = file.read()

    # Replace <CR><LF> with \n for proper splitting
    raw_data = raw_data.replace('\r\n', '\n')
    election_date = "04/02/24"

    # Split data into blocks for each race
    race_blocks = raw_data.split('\n\n')

    processed_data = []

    jurisdictions = get_jurisdictions("jurisdictions.csv")
    standardized_names = get_candidate_standard_names("standard_names.csv")
    for block in race_blocks:
        lines = block.strip().split('\n')

        if len(lines) < 2:
            continue

        # Extract the race name and number of seats
        race_name = lines[0].strip()
        seats_match = re.search(r'Vote For\s+(\d+)', lines[1].strip())
        if not seats_match:
            print("PROBLEM WITH", lines[1])
            print(lines)
            continue
        number_of_seats = int(seats_match[1])

        # Process candidate lines
        total_votes = 0
        candidates = []

        for line in lines[2:]:
            candidate_match = re.match(r'^(.*?)\s+(\d+[,.\d+]*)$', line)
            if candidate_match:
                candidate_name = fix_case(clean_candidate_name(candidate_match.group(1).strip()))
                if candidate_name in standardized_names:
                    candidate_name = standardized_names[candidate_name]
                votes_received = int(candidate_match.group(2).replace(',', ''))
                candidates.append((candidate_name, votes_received))
                total_votes += votes_received

        # Sort candidates by votes received in descending order
        candidates.sort(key=lambda x: x[1], reverse=True)

        excluded_candidates = ['Write-in', 'Yes', 'No']
        alders = get_alders("alders.csv")
        # Append data for each candidate to the processed_data list
        for i, (candidate_name, votes_received) in enumerate(candidates):
            percent_received = round((votes_received / total_votes) * 100, 1)
            elected = 1 if i < number_of_seats else 0
            if candidate_name not in excluded_candidates:
                jurisdiction = ""
                office = ""
                if race_name.startswith("Alderperson") and candidate_name in alders:
                    jurisdiction = alders[candidate_name]
                    office = race_name
                else:
                    race_fields = parse_race_name(race_name)
                    jurisdiction = race_fields['jurisdiction']
                    office = race_fields['office']
                processed_data.append({
                    "Jurisdiction": jurisdiction,
                    "Office": office,
                    "Race Name": race_name,
                    "Number of Seats": number_of_seats,
                    "Candidate Name": candidate_name,
                    "Votes Received": votes_received,
                    "Percent Received": percent_received,
                    "Total Votes": total_votes,
                    "Elected": elected,
                    "Election Date": election_date
                })

    # Write processed data to a CSV file
    election_date = election_date.replace('/','.')
    with open(output_file + '-' + election_date + ".csv", 'w', newline='') as csvfile:
        fieldnames = [
            "Jurisdiction", "Office",
            "Race Name", "Number of Seats", "Candidate Name", "Votes Received",
            "Percent Received", "Total Votes", "Elected", "Election Date"
        ]
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(processed_data)
    return processed_data


file_path = "cleaned_election_results.txt"
output_file = "election_results"
print(f"Processing file: {file_path}")
result = process_election_data(file_path, output_file)
race_names = []
for row in result:
    race_names.append(row["Race Name"])

with open("race_names_2024", 'w') as outfile:
    for string in race_names:
        outfile.write(string + '\n')
