
lines = []
with open('j:/Development/Python/dictation-helper/app.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Target range: Line 97 to 363 (1-based) -> Index 96 to 362
start_index = 96
end_index = 363 # Go up to line 363 inclusive

new_lines = []
for i, line in enumerate(lines):
    if start_index <= i < end_index:
        if line.startswith("        "):
            new_lines.append(line[4:])
        elif line.strip() == "":
            new_lines.append(line) # Keep empty lines
        else:
            # If it doesn't start with 8 spaces but is in the block, it might be a weirdly indented line or empty.
            # Just keep it if it's not 8 spaces but warn?
            # Actually, if it's less than 8 spaces, it shouldn't happen in a valid block unless it's empty.
            new_lines.append(line)
    else:
        new_lines.append(line)

with open('j:/Development/Python/dictation-helper/app.py', 'w', encoding='utf-8') as f:
    f.writelines(new_lines)

print("Indentation fixed.")
