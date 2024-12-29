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


def fix_case(text):
    # Words to keep in lowercase unless they are the first word
    lowercase_exceptions = {"of", "in", "the", "on", "at", "for", "and", "or", "but", "to", "a", "an"}

    # Check if the text is all caps
    if text.isupper():
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


def process_election_data(input_file, output_file):
    with open(input_file, 'r') as file:
        raw_data = file.read()

    # Replace <CR><LF> with \n for proper splitting
    raw_data = raw_data.replace('\r\n', '\n')
    raw_data = raw_data.replace("SCHOOL\n          DISTRICT", "SCHOOL DISTRICT")

    # Extract and remove header
    header_match = re.search(r'SUMMARY.*?RUN DATE:(\d{2}/\d{2}/\d{2}).*?\n\n', raw_data, re.DOTALL)
    election_date = ''
    if header_match:
        election_date = header_match.group(1)
        print(election_date)
        trimmed_out_national, start_index = strip_up_to_nonpartisan(raw_data)
        if start_index > 0:
            raw_data = trimmed_out_national
        else:
            raw_data = raw_data[header_match.end():]

    # Remove footer
    raw_data = re.sub(r'</PRE>\s*</HTML>', '', raw_data, flags=re.DOTALL)

    # Split data into blocks for each race
    if start_index > 0:
        race_blocks = raw_data.split('\n\n')
    else:
        race_blocks = raw_data.split('\n\n')[2:]

    processed_data = []

    for block in race_blocks:
        lines = block.strip().split('\n')

        if len(lines) < 2:
            continue

        # Extract the race name and number of seats
        race_name = lines[0].strip()
        seats_match = re.search(r'\(VOTE FOR\)\s+(\d+)', lines[1].strip())
        if not seats_match:
            seats_match = re.search(r'\(Vote for Not More Than \)\s+(\d+)', lines[1].strip())
        if not seats_match:
            seats_match = re.search(r'Vote for not more than\s+(\d+)', lines[1].strip())
        if not seats_match:
            print("PROBLEM WITH", lines[1])
            print(lines)
            continue

        # number_of_seats = int(seats_match.group(2))
        number_of_seats = int(seats_match[1])

        # Process candidate lines
        total_votes = 0
        candidates = []

        for line in lines[2:]:
            candidate_match = re.match(r'^(.*?)\.\s+\.*\s+(\d+[,.\d+]*)\s+(\d+[,.\d+]*)$', line)
            if candidate_match:
                candidate_name = clean_candidate_name(candidate_match.group(1).strip())
                votes_received = int(candidate_match.group(2).replace(',', ''))
                percent_received = float(candidate_match.group(3))
                candidates.append((candidate_name, votes_received, percent_received))
                total_votes += votes_received

        # Sort candidates by votes received in descending order
        candidates.sort(key=lambda x: x[1], reverse=True)

        # Append data for each candidate to the processed_data list
        for i, (candidate_name, votes_received, percent_received) in enumerate(candidates):
            elected = 1 if i < number_of_seats else 0
            processed_data.append({
                "Race Name": fix_case(race_name),
                "Number of Seats": number_of_seats,
                "Candidate Name": fix_case(candidate_name),
                "Votes Received": votes_received,
                "Percent Received": percent_received,
                "Total Votes": total_votes,
                "Elected": elected,
                "Election Date": election_date
            })

    # Write processed data to a CSV file
    election_date = election_date.replace('/','.')
    with open(output_file + '-' + election_date, 'w', newline='') as csvfile:
        fieldnames = [
            "Race Name", "Number of Seats", "Candidate Name", "Votes Received",
            "Percent Received", "Total Votes", "Elected", "Election Date"
        ]
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(processed_data)


def process_html_files(directory_path):
    """
    Iterates over a directory and opens every file ending with ".html".

    :param directory_path: Path to the directory to iterate over.
    """
    output_file = "election_results"
    try:
        for filename in os.listdir(directory_path):
            if filename.endswith(".html"):
                file_path = os.path.join(directory_path, filename)
                print(f"Processing file: {file_path}")
                process_election_data(file_path, output_file)
    except Exception as e:
        print(f"An error occurred: {e}")


# Example usage
directory_path = "../election results"
process_html_files(directory_path)
