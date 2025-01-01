import os

def process_html_files(directory_path):
    """
    Iterates over a directory and opens every file ending with ".html".

    :param directory_path: Path to the directory to iterate over.
    """
    try:
        for filename in os.listdir(directory_path):
            if filename.endswith(".html"):
                file_path = os.path.join(directory_path, filename)
                print(f"Processing file: {file_path}")
                
                # with open(file_path, 'r') as file:
                #     content = file.read()
                #     # Perform processing on the file content if needed
                #     print(f"Content of {filename[:50]}...\n")
    except Exception as e:
        print(f"An error occurred: {e}")

# Example usage
directory_path = "../election results"

process_html_files(directory_path)
