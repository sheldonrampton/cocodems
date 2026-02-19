import argparse
import csv
import os
import re
from dataclasses import dataclass
from datetime import date, timedelta
import calendar

import pdfplumber
import psycopg2
from dotenv import load_dotenv


ELECTION_DATE = date(2025, 4, 1)
OUTPUT_CSV = "election_2025.csv"


def _shared_load_dotenv() -> None:
    shared_dotenv_path = os.getenv(
        "COCODEMS_ENV_FILE",
        os.path.expanduser("~/.config/cocodems_elections/.env"),
    )
    if os.path.exists(shared_dotenv_path):
        load_dotenv(dotenv_path=shared_dotenv_path, override=True)
    else:
        load_dotenv(override=True)


def get_db_connection():
    return psycopg2.connect(
        dbname=os.getenv("DB_NAME"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        host=os.getenv("DB_HOST"),
        port=os.getenv("DB_PORT"),
    )


def fourth_monday_in_april(year: int) -> date:
    april_first = date(year, 4, 1)
    fourth_monday_offset = 21 + (calendar.MONDAY - april_first.weekday() + 7) % 7
    return april_first + timedelta(days=fourth_monday_offset)


def first_tuesday_in_april(year: int) -> date:
    april_first = date(year, 4, 1)
    days_until_tuesday = (calendar.TUESDAY - april_first.weekday() + 7) % 7
    return april_first + timedelta(days=days_until_tuesday)


@dataclass
class ParsedCandidate:
    candidate_name: str
    votes: int
    percent: float | None


@dataclass
class ParsedRace:
    raw_title: str
    seats_to_fill: int | None
    candidates: list[ParsedCandidate]
    write_in_votes: int


_VOTE_FOR_RE = re.compile(r"^Vote\s+for\s+(?P<n>\d+)\b", re.IGNORECASE)
_PRECINCTS_RE = re.compile(r"^Precincts\s+Reporting\b", re.IGNORECASE)
_WRITEIN_RE = re.compile(r"^Write-?in\s+Totals\b", re.IGNORECASE)
_TOTAL_LINE_RE = re.compile(r"^TOTAL$", re.IGNORECASE)
_REPORT_HEADER_RE = re.compile(r"^ELECTION SUMMARY\b", re.IGNORECASE)
_SPRING_ELECTION_RE = re.compile(r"\bSPRING ELECTION\b", re.IGNORECASE)
_REPORT_FOOTER_RE = re.compile(r"\bUnofficial Results Report\b", re.IGNORECASE)


def _normalize_space(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip())


def _parse_int_maybe(s: str) -> int | None:
    s = (s or "").strip().replace(",", "")
    if not s:
        return None
    try:
        return int(s)
    except ValueError:
        return None


def _parse_percent_maybe(s: str) -> float | None:
    s = (s or "").strip().replace("%", "")
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _split_candidate_line(line: str) -> ParsedCandidate | None:
    """Try to parse a candidate row.

    We expect something like:
        Jane Q. Public  1,234  56.78%
    but we tolerate missing percent:
        Jane Q. Public  1,234

    Returns None if the line does not look like a candidate row.
    """
    line = _normalize_space(line)
    if not line:
        return None

    if _WRITEIN_RE.search(line) or _PRECINCTS_RE.search(line):
        return None

    # Prefer a percent at end.
    m = re.match(r"^(?P<name>.+?)\s+(?P<votes>[\d,]+)\s+(?P<pct>\d+(?:\.\d+)?)%?$", line)
    if m:
        votes = _parse_int_maybe(m.group("votes"))
        if votes is None:
            return None
        pct = _parse_percent_maybe(m.group("pct"))
        return ParsedCandidate(candidate_name=m.group("name").strip(), votes=votes, percent=pct)

    # If it ends with votes only.
    m = re.match(r"^(?P<name>.+?)\s+(?P<votes>[\d,]+)$", line)
    if m:
        votes = _parse_int_maybe(m.group("votes"))
        if votes is None:
            return None
        return ParsedCandidate(candidate_name=m.group("name").strip(), votes=votes, percent=None)

    return None


def extract_text_lines(pdf_path: str) -> list[str]:
    lines: list[str] = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            page_text = page.extract_text() or ""
            for raw_line in page_text.splitlines():
                raw_line = raw_line.rstrip("\n")
                if raw_line.strip():
                    lines.append(raw_line)
    return lines


def parse_races(lines: list[str]) -> list[ParsedRace]:
    races: list[ParsedRace] = []

    current_title: str | None = None
    current_seats: int | None = None
    candidates: list[ParsedCandidate] = []
    write_in_votes: int = 0
    in_race = False

    def flush():
        nonlocal current_title, current_seats, candidates, write_in_votes, in_race
        if current_title and (candidates or write_in_votes):
            races.append(
                ParsedRace(
                    raw_title=current_title,
                    seats_to_fill=current_seats,
                    candidates=candidates,
                    write_in_votes=write_in_votes,
                )
            )
        current_title = None
        current_seats = None
        candidates = []
        write_in_votes = 0
        in_race = False

    for raw in lines:
        line = _normalize_space(raw)
        if not line:
            continue

        if _REPORT_HEADER_RE.search(line) or _SPRING_ELECTION_RE.search(line) or _REPORT_FOOTER_RE.search(line):
            continue

        if _TOTAL_LINE_RE.match(line):
            continue

        if _PRECINCTS_RE.search(line):
            # End of the race block.
            flush()
            continue

        vote_for = _VOTE_FOR_RE.match(line)
        if vote_for:
            in_race = True
            current_seats = int(vote_for.group("n"))
            continue

        if _WRITEIN_RE.match(line):
            # Often followed by a number on same line or next line.
            trailing = re.sub(_WRITEIN_RE.pattern, "", line, flags=re.IGNORECASE).strip()
            v = _parse_int_maybe(trailing)
            if v is not None:
                write_in_votes = v
            continue

        # Sometimes write-in total is on its own line right after the label.
        if in_race and candidates and write_in_votes == 0:
            maybe_votes_only = _parse_int_maybe(line)
            if maybe_votes_only is not None and maybe_votes_only > 0:
                # Heuristic: if we just saw "Write-in Totals" we'd have set it; but PDFs vary.
                pass

        cand = _split_candidate_line(line)
        if in_race and cand:
            candidates.append(cand)
            continue

        # Treat remaining non-data lines as race titles.
        # Only flush the previous race if we have started capturing candidate/write-in data.
        is_title_like = not _VOTE_FOR_RE.match(line) and not _PRECINCTS_RE.match(line) and not _WRITEIN_RE.match(line)
        if is_title_like:
            if current_title and (candidates or write_in_votes):
                flush()
            current_title = line
            in_race = False
            current_seats = None
            continue

    flush()
    return races


def _load_reference_data(conn):
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT jurisdiction_name
            FROM jurisdictions
            WHERE jurisdiction_name IS NOT NULL AND jurisdiction_name <> ''
            ORDER BY LENGTH(jurisdiction_name) DESC;
            """
        )
        jurisdictions = [r[0] for r in cur.fetchall() if r[0]]

        cur.execute("SELECT DISTINCT office_name FROM offices WHERE office_name IS NOT NULL AND office_name <> '';")
        office_names = [r[0] for r in cur.fetchall() if r[0]]

    return jurisdictions, office_names


def _best_prefix_match(text: str, options: list[str]) -> str | None:
    t = text.lower()
    for opt in options:
        o = opt.lower()
        if t.startswith(o):
            return opt
    return None


def _best_substring_match(text: str, options: list[str]) -> str | None:
    t = text.lower()
    best = None
    best_len = 0
    for opt in options:
        o = opt.lower()
        if o in t and len(o) > best_len:
            best = opt
            best_len = len(o)
    return best


def _split_race_title(raw_title: str, jurisdictions: list[str], office_names: list[str]) -> tuple[str, str]:
    title = _normalize_space(raw_title)

    m = re.match(r"^Alderperson\s+Columbus\s+District\s+(\d+)\s*$", title, flags=re.IGNORECASE)
    if m:
        district = m.group(1)
        return "City of Columbus", f"Alderperson District {district}"

    m = re.match(r"^Alderperson\s+District\s+(\d+)\s*$", title, flags=re.IGNORECASE)
    if m:
        district = m.group(1)
        return "City of Portage", f"Alderperson District {district}"

    title = re.sub(
        r"\bSchool\s+District\s+of\s+(?P<name>[A-Za-z0-9 .\-\']+)",
        lambda mm: f"{re.sub(r'\s*-\s*Area\s+.*$', '', mm.group('name'), flags=re.IGNORECASE).strip()} School District",
        title,
        flags=re.IGNORECASE,
    )

    jur = _best_prefix_match(title, jurisdictions) or _best_substring_match(title, jurisdictions)
    if jur:
        rest = title
        if title.lower().startswith(jur.lower()):
            rest = title[len(jur):].strip(" -–—,:\t")
        else:
            rest = title.replace(jur, "").strip(" -–—,:\t")
    else:
        jur = ""
        rest = title

    office = _best_substring_match(rest, office_names) or rest
    office = _normalize_space(office)

    return jur, office


def _lookup_term_years(conn, office: str) -> int | None:
    if not office:
        return None
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT term_years
            FROM offices
            WHERE office_name = %s AND term_years IS NOT NULL
            ORDER BY term_years DESC
            LIMIT 1;
            """,
            (office,),
        )
        row = cur.fetchone()
    return int(row[0]) if row else None


def _parse_person_name(candidate_name: str) -> tuple[str, str, str]:
    name = _normalize_space(candidate_name)
    name = re.sub(r"\s+\(.*?\)\s*$", "", name).strip()
    name = re.sub(r"\s+\*\s*$", "", name).strip()

    parts = [p for p in re.split(r"\s+", name) if p]
    if not parts:
        return "", "", ""
    if len(parts) == 1:
        return parts[0], "", ""
    if len(parts) == 2:
        return parts[0], "", parts[1]
    return parts[0], " ".join(parts[1:-1]), parts[-1]


def _normalize_name_key(s: str) -> str:
    s = (s or "").strip().lower()
    s = re.sub(r"[^a-z\s\-\']", "", s)
    s = _normalize_space(s)
    return s


def _normalize_full_name_key(s: str) -> str:
    s = _normalize_space(s).lower()
    s = re.sub(r"\s+", " ", s)
    s = s.strip("\t ")
    return s


def load_standard_names(csv_path: str) -> dict[str, str]:
    """Load Alt Name -> Standardized Name mappings.

    Keys are normalized for resilient lookup (case/whitespace-insensitive).
    """
    mapping: dict[str, str] = {}
    if not csv_path:
        return mapping
    if not os.path.exists(csv_path):
        return mapping

    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)

        def _get(row: dict, key: str) -> str:
            for k in row.keys():
                if (k or "").strip().lstrip("\ufeff").lower() == key.lower():
                    return row.get(k) or ""
            return ""

        for row in reader:
            alt = (_get(row, "Alt Name") or "").strip()
            std = (_get(row, "Standardized Name") or "").strip()
            if not alt or not std:
                # Fallback: attempt positional read from the first two columns.
                values = list(row.values())
                if len(values) >= 2:
                    alt = (values[0] or "").strip()
                    std = (values[1] or "").strip()
            if not alt or not std:
                continue
            mapping[_normalize_full_name_key(alt)] = std

    return mapping


def _lookup_contact_id(conn, first: str, middle: str, last: str) -> int | None:
    fn = _normalize_name_key(first)
    mn = _normalize_name_key(middle)
    ln = _normalize_name_key(last)
    if not fn or not ln:
        return None

    with conn.cursor() as cur:
        # 1) If we have a middle name/initial, first try to match it.
        if mn:
            # Exact middle-name match.
            cur.execute(
                """
                SELECT contact_id
                FROM individuals
                WHERE LOWER(TRIM(first_name)) = %s
                  AND LOWER(TRIM(last_name)) = %s
                  AND LOWER(TRIM(COALESCE(middle_name,''))) = %s
                ORDER BY contact_id ASC
                LIMIT 1;
                """,
                (fn, ln, mn),
            )
            row = cur.fetchone()
            if row:
                return int(row[0])

            # Middle initial match either direction.
            mi = mn[0]
            cur.execute(
                """
                SELECT contact_id
                FROM individuals
                WHERE LOWER(TRIM(first_name)) = %s
                  AND LOWER(TRIM(last_name)) = %s
                  AND (
                        LEFT(LOWER(TRIM(COALESCE(middle_name,''))), 1) = %s
                     OR %s = LEFT(LOWER(TRIM(COALESCE(middle_name,''))), 1)
                  )
                ORDER BY contact_id ASC
                LIMIT 1;
                """,
                (fn, ln, mi, mi),
            )
            row = cur.fetchone()
            if row:
                return int(row[0])

        # 2) Fall back to a looser match that ignores middle name.
        cur.execute(
            """
            SELECT contact_id
            FROM individuals
            WHERE LOWER(TRIM(first_name)) = %s
              AND LOWER(TRIM(last_name)) = %s
            ORDER BY contact_id ASC
            LIMIT 1;
            """,
            (fn, ln),
        )
        row = cur.fetchone()

    return int(row[0]) if row else None


def _compute_elected(candidates: list[ParsedCandidate], seats_to_fill: int | None) -> set[str]:
    if not seats_to_fill or seats_to_fill <= 0:
        return set()
    sorted_cands = sorted(candidates, key=lambda c: c.votes, reverse=True)
    if len(sorted_cands) <= seats_to_fill:
        return {c.candidate_name for c in sorted_cands}

    cutoff_votes = sorted_cands[seats_to_fill - 1].votes
    return {c.candidate_name for c in sorted_cands if c.votes >= cutoff_votes}


def _is_referendum_race(race: ParsedRace) -> bool:
    title = _normalize_space(race.raw_title).lower()
    if "referendum" in title:
        return True

    names = {_normalize_space(c.candidate_name).lower() for c in race.candidates}
    if names and names.issubset({"yes", "no"}):
        return True

    return False


def write_csv(rows: list[dict], output_path: str) -> None:
    fieldnames = [
        "Jurisdiction",
        "Office",
        "Votes Received",
        "Percent Received",
        "Total Votes",
        "Elected",
        "Election Date",
        "Term (years)",
        "Office Start Date",
        "Re-Election Date",
        "Term End Date",
        "First Name",
        "Middle Name",
        "Last Name",
        "Contact ID",
    ]

    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def main() -> int:
    parser = argparse.ArgumentParser(description="Extract 2025 April election results to CSV")
    parser.add_argument("--pdf", default="source_files/2025-April.pdf")
    parser.add_argument("--out", default=OUTPUT_CSV)
    parser.add_argument("--standard-names", default="standard_names.csv")
    args = parser.parse_args()

    _shared_load_dotenv()

    conn = get_db_connection()
    jurisdictions, office_names = _load_reference_data(conn)
    standard_names = load_standard_names(args.standard_names)

    lines = extract_text_lines(args.pdf)
    races = parse_races(lines)

    rows: list[dict] = []

    election_year = ELECTION_DATE.year
    office_start = fourth_monday_in_april(election_year)

    for race in races:
        if _is_referendum_race(race):
            continue

        jurisdiction, office = _split_race_title(race.raw_title, jurisdictions, office_names)
        term_years = _lookup_term_years(conn, office)

        total_votes = race.write_in_votes + sum(c.votes for c in race.candidates)
        elected_names = _compute_elected(race.candidates, race.seats_to_fill)

        if term_years is not None:
            reelection = first_tuesday_in_april(election_year + term_years)
            term_end = fourth_monday_in_april(election_year + term_years)
        else:
            reelection = None
            term_end = None

        for c in race.candidates:
            percent = c.percent
            if percent is None and total_votes > 0:
                percent = round((c.votes / total_votes) * 100.0, 2)

            first, middle, last = _parse_person_name(c.candidate_name)
            contact_id = _lookup_contact_id(conn, first, middle, last)

            if contact_id is None:
                std = standard_names.get(_normalize_full_name_key(c.candidate_name))
                if std:
                    s_first, s_middle, s_last = _parse_person_name(std)
                    contact_id = _lookup_contact_id(conn, s_first, s_middle, s_last)

            rows.append(
                {
                    "Jurisdiction": jurisdiction,
                    "Office": office,
                    "Votes Received": c.votes,
                    "Percent Received": percent,
                    "Total Votes": total_votes,
                    "Elected": 1 if c.candidate_name in elected_names else 0,
                    "Election Date": ELECTION_DATE.strftime("%-m/%-d/%y"),
                    "Term (years)": term_years if term_years is not None else "",
                    "Office Start Date": office_start.strftime("%-m/%-d/%y"),
                    "Re-Election Date": reelection.strftime("%-m/%-d/%y") if reelection else "",
                    "Term End Date": term_end.strftime("%-m/%-d/%y") if term_end else "",
                    "First Name": first,
                    "Middle Name": middle,
                    "Last Name": last,
                    "Contact ID": contact_id if contact_id is not None else "",
                }
            )

    conn.close()

    write_csv(rows, args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
