def clean_names(input_file, output_file):
    with open(input_file, 'r') as file:
        raw_data = file.read()
    fixed_names = []
    unfixed_names = []
    name_blocks = raw_data.split('\n\n')
    for block in name_blocks:
        lines = block.strip().split('\n')
        if len(lines) > 2:
            unfixed_names.append(block)
        else:
            words1 = lines[0].split(' ')
            words2 = lines[1].split(' ')
            if len(words1) == 3 and len(words2) == 2 and words1[0] == words2[0]:
                fixed_names.append(lines[0] + "\t" + lines[1])
            elif len(words2) == 3 and len(words1) == 2 and words1[0] == words2[0]:
                fixed_names.append(lines[1] + "\t" + lines[0])
            else:
                unfixed_names.append(block)
    with open(output_file, 'w') as outfile:
        for string in fixed_names:
            outfile.write(string + '\n')
        for block in unfixed_names:
            outfile.write(block + '\n\n\n')

# Example usage
input_file = "more_name_variations.txt"
output_file = "more_name_variations2.txt"
clean_names(input_file, output_file)
print(f"Cleaned names saved to {output_file}.")
