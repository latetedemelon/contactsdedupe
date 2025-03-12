# Contacts Deduplicator
1. Importing Data:
For VCF input, it uses vobject to parse each vCard and stores each contact as an ordered dictionary (thus preserving field order).
For CSV input, it reads rows (preserving header order).
2. Deduplication:
The function deduplicate_contacts compares each contact (using RapidFuzz’s fuzzy matching on phone, email, and full name).
In linking mode (default when --merge is not provided), it sets “match” and “certainty” fields without merging records.
In merging mode (when --merge is specified), it either merges duplicate contacts (by combining field values) or, if --dry-run is specified, prints out the potential merges without modifying the data.
3. Exporting Data:
For CSV output, it writes a file that begins with “match” and “certainty” columns followed by all other fields in the order they were first encountered.
For VCF output, it exports only the original vCard fields (excluding “match” and “certainty”), preserving the field order.
You can run the script from the command line. For example, to merge duplicates from a VCF file and export the merged result to CSV:


# How to Use
1. Download or clone the source code
2. Open terminal inside the downloaded folder
3. `pip install -r requirements.txt`
5. `python contact-merge.py --input-file contacts.vcf --input-format vcf --output-file output.vsf --output-format vsf --threshold 85`

# Dry Run Example with Merge
```bash
python script.py --input-file contacts.vcf --input-format vcf --output-file output.csv --output-format csv --threshold 85 --merge --dry-run
```
# Merge Example

```bash
python script.py --input-file contacts.vcf --input-format vcf --output-file output.csv --output-format csv --threshold 85 --merge
```
