import io
import re

from pypdf import PdfReader


class SubmissionPdfError(ValueError):
    pass


def extract_registration_rows(pdf_bytes: bytes) -> tuple[list[dict[str, str]], int]:
    """Read bulk participant rows from table exports or one response per page."""
    try:
        reader = PdfReader(io.BytesIO(pdf_bytes), strict=False)
        pages = [page.extract_text(extraction_mode="layout") or "" for page in reader.pages]
    except Exception as exc:
        raise SubmissionPdfError("The uploaded file could not be read as a PDF.") from exc

    output: list[dict[str, str]] = []
    email_pattern = re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.I)
    name_header = re.compile(r"\b(?:(?:participant(?:'s)?|student|applicant|registrant|candidate|full)\s+)?name\b", re.I)
    phone_header = re.compile(r"\b(?:phone(?:\s+(?:number|no\.?))?|mobile(?:\s+(?:number|no\.?))?|cell(?:\s+phone)?|contact\s+(?:number|no\.?|phone)|telephone)\b", re.I)
    email_header = re.compile(r"\bemail(?:\s+(?:address|id))?\b", re.I)
    skipped = 0

    for page_text in pages:
        lines = page_text.splitlines()
        header_info = None
        for header_index, header in enumerate(lines):
            names = list(name_header.finditer(header))
            phones = list(phone_header.finditer(header))
            emails = list(email_header.finditer(header))
            if names and phones:
                # When a sheet includes both Email Address (Google account)
                # and Email (form answer), use the exact Email header.
                exact_emails = [match for match in emails if not re.match(r"\s+address", header[match.end():], re.I)]
                preferred_name = re.search(r"\b(?:participant(?:'s)?|student|applicant|registrant|candidate|full)\s+name\b", header, re.I)
                name_column = preferred_name or next((m for m in names if not re.search(r"\b(?:project|college|institution|university)\s+$", header[max(0, m.start()-24):m.start()], re.I)), names[0])
                header_info = (header_index, header, name_column, phones[-1], (exact_emails or emails)[-1] if emails else None)
                break
        if not header_info:
            continue
        header_index, header, name_match, phone_match, email_match = header_info
        columns = {"name": name_match.start(), "phone": phone_match.start(), "email": email_match.start() if email_match else -1}
        email_address_match = re.search(r"\bemail\s+address\b", header, re.I)
        email_address_col = email_address_match.start() if email_address_match else -1

        # Also use common neighbouring headers as cell boundaries, so phone
        # columns remain isolated when colleges/branches are placed beside them.
        boundary_patterns = [
            r"\btimestamp\b", email_header.pattern, name_header.pattern,
            phone_header.pattern,
            r"\b(?:roll|registration|application)\s*(?:number|no\.?|id)\b",
            r"\b(?:college|institution|university)\b", r"\bbranch\b",
            r"\byear\s+of\s+study\b", r"\bdepartment\b", r"\bcourse\b",
            r"\bdomains?\b", r"\bproject(?:\s+idea)?\b",
            r"\bprevious\s+hackathon\s+experience\b",
        ]
        known_starts = sorted({m.start() for pattern in boundary_patterns for m in re.finditer(pattern, header, re.I)})

        def cell(line: str, column: int) -> str:
            next_columns = [start for start in known_starts if start > column]
            end = min(next_columns) if next_columns else len(line)
            return line[column:end].strip()

        for line in lines[header_index + 1:]:
            if not line.strip() or line == header:
                continue
            name = cell(line, columns["name"])
            if len(name) < 2 and email_address_col >= 0:
                overflow = line[email_address_col:columns["name"]]
                boundary = re.search(r"@[a-z0-9.-]+(?=[A-Z])", overflow)
                if boundary:
                    name = (overflow[boundary.end():] + name).strip()
            phone_cell = cell(line, columns["phone"])
            phone_match_value = re.search(r"\+?\d[\d\s().-]{5,}\d", phone_cell)
            phone = re.sub(r"\D", "", phone_match_value.group(0)) if phone_match_value else ""
            # Most tables have one response per printed line. For exports with
            # no timestamp, a populated phone column is the row discriminator.
            if not phone and not re.match(r"\s*\d{1,2}/\d{1,2}/\d{4}\b", line):
                continue
            if len(name) < 2 or len(phone) < 7:
                skipped += 1
                continue
            email_cell = cell(line, columns["email"]) if columns["email"] >= 0 else ""
            email_matches = list(email_pattern.finditer(email_cell))
            email_match = email_matches[-1] if email_matches else None
            if not email_match and email_address_col >= 0:
                responder_email_cell = cell(line, email_address_col)
                email_match = email_pattern.search(responder_email_cell)
            if not email_match:
                # Keep a clipped/missing email empty rather than guessing it.
                all_line_emails = list(email_pattern.finditer(line))
                email_match = all_line_emails[-1] if all_line_emails else None
            output.append({"participant_name": name[:200], "phone": phone[:60], "email": email_match.group(0).lower() if email_match else ""})

    # Some hosts receive a PDF with one labelled response per page instead of
    # a response table. Parse each page separately so values cannot bleed
    # across participants. Never parse a multi-page document as one response.
    if not output:
        for page_text in pages:
            if not page_text.strip():
                continue
            details = _parse_form_details_text(page_text)
            names = details.get("participant_names") or []
            phone = re.sub(r"\D", "", str(details.get("phone", "")))
            email_match = email_pattern.search(str(details.get("email", "")))
            if len(names) == 1 and len(phone) >= 7:
                output.append({"participant_name": names[0][:200], "phone": phone[:60], "email": email_match.group(0).lower() if email_match else ""})
            elif names or phone or details.get("email"):
                skipped += 1
        if output:
            unique: dict[tuple[str, str], dict[str, str]] = {}
            for row in output:
                unique.setdefault((row["participant_name"].strip().casefold(), row["phone"]), row)
            return list(unique.values()), skipped
        text = "\n".join(pages)
        if not text.strip():
            raise SubmissionPdfError("No selectable text was found. Upload a text-based Google Forms responses PDF.")
        raise SubmissionPdfError("Could not read participant rows. Use a searchable PDF with a table header containing Name and Phone (Email is optional), or one labelled participant response per page.")
    # Deduplicate identical rows that may be repeated at page boundaries.
    unique: dict[tuple[str, str], dict[str, str]] = {}
    for row in output:
        key = (row["participant_name"].strip().casefold(), row["phone"])
        unique.setdefault(key, row)
    return list(unique.values()), skipped


FIELD_PATTERNS = {
    "application_number": r"application\s*(?:number|no\.?|id)|registration\s*(?:number|no\.?|id)|registered\s*id",
    "project_name": r"project\s*name|name\s*of\s*project",
    "participant_names": r"name|full\s*name|participant(?:s)?\s*name(?:s)?|name(?:s)?\s*of\s*participant(?:s)?|team\s*member(?:s)?",
    "phone": r"phone(?:\s*(?:number|no\.?))?|mobile(?:\s*(?:number|no\.?))?|contact\s*number",
    "email": r"e-?mail(?:\s*address)?",
    "college_name": r"college(?:\s*name)?|institution(?:\s*name)?",
    "problem_statement": r"problem\s*statement|what\s*problem(?:s)?",
    "solution_description": r"solution\s*description|project\s*description|description|describe\s*(?:your\s*)?(?:project|solution)",
}
ALL_LABELS = "|".join(f"(?:{pattern})" for pattern in FIELD_PATTERNS.values())


def _parse_form_details_text(text: str) -> dict:
    text = re.sub(r"[\t\u00a0]+", " ", text).replace("\r", "\n")
    labels = re.compile(rf"(?im)^\s*(?:\d+[.)]\s*)?(?P<label>{ALL_LABELS})\s*(?:\([^)]*\))?\s*[:?]?\s*(?P<inline>[^\n]*)$")
    found = {}
    matches = list(labels.finditer(text))
    for index, match in enumerate(matches):
        label = re.sub(r"\s+", " ", match.group("label").lower()).strip()
        field = next((key for key, pattern in FIELD_PATTERNS.items() if re.fullmatch(pattern, label, re.I)), None)
        if field is None:
            continue
        value = match.group("inline").strip()
        if not value:
            end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
            value = text[match.end():end].strip()
        value = re.sub(r"\s+", " ", value).strip(" :-\n")
        if field == "participant_names":
            found[field] = [name.strip() for name in re.split(r"[,;\n]+", value) if name.strip()]
        elif value:
            found[field] = value
    return found


def extract_form_details(pdf_bytes: bytes, required_fields: set[str] | None = None) -> tuple[dict, str]:
    try:
        reader = PdfReader(io.BytesIO(pdf_bytes), strict=False)
        text = "\n".join(page.extract_text() or "" for page in reader.pages)
    except Exception as exc:
        raise SubmissionPdfError("The uploaded file could not be read as a PDF.") from exc

    found = _parse_form_details_text(text)

    required_fields = required_fields or {"project_name", "participant_names", "problem_statement", "solution_description"}
    missing = [field.replace("_", " ") for field in required_fields if not found.get(field)]
    if missing:
        if not text.strip():
            raise SubmissionPdfError("No selectable text was found. Upload a text-based Google Form response PDF; scanned PDFs are not supported yet.")
        if required_fields == {"participant_names", "phone", "email"}:
            expected = "Use headings Name, Phone, and Email. Make sure the PDF contains selectable text."
        else:
            expected = "Use headings Project Name, Participant Name, Problem Statement, and Description."
        raise SubmissionPdfError("Could not find these fields in the PDF: " + ", ".join(sorted(missing)) + ". " + expected)
    if not isinstance(found.get("participant_names"), list):
        found["participant_names"] = [str(found["participant_names"])]
    return found, text[:50000]
