# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Quarterly estimated tax calculator for US federal and Virginia state taxes. Single-file Python application that calculates tax liability, withholding gaps, safe harbor amounts, and quarterly payment schedules based on YAML configuration input.

## Commands

```bash
# Install dependencies
uv sync

# Run with default config (tax_config.yaml)
uv run python estimated_tax_calculator.py

# Run with specific config
uv run python estimated_tax_calculator.py personal.yaml

# Run via installed entry point
uv run estimated-tax
```

```bash
# Sanitize PDFs (redact PII)
uv run pdf-sanitizer ./pdfs/                              # batch process folder
uv run pdf-sanitizer doc.pdf --dry-run --verbose          # preview mode (yellow highlights)
uv run pdf-sanitizer ./pdfs/ --config my_pii.yaml         # custom config
```

There are no tests, linting, or CI configured.

## Architecture

Everything lives in `estimated_tax_calculator.py` (~940 lines):

- **Constants (top)**: 2026 federal tax brackets, LTCG brackets, standard deductions, NIIT thresholds, VA state brackets, quarterly due dates. These are hardcoded per tax year.
- **TaxConfig dataclass**: Holds all user inputs; uses `Decimal` throughout for precision.
- **Core calculation functions**: `calculate_ordinary_income_tax()`, `calculate_ltcg_tax()`, `calculate_niit()`, `calculate_total_tax()`, `calculate_virginia_tax()`, `calculate_withholding()`, `calculate_safe_harbor()`, `calculate_quarterly_payments()`.
- **I/O**: `load_config()` parses YAML, `print_results()` formats output, `main()` is the CLI entry point.

Configuration files (`tax_config.yaml`, `personal.yaml`) define income sources, withholding, filing status, and prior year tax info.

`pdf_sanitizer.py` (~300 lines) is a standalone CLI tool that redacts PII from financial PDFs using PyMuPDF. PII detection is hybrid: user-supplied literal strings (names/addresses from `sanitizer_config.yaml`) plus regex patterns (SSN, EIN, phone, email, DOB) plus context-aware account number matching. Uses `page.apply_redactions()` for permanent black-box redaction.

## Key Design Decisions

- All monetary values use `Decimal` (never float) — the `d()` helper converts to Decimal.
- RSU supplemental withholding defaults to 22% flat rate; the output highlights underwithholding for high earners.
- Safe harbor shows both "required" (minimum to avoid penalties per IRS rules) and "recommended" (full liability) amounts.
- Virginia state tax is optional, controlled by `calculate_virginia_tax` flag in config.
- Dependencies: `pyyaml` (YAML config parsing), `pymupdf` (PDF redaction).
