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


def process_election_data(input_file, output_file):
    with open(input_file, 'r') as file:
        raw_data = file.read()

    # Replace <CR><LF> with \n for proper splitting
    raw_data = raw_data.replace('\r\n', '\n')

    # Extract and remove header
    header_match = re.search(r'ELECTION SUMMARY.*?RUN DATE:(\d{2}/\d{2}/\d{2}).*?\n\n', raw_data, re.DOTALL)
    election_date = ''
    if header_match:
        election_date = header_match.group(1)
        print(election_date)
        raw_data = raw_data[header_match.end():]

    # Remove footer
    raw_data = re.sub(r'</PRE>\s*</HTML>', '', raw_data, flags=re.DOTALL)

    # Split data into blocks for each race
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
            print("PROBLEM WITH", lines[1])
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
    with open(output_file + '-' + election_date, 'w', newline='') as csvfile:
        fieldnames = [
            "Race Name", "Number of Seats", "Candidate Name", "Votes Received",
            "Percent Received", "Total Votes", "Elected", "Election Date"
        ]
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(processed_data)

# Example usage
input_file = "../election results/2022-april.html"  # Replace with the path to your input HTML file
output_file = "election_results"  # Replace with the desired output CSV file name
process_election_data(input_file, output_file)

print(f"Election data processed and saved to {output_file}.")
