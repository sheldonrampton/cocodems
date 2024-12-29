import pdfplumber

# Function to extract text from PDF
def extract_text_from_pdf(pdf_path, output_text_file):
    with pdfplumber.open(pdf_path) as pdf:
        all_text = ''
        for page in pdf.pages:
            all_text += page.extract_text() + '\n'
    # Save the extracted text to a file
    with open(output_text_file, 'w') as file:
        file.write(all_text)

# Example usage
pdf_path = "../election results/2024-april.pdf"  # Replace with your PDF file path
output_text_file = "election_results.txt"
extract_text_from_pdf(pdf_path, output_text_file)

print(f"Text extracted and saved to {output_text_file}.")
