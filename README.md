# cocodems
Code for the Columbia County Democrats

## Loading libraries
    source ccdems_env/bin/activate

## Requirements
    pip3 freeze > requirements.txt

## Code
* clean_election_report.py: cleans up the text extracted from a PDF file
* extract_election_results.py: extracts election result information from one of the test files on the Columbia County website
* extract_2024_election_results.py: extracts election results from April 2024, which are formatted differently than in other years
* extract_pdf.py: Saves the contents of a PDF to text
* get_jurisdictions.py: proof-of-concept code to get jurisdiction names and CiviCRM IDs
* parse_race_name.py: proof-of-concept code to parse a race name into office and jurisdiction
* standardize_alders.py: utility script to standardize naming conventions in the list of alderpersons
* standardize_names.py: utility script used to compile standard_names.csv, which is used to enforce conventions for candidates' names
* strip_function.py: used to test code. Doesn't really do anything.