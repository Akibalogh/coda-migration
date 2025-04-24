import fitz  # PyMuPDF

pdf_path = "DLC.link Wiki.pdf"
output_path = "extracted_headers.txt"

doc = fitz.open(pdf_path)
sections = []

for page_number in range(len(doc)):
    page = doc[page_number]
    blocks = page.get_text("dict")["blocks"]
    for b in blocks:
        if "lines" in b:
            for l in b["lines"]:
                for span in l["spans"]:
                    text = span["text"].strip()
                    size = span["size"]
                    if len(text) > 0 and size > 14 and len(text) < 100:
                        sections.append((page_number + 1, text))
                        break  # only take first heading-sized text per line

# Save to text file
with open(output_path, "w") as f:
    for page_num, header in sections:
        f.write(header + "\n")

# Show in console
for page_num, header in sections:
    print(f"Page {page_num}: {header}")
