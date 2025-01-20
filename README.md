# cocodems
Code for the Columbia County Democrats

## Loading libraries
    source ccdems_env/bin/activate

## Requirements
    pip3 freeze > requirements.txt

## Code
* clean_election_report.py: cleans up the text extracted from a PDF file.
* enhance_csv.py: calculates some additional rows to add to the data.
* extract_2024_election_results.py: extracts election results from April 2024, which are formatted differently than in other years. This Python script can probably be deleted, because it was incorporated into extract_election_results.py.
* extract_election_results.py: extracts election result information from one of the test files on the Columbia County website
* extract_fall_election_results.py: extracts election results from fall elections, which are formatted differently than April elections. This Python script was NOT incorporated into extract_election_results.py.
* extract_pdf.py: Saves the contents of a PDF for the April 2024 election to a textfile (election_results.txt)
* get_jurisdictions.py: proof-of-concept code to get jurisdiction names and CiviCRM IDs
* parse_race_name.py: proof-of-concept code to parse a race name into office and jurisdiction
* standardize_alders.py: utility script to standardize naming conventions in the list of alderpersons
* standardize_names.py: utility script used to compile standard_names.csv, which is used to enforce conventions for candidates' names
* strip_function.py: used to test code. Doesn't really do anything.

# Info files
* alders_standardized: Intermediate file, probably can be deleted.
* alders.csv: A list of alderpersons and the cities that are their jurisdictions
* all_fall_years.csv: elections results from fall elections
* all_years.csv: manually created by combining April and fall elections into a single CSV
* all_years_complete.csv: finalized changes to all years
* cleaned_election_results.txt: a cleaned-up text file with 2024 April election results
* election_terms.csv: the term length of each elected office in years
* election_results.txt: Text extracted from the PDF for the April 2024 election
* jurisdictions.csv: jurisdictions exported from CiviCRM
* missing_jurisdictions.csv: jurisdictions that were not in CiviCRM
* processed_election_data.csv: the final election data file which computes some additional fields such as term start and end dates, re-election date, and breaks out candidate first, middle and last names
* processed_election_data.xlsx: has a little manual cleanup to include things such as a recall election
* standard_names.csv: A list of alt names and the standard names that should be used in their place; used to clean up some inconsistencies
* unusual_names.csv: A list of some names that are unusual and can't be automatically parsed into first, middle and last
