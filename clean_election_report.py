def clean_election_report(input_file, output_file):
    with open(input_file, 'r') as infile:
        lines = infile.readlines()

    cleaned_lines = []
    skip_until = True
    
    for line in lines:
        # Remove lines starting with specific text
        if line.startswith("Columbia County Unofficial Results Report"):
            continue

        # Remove specific block of lines
        if line.strip() in [
            "ELECTION SUMMARY UNOFFICIAL RESULTS",
            "2024 PRESIDENTIAL PREFERENCE AND SPRING ELECTION",
            "APRIL 2, 2024 COLUMBIA COUNTY, WI"
        ]:
            continue

        # Remove lines that are just the word "TOTAL"
        if line.strip() == "TOTAL":
            continue

        # Skip lines until the target start line is found
        if skip_until:
            if line.strip() == "Circuit Court Judge Branch 3 Columbia County":
                cleaned_lines.append(line)
                skip_until = False
            continue

        # Remove text from lines starting with "Precincts Reporting"
        if line.startswith("Precincts Reporting"):
            cleaned_lines.append("\n")
            continue

        # Add remaining lines to cleaned_lines
        cleaned_lines.append(line)

    # Write the cleaned lines to the output file
    with open(output_file, 'w') as outfile:
        outfile.writelines(cleaned_lines)

# Example usage
input_file = "election_results.txt"
output_file = "cleaned_election_results.txt"
clean_election_report(input_file, output_file)
print(f"Cleaned election report saved to {output_file}.")
