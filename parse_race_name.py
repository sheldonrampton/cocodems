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
    return {"office": race_name.strip(), "jurisdiction": None}

# Example usage
examples = [
    "Village Trustee Village of Friesland",
    "Village Trustee Village of Arlington",
    "Town Board Supervisor 1 Town of Fountain Prairie",
    "School Board Member Rio Community School District",
    "Mayor City of Lodi"
]

for race_name in examples:
    parsed = parse_race_name(race_name)
    print(parsed)
