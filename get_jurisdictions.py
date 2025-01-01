import csv

def csv_to_dict(file_path):
    """
    Reads a CSV file and returns a dictionary where the keys are organization names
    and the values are organization IDs.

    :param file_path: Path to the CSV file
    :return: Dictionary with organization names as keys and IDs as values
    """
    result_dict = {}
    # try:
    with open(file_path, 'r', encoding='utf-8-sig') as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
            print(row)
            organization_name = row['Organization Name']
            organization_id = row['ID']
            result_dict[organization_name] = organization_id
    # except Exception as e:
    #     print(f"Error reading the CSV file: {e}")
    return result_dict

# Example usage
file_path = "jurisdictions.csv"  # Replace with your CSV file path
organization_dict = csv_to_dict(file_path)
print(organization_dict)
