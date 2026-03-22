"""PDF PII Sanitizer — Redact personally identifiable information from financial PDFs.

Permanently removes PII (names, addresses, SSNs, account numbers, etc.) from PDF
documents using black-box redaction. Designed for sanitizing financial documents
(W-2s, 1099s, brokerage statements, bank statements) before cloud processing.
"""

import argparse
import logging
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

import fitz  # pymupdf
import yaml

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Regex patterns for structured PII
# ---------------------------------------------------------------------------

SSN_PATTERNS = [
    re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),          # 123-45-6789
    re.compile(r"\b\d{3}\s\d{2}\s\d{4}\b"),         # 123 45 6789
    re.compile(r"\bXXX-XX-\d{4}\b"),                 # XXX-XX-6789 (masked)
    re.compile(r"\b\*{3}-\*{2}-\d{4}\b"),            # ***-**-6789 (masked)
]

EIN_PATTERNS = [
    re.compile(r"\b\d{2}-\d{7}\b"),                  # 12-3456789
]

PHONE_PATTERNS = [
    re.compile(r"\(\d{3}\)\s?\d{3}-\d{4}"),          # (123) 456-7890
    re.compile(r"\b\d{3}-\d{3}-\d{4}\b"),            # 123-456-7890
    re.compile(r"\b\d{3}\.\d{3}\.\d{4}\b"),          # 123.456.7890
]

EMAIL_PATTERNS = [
    re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"),
]

DOB_PATTERNS = [
    re.compile(r"\b\d{2}/\d{2}/\d{4}\b"),            # 01/15/1990
    re.compile(r"\b\d{2}-\d{2}-\d{4}\b"),            # 01-15-1990
]

# Labels that indicate a nearby number is an account number
ACCOUNT_LABELS = re.compile(
    r"(account\s*(number|no|#|num)?|acct\s*(number|no|#|num)?|routing\s*(number|no|#)?|member\s*(number|no|#)?)",
    re.IGNORECASE,
)

ACCOUNT_NUMBER_PATTERN = re.compile(r"\b\d{6,17}\b")

ALL_REGEX_CATEGORIES = {
    "ssn": SSN_PATTERNS,
    "ein": EIN_PATTERNS,
    "phone": PHONE_PATTERNS,
    "email": EMAIL_PATTERNS,
    "dob": DOB_PATTERNS,
}


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

@dataclass
class SanitizerConfig:
    """Configuration for PII detection and redaction."""

    names: list[str] = field(default_factory=list)
    addresses: list[str] = field(default_factory=list)
    custom_strings: list[str] = field(default_factory=list)
    redact_ssn: bool = True
    redact_ein: bool = True
    redact_phone: bool = True
    redact_email: bool = True
    redact_dob: bool = True
    redact_account_numbers: bool = True


def load_config(config_path: Path) -> SanitizerConfig:
    """Load sanitizer configuration from a YAML file."""
    with open(config_path) as f:
        data = yaml.safe_load(f) or {}

    return SanitizerConfig(
        names=data.get("names", []),
        addresses=data.get("addresses", []),
        custom_strings=data.get("custom", []),
        redact_ssn=data.get("redact_ssn", True),
        redact_ein=data.get("redact_ein", True),
        redact_phone=data.get("redact_phone", True),
        redact_email=data.get("redact_email", True),
        redact_dob=data.get("redact_dob", True),
        redact_account_numbers=data.get("redact_account_numbers", True),
    )


# ---------------------------------------------------------------------------
# PII detection
# ---------------------------------------------------------------------------

def find_literal_matches(page: fitz.Page, strings: list[str]) -> list[fitz.Rect]:
    """Find bounding rectangles for literal string matches on a page."""
    rects = []
    for text in strings:
        if not text:
            continue
        found = page.search_for(text)
        if found:
            rects.extend(found)
            logger.debug("  Literal match '%s': %d hit(s)", text, len(found))
    return rects


def find_regex_matches(page: fitz.Page, config: SanitizerConfig) -> list[fitz.Rect]:
    """Find bounding rectangles for regex-matched PII on a page."""
    page_text = page.get_text("text")
    if not page_text.strip():
        return []

    rects = []
    category_flags = {
        "ssn": config.redact_ssn,
        "ein": config.redact_ein,
        "phone": config.redact_phone,
        "email": config.redact_email,
        "dob": config.redact_dob,
    }

    for category, patterns in ALL_REGEX_CATEGORIES.items():
        if not category_flags.get(category, True):
            continue
        for pattern in patterns:
            for match in pattern.finditer(page_text):
                matched_text = match.group()
                found = page.search_for(matched_text)
                if found:
                    rects.extend(found)
                    logger.debug("  Regex [%s] match '%s': %d hit(s)",
                                 category, matched_text, len(found))
    return rects


def find_contextual_matches(page: fitz.Page, config: SanitizerConfig) -> list[fitz.Rect]:
    """Find account numbers that appear near account-related labels.

    Only matches digit sequences (6-17 digits) that are within proximity of
    labels like 'Account Number', 'Acct #', 'Routing', etc. This avoids
    false positives on dollar amounts, dates, and other numeric fields.
    """
    if not config.redact_account_numbers:
        return []

    rects = []
    blocks = page.get_text("dict")["blocks"]

    for block in blocks:
        if block.get("type") != 0:  # text block
            continue
        for line in block.get("lines", []):
            line_text = ""
            spans = line.get("spans", [])
            for span in spans:
                line_text += span.get("text", "")

            if not ACCOUNT_LABELS.search(line_text):
                continue

            # Found a label — redact digit sequences on this line
            for match in ACCOUNT_NUMBER_PATTERN.finditer(line_text):
                matched_text = match.group()
                # Skip if it looks like a dollar amount (preceded by $ or has decimal)
                prefix_end = match.start()
                if prefix_end > 0 and line_text[prefix_end - 1] == "$":
                    continue
                found = page.search_for(matched_text)
                if found:
                    # Only keep rects that overlap with this line's vertical position
                    line_rect = fitz.Rect(line["bbox"])
                    for r in found:
                        if abs(r.y0 - line_rect.y0) < line_rect.height * 1.5:
                            rects.append(r)
                            logger.debug("  Account number '%s' near label", matched_text)

    return rects


# ---------------------------------------------------------------------------
# Redaction
# ---------------------------------------------------------------------------

def redact_page(page: fitz.Page, config: SanitizerConfig) -> int:
    """Detect and redact all PII on a single page. Returns redaction count."""
    all_rects = []

    # User-supplied literal strings
    all_strings = config.names + config.addresses + config.custom_strings
    all_rects.extend(find_literal_matches(page, all_strings))

    # Regex-based structured PII
    all_rects.extend(find_regex_matches(page, config))

    # Context-aware account numbers
    all_rects.extend(find_contextual_matches(page, config))

    if not all_rects:
        return 0

    # Deduplicate overlapping rects
    unique_rects = _deduplicate_rects(all_rects)

    for rect in unique_rects:
        page.add_redact_annot(rect, fill=(0, 0, 0))  # black fill

    page.apply_redactions()
    return len(unique_rects)


def _deduplicate_rects(rects: list[fitz.Rect]) -> list[fitz.Rect]:
    """Remove duplicate or substantially overlapping rectangles."""
    if not rects:
        return []

    unique = []
    for rect in rects:
        is_dup = False
        for existing in unique:
            # Consider rects duplicates if they overlap significantly
            intersection = rect & existing  # intersection
            if not intersection.is_empty:
                smaller_area = min(rect.get_area(), existing.get_area())
                if smaller_area > 0 and intersection.get_area() / smaller_area > 0.8:
                    is_dup = True
                    break
        if not is_dup:
            unique.append(rect)
    return unique


def highlight_page(page: fitz.Page, config: SanitizerConfig) -> int:
    """Highlight (not redact) PII for dry-run preview. Returns highlight count."""
    all_rects = []

    all_strings = config.names + config.addresses + config.custom_strings
    all_rects.extend(find_literal_matches(page, all_strings))
    all_rects.extend(find_regex_matches(page, config))
    all_rects.extend(find_contextual_matches(page, config))

    if not all_rects:
        return 0

    unique_rects = _deduplicate_rects(all_rects)

    for rect in unique_rects:
        highlight = page.add_highlight_annot(rect)
        highlight.set_colors(stroke=(1, 1, 0))  # yellow
        highlight.update()

    return len(unique_rects)


# ---------------------------------------------------------------------------
# File processing
# ---------------------------------------------------------------------------

def sanitize_pdf(
    input_path: Path,
    output_path: Path,
    config: SanitizerConfig,
    dry_run: bool = False,
) -> dict:
    """Sanitize a single PDF file. Returns stats dict."""
    doc = fitz.open(input_path)
    total_redactions = 0
    warnings = []

    for page_num in range(len(doc)):
        page = doc[page_num]
        page_text = page.get_text("text").strip()

        if not page_text:
            warnings.append(f"Page {page_num + 1}: image-only (no extractable text), skipped")
            continue

        if dry_run:
            count = highlight_page(page, config)
        else:
            count = redact_page(page, config)

        total_redactions += count
        logger.info("  Page %d: %d redaction(s)", page_num + 1, count)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(output_path), garbage=4, deflate=True)
    doc.close()

    return {
        "pages": doc.page_count,
        "redactions": total_redactions,
        "warnings": warnings,
        "dry_run": dry_run,
    }


def process_folder(
    input_dir: Path,
    output_dir: Path,
    config: SanitizerConfig,
    dry_run: bool = False,
) -> None:
    """Process all PDFs in a folder."""
    pdf_files = sorted(input_dir.glob("*.pdf"))
    if not pdf_files:
        print(f"No PDF files found in {input_dir}")
        return

    print(f"{'[DRY RUN] ' if dry_run else ''}Processing {len(pdf_files)} PDF(s)...\n")

    total_files = 0
    total_redactions = 0

    for pdf_file in pdf_files:
        output_path = output_dir / pdf_file.name
        print(f"  {pdf_file.name}")

        stats = sanitize_pdf(pdf_file, output_path, config, dry_run=dry_run)
        total_files += 1
        total_redactions += stats["redactions"]

        action = "highlighted" if dry_run else "redacted"
        print(f"    {stats['redactions']} region(s) {action} across {stats['pages']} page(s)")

        for warning in stats["warnings"]:
            print(f"    WARNING: {warning}")

    print(f"\nDone. {total_files} file(s), {total_redactions} total redaction(s).")
    print(f"Output: {output_dir}/")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Redact PII from financial PDF documents.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  pdf-sanitizer ./tax_docs/\n"
            "  pdf-sanitizer w2.pdf --dry-run --verbose\n"
            "  pdf-sanitizer ./pdfs/ --output-dir ./clean/ --config my_pii.yaml\n"
        ),
    )
    parser.add_argument(
        "input",
        type=Path,
        help="PDF file or folder of PDFs to sanitize",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Output directory (default: <input>_sanitized/ or <input_dir>_sanitized/)",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("sanitizer_config.yaml"),
        help="YAML config with names/addresses to redact (default: sanitizer_config.yaml)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Highlight PII in yellow instead of redacting (preview mode)",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print detailed per-page redaction info",
    )

    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.WARNING,
        format="%(message)s",
    )

    if not args.input.exists():
        print(f"Error: '{args.input}' does not exist.", file=sys.stderr)
        sys.exit(1)

    # Load config
    if args.config.exists():
        config = load_config(args.config)
        literal_count = len(config.names) + len(config.addresses) + len(config.custom_strings)
        print(f"Config: {args.config} ({literal_count} literal string(s) to redact)")
    else:
        print(f"No config file found at '{args.config}' — using regex-only detection.")
        print("Create a config to also redact names and addresses (see sanitizer_config.example.yaml).\n")
        config = SanitizerConfig()

    # Determine input/output paths
    if args.input.is_file():
        output_dir = args.output_dir or args.input.parent / f"{args.input.stem}_sanitized"
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / args.input.name

        action = "Highlighting" if args.dry_run else "Redacting"
        print(f"{action}: {args.input.name}")

        stats = sanitize_pdf(args.input, output_path, config, dry_run=args.dry_run)

        action_past = "highlighted" if args.dry_run else "redacted"
        print(f"  {stats['redactions']} region(s) {action_past} across {stats['pages']} page(s)")
        for warning in stats["warnings"]:
            print(f"  WARNING: {warning}")
        print(f"Output: {output_path}")

    elif args.input.is_dir():
        output_dir = args.output_dir or args.input.parent / f"{args.input.name}_sanitized"
        process_folder(args.input, output_dir, config, dry_run=args.dry_run)

    else:
        print(f"Error: '{args.input}' is not a file or directory.", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
