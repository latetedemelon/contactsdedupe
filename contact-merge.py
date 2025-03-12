#!/usr/bin/env python3
import argparse
import csv
import re
import sys
from collections import OrderedDict

import vobject
from rapidfuzz import fuzz

##############################
# Helper functions
##############################

def normalize_phone(phone):
    """Remove non-digit characters from a phone number."""
    return re.sub(r'\D', '', phone)

def compute_match_score(contact_a, contact_b):
    """
    Compute an average fuzzy match score between two contacts based on:
      - Telephone numbers (supports multiple numbers separated by semicolons)
      - Email addresses (supports multiple emails separated by semicolons)
      - Full name (using token_set_ratio to handle partial or unordered name matches)
    """
    scores = []

    # Compare telephone numbers if available
    if contact_a.get('tel') and contact_b.get('tel'):
        phones_a = [normalize_phone(p) for p in contact_a['tel'].split(';') if p.strip()]
        phones_b = [normalize_phone(p) for p in contact_b['tel'].split(';') if p.strip()]
        phone_scores = []
        for pa in phones_a:
            for pb in phones_b:
                if pa and pb:
                    phone_scores.append(fuzz.ratio(pa, pb))
        if phone_scores:
            scores.append(max(phone_scores))

    # Compare email addresses if available
    if contact_a.get('email') and contact_b.get('email'):
        emails_a = [p.strip().lower() for p in contact_a['email'].split(';') if p.strip()]
        emails_b = [p.strip().lower() for p in contact_b['email'].split(';') if p.strip()]
        email_scores = []
        for ea in emails_a:
            for eb in emails_b:
                if ea and eb:
                    email_scores.append(fuzz.ratio(ea, eb))
        if email_scores:
            scores.append(max(email_scores))

    # Compare full names using token_set_ratio to handle cases where names are partial or unordered
    if contact_a.get('fn') and contact_b.get('fn'):
        name_score = fuzz.token_set_ratio(contact_a['fn'], contact_b['fn'])
        scores.append(name_score)

    if scores:
        return sum(scores) / len(scores)
    else:
        return 0

def merge_contacts(master, duplicate):
    """
    Merge information from duplicate into master.
    For each field (except uid, match, certainty), if master is empty, use duplicate;
    if both exist and are different and not already combined, append with a semicolon.
    """
    for key, value in duplicate.items():
        if key in ['uid', 'match', 'certainty']:
            continue
        dup_value = value.strip()
        master_value = master.get(key, "").strip()
        if not master_value and dup_value:
            master[key] = dup_value
        elif dup_value and dup_value not in master_value.split(';'):
            master[key] = master_value + ';' + dup_value if master_value else dup_value

def compute_field_order(contacts):
    """
    Compute the order of fields as first encountered (ignoring 'match' and 'certainty').
    """
    order = []
    for contact in contacts:
        for key in contact.keys():
            if key in ['match', 'certainty']:
                continue
            if key not in order:
                order.append(key)
    return order

##############################
# Import/Export functions
##############################

def parse_vcf_to_contacts(vcf_filename):
    """
    Reads a VCF file and converts each vCard into an OrderedDict.
    All fields from the vCard are preserved in the order they appear.
    Each contact is assigned a unique id stored in the 'uid' field.
    """
    contacts = []
    with open(vcf_filename, 'r', encoding='utf-8') as f:
        vcards = vobject.readComponents(f.read())
        for idx, vcard in enumerate(vcards):
            contact = OrderedDict()
            contact['uid'] = str(idx)
            # vcard.contents is already an OrderedDict; iterate to preserve order
            for key, items in vcard.contents.items():
                values = []
                for item in items:
                    try:
                        value = str(item.value)
                    except Exception:
                        value = ''
                    values.append(value)
                contact[key] = ';'.join(values)
            # Initialize deduplication fields
            contact['match'] = ""
            contact['certainty'] = ""
            contacts.append(contact)
    return contacts

def import_csv_to_contacts(csv_filename):
    """
    Reads a CSV file (assumed to have headers) and returns a list of OrderedDict.
    """
    contacts = []
    with open(csv_filename, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            contact = OrderedDict(row)
            contacts.append(contact)
    return contacts

def write_contacts_to_csv(contacts, csv_filename, field_order):
    """
    Writes contacts to a CSV file.
    The CSV will have two leading columns ('match' and 'certainty') followed by the fields in field_order.
    """
    header = ['match', 'certainty'] + field_order
    with open(csv_filename, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=header)
        writer.writeheader()
        for contact in contacts:
            writer.writerow(contact)

def write_contacts_to_vcf(contacts, vcf_filename, field_order):
    """
    Writes contacts to a VCF file.
    The export does not include the 'match' or 'certainty' fields.
    Fields are written in the order provided by field_order.
    """
    with open(vcf_filename, 'w', encoding='utf-8') as f:
        for contact in contacts:
            card = vobject.vCard()
            for key in field_order:
                if key in contact:
                    try:
                        card.add(key).value = contact[key]
                    except Exception as e:
                        print(f"Warning: Could not add field {key} with value {contact[key]}: {e}")
            f.write(card.serialize())
            f.write("\n")

##############################
# Deduplication functions
##############################

def deduplicate_contacts(contacts, threshold=80, merge=False, dry_run=False):
    """
    Deduplicate contacts by comparing telephone, email, and full name.
    
    If merge is False:
      - For each contact (after the first), compare with earlier contacts.
      - If a match score exceeds the threshold, set the contact's 'match' and 'certainty' fields.
      - Returns the list of contacts (all are kept).
    
    If merge is True:
      - Compares each contact against master contacts.
      - If a match is found above threshold:
           * In dry_run mode, prints the potential merge action.
           * Otherwise, merges the duplicate into the master contact (merging all fields) and excludes the duplicate.
      - Returns only the master contacts.
    """
    if not merge:
        # Linking mode: compare each contact with all previous ones.
        for i in range(1, len(contacts)):
            current = contacts[i]
            for j in range(i):
                candidate = contacts[j]
                score = compute_match_score(current, candidate)
                if score >= threshold:
                    current['match'] = candidate['uid']
                    current['certainty'] = str(score)
                    break  # Stop at the first match found
        return contacts
    else:
        # Merging mode: only keep master contacts.
        masters = []
        for contact in contacts:
            found_match = False
            for master in masters:
                score = compute_match_score(contact, master)
                if score >= threshold:
                    found_match = True
                    if dry_run:
                        print(f"DRY RUN: Would merge contact UID {contact['uid']} into master UID {master['uid']} with score {score:.2f}")
                    else:
                        merge_contacts(master, contact)
                    break
            if not found_match:
                masters.append(contact)
        return masters

##############################
# Main function with CLI
##############################

def main():
    parser = argparse.ArgumentParser(description="VCF/CSV deduplication and conversion tool.")
    parser.add_argument("--input-file", required=True, help="Path to input file (VCF or CSV).")
    parser.add_argument("--input-format", choices=["vcf", "csv"], required=True, help="Format of the input file.")
    parser.add_argument("--output-file", required=True, help="Path to output file.")
    parser.add_argument("--output-format", choices=["vcf", "csv"], required=True, help="Desired output format.")
    parser.add_argument("--threshold", type=float, default=80, help="Match threshold (default: 80).")
    parser.add_argument("--merge", action="store_true", help="Automatically merge duplicates above threshold.")
    parser.add_argument("--dry-run", action="store_true", help="Perform a dry run of merging (print matches to terminal without modifying data).")
    args = parser.parse_args()

    # Import contacts from input file
    if args.input_format == "vcf":
        contacts = parse_vcf_to_contacts(args.input_file)
    else:
        contacts = import_csv_to_contacts(args.input_file)

    if not contacts:
        print("No contacts found in the input file.")
        sys.exit(1)

    # Compute field order (excluding deduplication fields) based on first encountered order
    field_order = compute_field_order(contacts)

    # Deduplicate contacts (either linking or merging)
    deduped_contacts = deduplicate_contacts(contacts, threshold=args.threshold, merge=args.merge, dry_run=args.dry_run)
    
    # If in dry-run mode for merging, exit without writing output.
    if args.merge and args.dry_run:
        print("Dry run complete. No changes have been made.")
        sys.exit(0)

    # Export contacts to output file in the desired format
    if args.output_format == "csv":
        write_contacts_to_csv(deduped_contacts, args.output_file, field_order)
        print(f"Exported {len(deduped_contacts)} contacts to CSV: {args.output_file}")
    else:
        write_contacts_to_vcf(deduped_contacts, args.output_file, field_order)
        print(f"Exported {len(deduped_contacts)} contacts to VCF: {args.output_file}")

if __name__ == "__main__":
    main()
