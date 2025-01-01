import csv


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


# Example usage
alders = get_alders("alders.csv")
standard_names = get_candidate_standard_names("standard_names.csv")
standardized_alders = {}
for name, city in alders.items():
    if name in standard_names:
        standardized_alders[standard_names[name]] = city
    else:
        standardized_alders[name] = city

with open("alders_standardized.csv", 'w', newline='') as csvfile:
    writer = csv.writer(csvfile)
    
    # Write the header
    writer.writerow(["Name", "City"])
    
    # Write the keys and values
    for key, value in standardized_alders.items():
        writer.writerow([key, value])
