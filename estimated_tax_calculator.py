#!/usr/bin/env python3
"""
Quarterly Estimated Tax Calculator (IRS Form 1040-ES)

Calculates quarterly estimated tax payments based on:
- W-2 wages and withholding
- RSU income (with supplemental 22% flat withholding)
- Dividend income (qualified and ordinary)
- Interest income
- Other income sources

Uses IRS 1040-ES safe harbor rules and current tax brackets.

Usage:
    python estimated_tax_calculator.py [config.yaml]

If no config file specified, looks for 'tax_config.yaml' in current directory.
"""

import sys
import yaml
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

# =============================================================================
# 2026 Tax Year Constants (for 2026 estimated payments)
# Update these annually based on IRS guidance (Form 1040-ES)
# =============================================================================

# 2026 Federal Income Tax Brackets
TAX_BRACKETS = {
    "single": [
        (12400, Decimal("0.10")),
        (50400, Decimal("0.12")),
        (105700, Decimal("0.22")),
        (201775, Decimal("0.24")),
        (256225, Decimal("0.32")),
        (640600, Decimal("0.35")),
        (float("inf"), Decimal("0.37")),
    ],
    "married_filing_jointly": [
        (24800, Decimal("0.10")),
        (100800, Decimal("0.12")),
        (211400, Decimal("0.22")),
        (403550, Decimal("0.24")),
        (512450, Decimal("0.32")),
        (768700, Decimal("0.35")),
        (float("inf"), Decimal("0.37")),
    ],
    "married_filing_separately": [
        (12400, Decimal("0.10")),
        (50400, Decimal("0.12")),
        (105700, Decimal("0.22")),
        (201775, Decimal("0.24")),
        (256225, Decimal("0.32")),
        (384350, Decimal("0.35")),
        (float("inf"), Decimal("0.37")),
    ],
    "head_of_household": [
        (17700, Decimal("0.10")),
        (67450, Decimal("0.12")),
        (105700, Decimal("0.22")),
        (201750, Decimal("0.24")),
        (256200, Decimal("0.32")),
        (640600, Decimal("0.35")),
        (float("inf"), Decimal("0.37")),
    ],
}

# 2026 Qualified Dividends / Long-Term Capital Gains Brackets
LTCG_BRACKETS = {
    "single": [
        (50400, Decimal("0.00")),
        (553850, Decimal("0.15")),
        (float("inf"), Decimal("0.20")),
    ],
    "married_filing_jointly": [
        (100800, Decimal("0.00")),
        (623300, Decimal("0.15")),
        (float("inf"), Decimal("0.20")),
    ],
    "married_filing_separately": [
        (50400, Decimal("0.00")),
        (311650, Decimal("0.15")),
        (float("inf"), Decimal("0.20")),
    ],
    "head_of_household": [
        (67450, Decimal("0.00")),
        (588750, Decimal("0.15")),
        (float("inf"), Decimal("0.20")),
    ],
}

# 2026 Standard Deductions
STANDARD_DEDUCTION = {
    "single": Decimal("16100"),
    "married_filing_jointly": Decimal("32200"),
    "married_filing_separately": Decimal("16100"),
    "head_of_household": Decimal("24150"),
}

# Net Investment Income Tax (NIIT) threshold - 3.8% on investment income
# for AGI above these thresholds
NIIT_THRESHOLDS = {
    "single": Decimal("200000"),
    "married_filing_jointly": Decimal("250000"),
    "married_filing_separately": Decimal("125000"),
    "head_of_household": Decimal("200000"),
}
NIIT_RATE = Decimal("0.038")

# Safe harbor: 110% of prior year tax if AGI > this threshold
SAFE_HARBOR_110_THRESHOLD = {
    "single": Decimal("150000"),
    "married_filing_jointly": Decimal("150000"),
    "married_filing_separately": Decimal("75000"),
    "head_of_household": Decimal("150000"),
}

# RSU supplemental wage withholding rate
RSU_SUPPLEMENTAL_WITHHOLDING_RATE = Decimal("0.22")

# 2026 Quarterly Due Dates (for 2026 tax year estimated payments)
QUARTERLY_DUE_DATES = [
    "April 15, 2026",
    "June 15, 2026",
    "September 15, 2026",
    "January 15, 2027",
]

# =============================================================================
# Virginia State Tax Constants
# =============================================================================

VA_TAX_BRACKETS = [
    (Decimal("3000"), Decimal("0.02")),
    (Decimal("5000"), Decimal("0.03")),
    (Decimal("17000"), Decimal("0.05")),
    (Decimal("Infinity"), Decimal("0.0575")),
]

VA_STANDARD_DEDUCTION = {
    "single": Decimal("8750"),
    "married_filing_jointly": Decimal("17500"),
    "married_filing_separately": Decimal("8750"),
    "head_of_household": Decimal("8750"),
}

VA_PERSONAL_EXEMPTION = Decimal("930")

VA_PERSONAL_EXEMPTION_COUNT = {
    "single": 1,
    "married_filing_jointly": 2,
    "married_filing_separately": 2,
    "head_of_household": 1,
}

VA_QUARTERLY_DUE_DATES = [
    "May 1, 2026",
    "June 15, 2026",
    "September 15, 2026",
    "January 15, 2027",
]


@dataclass
class TaxConfig:
    """Configuration for tax calculation."""
    filing_status: str

    # W-2 Income
    w2_wages: Decimal = Decimal("0")
    w2_federal_withholding: Decimal = Decimal("0")

    # RSU Income (vested value, typically withheld at 22% flat rate)
    rsu_income: Decimal = Decimal("0")
    rsu_withholding: Decimal = Decimal("0")  # If 0, calculated at 22%

    # Investment Income
    qualified_dividends: Decimal = Decimal("0")
    ordinary_dividends: Decimal = Decimal("0")  # Non-qualified portion
    interest_income: Decimal = Decimal("0")
    short_term_capital_gains: Decimal = Decimal("0")
    long_term_capital_gains: Decimal = Decimal("0")

    # Other Income
    other_income: Decimal = Decimal("0")

    # Deductions
    use_standard_deduction: bool = True
    itemized_deductions: Decimal = Decimal("0")
    above_line_deductions: Decimal = Decimal("0")  # 401k, HSA, etc.

    # Credits
    tax_credits: Decimal = Decimal("0")

    # Prior Year (for safe harbor calculation)
    prior_year_tax: Decimal = Decimal("0")
    prior_year_agi: Decimal = Decimal("0")

    # Already paid estimated taxes this year
    estimated_payments_made: Decimal = Decimal("0")

    # Virginia state withholding (0 = auto-estimate)
    va_withholding: Decimal = Decimal("0")


def d(value) -> Decimal:
    """Convert value to Decimal."""
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def round_currency(amount: Decimal) -> Decimal:
    """Round to nearest dollar."""
    return amount.quantize(Decimal("1"), rounding=ROUND_HALF_UP)


def calculate_ordinary_income_tax(taxable_income: Decimal, filing_status: str) -> Decimal:
    """Calculate tax on ordinary income using progressive brackets."""
    if taxable_income <= 0:
        return Decimal("0")

    brackets = TAX_BRACKETS[filing_status]
    tax = Decimal("0")
    prev_bracket = Decimal("0")

    for bracket_max, rate in brackets:
        bracket_max = d(bracket_max)
        if taxable_income <= prev_bracket:
            break
        taxable_in_bracket = min(taxable_income, bracket_max) - prev_bracket
        if taxable_in_bracket > 0:
            tax += taxable_in_bracket * rate
        prev_bracket = bracket_max

    return tax


def calculate_ltcg_tax(taxable_income: Decimal, ltcg_amount: Decimal,
                       filing_status: str) -> Decimal:
    """
    Calculate tax on qualified dividends and long-term capital gains.

    These are taxed at preferential rates (0%, 15%, or 20%) based on
    total taxable income.
    """
    if ltcg_amount <= 0:
        return Decimal("0")

    brackets = LTCG_BRACKETS[filing_status]

    # LTCG is "stacked" on top of ordinary income for bracket determination
    ordinary_income = taxable_income - ltcg_amount
    if ordinary_income < 0:
        ordinary_income = Decimal("0")

    tax = Decimal("0")
    remaining_ltcg = ltcg_amount

    for bracket_max, rate in brackets:
        bracket_max = d(bracket_max)

        # How much room is left in this bracket after ordinary income?
        bracket_start = Decimal("0") if brackets.index((bracket_max, rate)) == 0 else d(brackets[brackets.index((bracket_max, rate)) - 1][0])

        if ordinary_income >= bracket_max:
            # Ordinary income fills this entire bracket
            continue

        # Calculate LTCG taxable in this bracket
        bracket_room = bracket_max - max(ordinary_income, bracket_start)
        ltcg_in_bracket = min(remaining_ltcg, bracket_room)

        if ltcg_in_bracket > 0:
            tax += ltcg_in_bracket * rate
            remaining_ltcg -= ltcg_in_bracket

        if remaining_ltcg <= 0:
            break

    return tax


def calculate_niit(agi: Decimal, investment_income: Decimal,
                   filing_status: str) -> Decimal:
    """
    Calculate Net Investment Income Tax (3.8%).

    Applies to the lesser of:
    - Net investment income, OR
    - AGI exceeding the threshold
    """
    threshold = NIIT_THRESHOLDS[filing_status]

    if agi <= threshold:
        return Decimal("0")

    agi_excess = agi - threshold
    taxable_amount = min(investment_income, agi_excess)

    return taxable_amount * NIIT_RATE


def calculate_total_tax(config: TaxConfig) -> dict:
    """
    Calculate total federal income tax liability.

    Returns a dict with breakdown of calculations.
    """
    results = {}

    # Calculate Gross Income
    gross_income = (
        config.w2_wages +
        config.rsu_income +
        config.qualified_dividends +
        config.ordinary_dividends +
        config.interest_income +
        config.short_term_capital_gains +
        config.long_term_capital_gains +
        config.other_income
    )
    results["gross_income"] = gross_income

    # Calculate AGI
    agi = gross_income - config.above_line_deductions
    results["agi"] = agi

    # Calculate Deduction
    if config.use_standard_deduction:
        deduction = STANDARD_DEDUCTION[config.filing_status]
    else:
        deduction = config.itemized_deductions
    results["deduction"] = deduction

    # Calculate Taxable Income
    taxable_income = max(agi - deduction, Decimal("0"))
    results["taxable_income"] = taxable_income

    # Separate preferentially-taxed income
    preferential_income = config.qualified_dividends + config.long_term_capital_gains
    ordinary_taxable = taxable_income - preferential_income
    if ordinary_taxable < 0:
        # If deduction exceeds ordinary income, reduce preferential income
        preferential_income = taxable_income
        ordinary_taxable = Decimal("0")

    results["ordinary_taxable_income"] = ordinary_taxable
    results["preferential_income"] = preferential_income

    # Calculate Tax on Ordinary Income
    ordinary_tax = calculate_ordinary_income_tax(ordinary_taxable, config.filing_status)
    results["ordinary_income_tax"] = ordinary_tax

    # Calculate Tax on Qualified Dividends / LTCG
    ltcg_tax = calculate_ltcg_tax(taxable_income, preferential_income, config.filing_status)
    results["ltcg_tax"] = ltcg_tax

    # Calculate NIIT
    investment_income = (
        config.qualified_dividends +
        config.ordinary_dividends +
        config.interest_income +
        config.short_term_capital_gains +
        config.long_term_capital_gains
    )
    niit = calculate_niit(agi, investment_income, config.filing_status)
    results["niit"] = niit
    results["investment_income"] = investment_income

    # Total Tax Before Credits
    total_tax_before_credits = ordinary_tax + ltcg_tax + niit
    results["total_tax_before_credits"] = total_tax_before_credits

    # Apply Credits
    total_tax = max(total_tax_before_credits - config.tax_credits, Decimal("0"))
    results["total_tax"] = total_tax

    return results


def estimate_w2_withholding(wages: Decimal, filing_status: str) -> Decimal:
    """
    Estimate federal income tax withholding on W-2 wages.

    Approximates employer withholding by computing tax on wages minus
    the standard deduction using the progressive brackets. This assumes
    single/default withholding with no additional adjustments.
    """
    deduction = STANDARD_DEDUCTION[filing_status]
    taxable = max(wages - deduction, Decimal("0"))
    return calculate_ordinary_income_tax(taxable, filing_status)


def calculate_va_income_tax(taxable_income: Decimal) -> Decimal:
    """Calculate Virginia income tax using progressive brackets."""
    if taxable_income <= 0:
        return Decimal("0")

    tax = Decimal("0")
    prev_bracket = Decimal("0")

    for bracket_max, rate in VA_TAX_BRACKETS:
        if taxable_income <= prev_bracket:
            break
        taxable_in_bracket = min(taxable_income, bracket_max) - prev_bracket
        if taxable_in_bracket > 0:
            tax += taxable_in_bracket * rate
        prev_bracket = bracket_max

    return tax


def calculate_virginia_tax(config: TaxConfig, federal_agi: Decimal) -> dict:
    """Calculate Virginia state income tax."""
    results = {}

    va_agi = federal_agi
    results["va_agi"] = va_agi

    va_deduction = VA_STANDARD_DEDUCTION[config.filing_status]
    results["va_deduction"] = va_deduction

    exemption_count = VA_PERSONAL_EXEMPTION_COUNT[config.filing_status]
    va_exemptions = VA_PERSONAL_EXEMPTION * exemption_count
    results["va_exemptions"] = va_exemptions
    results["va_exemption_count"] = exemption_count

    va_taxable_income = max(va_agi - va_deduction - va_exemptions, Decimal("0"))
    results["va_taxable_income"] = va_taxable_income

    va_tax = calculate_va_income_tax(va_taxable_income)
    results["va_tax"] = va_tax

    return results


def estimate_va_withholding(wages: Decimal, filing_status: str) -> Decimal:
    """Estimate Virginia state tax withholding on W-2 wages."""
    deduction = VA_STANDARD_DEDUCTION[filing_status]
    exemption_count = VA_PERSONAL_EXEMPTION_COUNT[filing_status]
    exemptions = VA_PERSONAL_EXEMPTION * exemption_count
    taxable = max(wages - deduction - exemptions, Decimal("0"))
    return calculate_va_income_tax(taxable)


def calculate_withholding(config: TaxConfig) -> dict:
    """Calculate total expected withholding for the year."""
    results = {}

    # W-2 Withholding (use provided or estimate from brackets)
    if config.w2_federal_withholding > 0:
        results["w2_withholding"] = config.w2_federal_withholding
        results["w2_withholding_estimated"] = False
    else:
        results["w2_withholding"] = estimate_w2_withholding(
            config.w2_wages, config.filing_status
        )
        results["w2_withholding_estimated"] = True

    # RSU Withholding (use provided or calculate at 22%)
    if config.rsu_withholding > 0:
        rsu_withheld = config.rsu_withholding
    else:
        rsu_withheld = config.rsu_income * RSU_SUPPLEMENTAL_WITHHOLDING_RATE
    results["rsu_withholding"] = rsu_withheld

    # Already paid estimated taxes
    results["estimated_payments_made"] = config.estimated_payments_made

    # Total
    results["total_withholding"] = (
        results["w2_withholding"] +
        results["rsu_withholding"] +
        results["estimated_payments_made"]
    )

    return results


def calculate_safe_harbor(config: TaxConfig, current_year_tax: Decimal) -> dict:
    """
    Calculate safe harbor amount to avoid underpayment penalties.

    Safe harbor rules:
    - Pay at least 90% of current year tax, OR
    - Pay 100% of prior year tax (110% if AGI > $150K/$75K MFS)
    """
    results = {}

    # 90% of current year tax
    current_year_90 = current_year_tax * Decimal("0.90")
    results["current_year_90_percent"] = current_year_90

    # Prior year safe harbor
    if config.prior_year_tax > 0:
        threshold = SAFE_HARBOR_110_THRESHOLD[config.filing_status]
        if config.prior_year_agi > threshold:
            prior_year_safe_harbor = config.prior_year_tax * Decimal("1.10")
            results["prior_year_multiplier"] = "110%"
        else:
            prior_year_safe_harbor = config.prior_year_tax
            results["prior_year_multiplier"] = "100%"
        results["prior_year_safe_harbor"] = prior_year_safe_harbor
    else:
        results["prior_year_safe_harbor"] = None
        results["prior_year_multiplier"] = None

    # Minimum required is the lesser of the two
    if results["prior_year_safe_harbor"] is not None:
        results["minimum_required"] = min(current_year_90, results["prior_year_safe_harbor"])
    else:
        results["minimum_required"] = current_year_90

    return results


def calculate_quarterly_payments(config: TaxConfig) -> dict:
    """
    Calculate quarterly estimated tax payments.

    Returns comprehensive breakdown of all calculations.
    """
    results = {}

    # Calculate total tax
    tax_results = calculate_total_tax(config)
    results["tax"] = tax_results

    # Calculate withholding
    withholding_results = calculate_withholding(config)
    results["withholding"] = withholding_results

    # Calculate safe harbor
    safe_harbor = calculate_safe_harbor(config, tax_results["total_tax"])
    results["safe_harbor"] = safe_harbor

    # Calculate amount owed
    tax_owed = tax_results["total_tax"] - withholding_results["total_withholding"]
    results["tax_owed"] = tax_owed

    # Calculate required estimated payments
    # Must pay enough to meet safe harbor requirement
    required_total = max(
        safe_harbor["minimum_required"] - withholding_results["total_withholding"],
        Decimal("0")
    )
    results["required_estimated_total"] = required_total

    # But if you owe more than safe harbor, you might want to pay the full amount
    recommended_total = max(tax_owed, Decimal("0"))
    results["recommended_estimated_total"] = recommended_total

    # Quarterly amounts (divided equally)
    if required_total > 0:
        quarterly_required = round_currency(required_total / 4)
    else:
        quarterly_required = Decimal("0")
    results["quarterly_required"] = quarterly_required

    if recommended_total > 0:
        quarterly_recommended = round_currency(recommended_total / 4)
    else:
        quarterly_recommended = Decimal("0")
    results["quarterly_recommended"] = quarterly_recommended

    # Due dates
    results["due_dates"] = QUARTERLY_DUE_DATES

    # Virginia state tax
    va_results = calculate_virginia_tax(config, tax_results["agi"])
    results["va"] = va_results

    # VA withholding
    if config.va_withholding > 0:
        va_withholding = config.va_withholding
        va_withholding_estimated = False
    else:
        va_withholding = estimate_va_withholding(config.w2_wages, config.filing_status)
        va_withholding_estimated = True
    results["va_withholding"] = va_withholding
    results["va_withholding_estimated"] = va_withholding_estimated

    # VA estimated payments needed
    va_owed = va_results["va_tax"] - va_withholding
    results["va_owed"] = va_owed
    va_estimated_total = max(va_owed, Decimal("0"))
    results["va_estimated_total"] = va_estimated_total

    if va_estimated_total > 0:
        va_quarterly = round_currency(va_estimated_total / 4)
    else:
        va_quarterly = Decimal("0")
    results["va_quarterly"] = va_quarterly
    results["va_due_dates"] = VA_QUARTERLY_DUE_DATES

    return results


def load_config(config_path: str) -> TaxConfig:
    """Load configuration from YAML file."""
    with open(config_path, "r") as f:
        data = yaml.safe_load(f)

    # Normalize filing status
    filing_status = data.get("filing_status", "single").lower().replace(" ", "_")
    if filing_status not in TAX_BRACKETS:
        raise ValueError(f"Invalid filing status: {filing_status}. "
                        f"Must be one of: {list(TAX_BRACKETS.keys())}")

    return TaxConfig(
        filing_status=filing_status,
        w2_wages=d(data.get("w2_wages", 0)),
        w2_federal_withholding=d(data.get("w2_federal_withholding", 0)),
        rsu_income=d(data.get("rsu_income", 0)),
        rsu_withholding=d(data.get("rsu_withholding", 0)),
        qualified_dividends=d(data.get("qualified_dividends", 0)),
        ordinary_dividends=d(data.get("ordinary_dividends", 0)),
        interest_income=d(data.get("interest_income", 0)),
        short_term_capital_gains=d(data.get("short_term_capital_gains", 0)),
        long_term_capital_gains=d(data.get("long_term_capital_gains", 0)),
        other_income=d(data.get("other_income", 0)),
        use_standard_deduction=data.get("use_standard_deduction", True),
        itemized_deductions=d(data.get("itemized_deductions", 0)),
        above_line_deductions=d(data.get("above_line_deductions", 0)),
        tax_credits=d(data.get("tax_credits", 0)),
        prior_year_tax=d(data.get("prior_year_tax", 0)),
        prior_year_agi=d(data.get("prior_year_agi", 0)),
        estimated_payments_made=d(data.get("estimated_payments_made", 0)),
        va_withholding=d(data.get("va_withholding", 0)),
    )


def format_currency(amount: Decimal) -> str:
    """Format amount as currency string."""
    rounded = round_currency(amount)
    if rounded < 0:
        return f"-${abs(rounded):,.0f}"
    return f"${rounded:,.0f}"


def get_marginal_rate(taxable_income: Decimal, filing_status: str) -> Decimal:
    """Get the marginal tax rate for given taxable income."""
    brackets = TAX_BRACKETS[filing_status]
    for bracket_max, rate in brackets:
        if taxable_income <= bracket_max:
            return rate
    return brackets[-1][1]


def print_results(results: dict, config: TaxConfig):
    """Print formatted results."""
    tax = results["tax"]
    withholding = results["withholding"]
    safe_harbor = results["safe_harbor"]

    print("\n" + "=" * 70)
    print("          QUARTERLY ESTIMATED TAX CALCULATION (Form 1040-ES)")
    print("=" * 70)

    # Filing Status
    status_display = config.filing_status.replace("_", " ").title()
    print(f"\nFiling Status: {status_display}")

    # Income Summary
    print("\n" + "-" * 40)
    print("INCOME SUMMARY")
    print("-" * 40)
    print(f"  W-2 Wages:                  {format_currency(config.w2_wages):>15}")
    print(f"  RSU Income:                 {format_currency(config.rsu_income):>15}")
    print(f"  Qualified Dividends:        {format_currency(config.qualified_dividends):>15}")
    print(f"  Ordinary Dividends:         {format_currency(config.ordinary_dividends):>15}")
    print(f"  Interest Income:            {format_currency(config.interest_income):>15}")
    print(f"  Short-Term Capital Gains:   {format_currency(config.short_term_capital_gains):>15}")
    print(f"  Long-Term Capital Gains:    {format_currency(config.long_term_capital_gains):>15}")
    print(f"  Other Income:               {format_currency(config.other_income):>15}")
    print(f"                              {'-' * 15}")
    print(f"  Gross Income:               {format_currency(tax['gross_income']):>15}")
    print(f"  Above-Line Deductions:      {format_currency(config.above_line_deductions):>15}")
    print(f"  Adjusted Gross Income:      {format_currency(tax['agi']):>15}")

    # Deductions
    print("\n" + "-" * 40)
    print("DEDUCTIONS")
    print("-" * 40)
    deduction_type = "Standard" if config.use_standard_deduction else "Itemized"
    print(f"  {deduction_type} Deduction:        {format_currency(tax['deduction']):>15}")
    print(f"  Taxable Income:             {format_currency(tax['taxable_income']):>15}")

    # Tax Calculation
    print("\n" + "-" * 40)
    print("TAX CALCULATION")
    print("-" * 40)
    marginal_rate = get_marginal_rate(tax["ordinary_taxable_income"], config.filing_status)
    print(f"  Ordinary Income Tax:        {format_currency(tax['ordinary_income_tax']):>15}")
    print(f"    (Marginal rate: {marginal_rate * 100:.0f}%)")
    print(f"  Qualified Div/LTCG Tax:     {format_currency(tax['ltcg_tax']):>15}")
    print(f"    (On {format_currency(tax['preferential_income'])} preferential income)")

    if tax["niit"] > 0:
        print(f"  Net Investment Income Tax:  {format_currency(tax['niit']):>15}")
        print(f"    (3.8% on {format_currency(tax['investment_income'])} investment income)")

    print(f"                              {'-' * 15}")
    print(f"  Tax Before Credits:         {format_currency(tax['total_tax_before_credits']):>15}")

    if config.tax_credits > 0:
        print(f"  Tax Credits:               -{format_currency(config.tax_credits):>14}")

    print(f"  TOTAL TAX LIABILITY:        {format_currency(tax['total_tax']):>15}")

    # Virginia State Tax
    va = results["va"]
    print("\n" + "-" * 40)
    print("VIRGINIA STATE TAX")
    print("-" * 40)
    print(f"  Federal AGI:                {format_currency(va['va_agi']):>15}")
    print(f"  VA Standard Deduction:      {format_currency(va['va_deduction']):>15}")
    print(f"  VA Personal Exemptions:     {format_currency(va['va_exemptions']):>15}")
    print(f"    ({va['va_exemption_count']} x {format_currency(VA_PERSONAL_EXEMPTION)})")
    print(f"  VA Taxable Income:          {format_currency(va['va_taxable_income']):>15}")
    print(f"  VA TAX LIABILITY:           {format_currency(va['va_tax']):>15}")

    # Withholding
    print("\n" + "-" * 40)
    print("WITHHOLDING & PAYMENTS")
    print("-" * 40)
    w2_label = "W-2 Federal Withholding"
    if withholding.get("w2_withholding_estimated"):
        w2_label += " (est)"
    print(f"  {w2_label + ':':<30}{format_currency(withholding['w2_withholding']):>15}")
    print(f"  RSU Withholding (22%):      {format_currency(withholding['rsu_withholding']):>15}")
    va_wh_label = "VA State Withholding"
    if results.get("va_withholding_estimated"):
        va_wh_label += " (est)"
    print(f"  {va_wh_label + ':':<30}{format_currency(results['va_withholding']):>15}")
    if withholding["estimated_payments_made"] > 0:
        print(f"  Estimated Payments Made:    {format_currency(withholding['estimated_payments_made']):>15}")
    print(f"                              {'-' * 15}")
    print(f"  Total Federal Withholding:  {format_currency(withholding['total_withholding']):>15}")

    # Tax Owed/Refund
    print("\n" + "-" * 40)
    print("BALANCE")
    print("-" * 40)
    if results["tax_owed"] >= 0:
        print(f"  Estimated Tax Owed:         {format_currency(results['tax_owed']):>15}")
    else:
        print(f"  Estimated Refund:           {format_currency(abs(results['tax_owed'])):>15}")

    # Safe Harbor
    print("\n" + "-" * 40)
    print("SAFE HARBOR ANALYSIS")
    print("-" * 40)
    print(f"  90% of Current Year Tax:    {format_currency(safe_harbor['current_year_90_percent']):>15}")
    if safe_harbor["prior_year_safe_harbor"] is not None:
        print(f"  {safe_harbor['prior_year_multiplier']} of Prior Year Tax:     {format_currency(safe_harbor['prior_year_safe_harbor']):>15}")
        print(f"  Minimum Required Payment:   {format_currency(safe_harbor['minimum_required']):>15}")
        print("    (Lesser of above two amounts)")
    else:
        print("  Prior year tax not provided - using 90% current year")

    # RSU Underwithholding Analysis
    if config.rsu_income > 0:
        print("\n" + "-" * 40)
        print("RSU UNDERWITHHOLDING ANALYSIS")
        print("-" * 40)
        rsu_at_22 = config.rsu_income * Decimal("0.22")
        rsu_at_marginal = config.rsu_income * marginal_rate
        rsu_shortfall = rsu_at_marginal - rsu_at_22
        print(f"  RSU Income:                 {format_currency(config.rsu_income):>15}")
        print(f"  Withheld at 22%:            {format_currency(rsu_at_22):>15}")
        print(f"  Tax at Marginal Rate ({marginal_rate*100:.0f}%):{format_currency(rsu_at_marginal):>15}")
        if rsu_shortfall > 0:
            print(f"  Estimated Shortfall:        {format_currency(rsu_shortfall):>15}")
            print("  (RSU withholding is below your marginal rate)")

    # Quarterly Payments
    print("\n" + "=" * 70)
    print("          QUARTERLY ESTIMATED TAX PAYMENTS")
    print("=" * 70)

    print("\n  To avoid underpayment penalties, pay at least:")
    print(f"  {format_currency(results['quarterly_required'])} per quarter")

    print("\n  To pay your full estimated tax liability:")
    print(f"  {format_currency(results['quarterly_recommended'])} per quarter")

    print("\n  Payment Schedule:")
    print("  " + "-" * 50)
    for i, due_date in enumerate(results["due_dates"], 1):
        print(f"  Q{i}: {due_date:25} {format_currency(results['quarterly_recommended']):>15}")
    print("  " + "-" * 50)
    print(f"  Total:                               {format_currency(results['recommended_estimated_total']):>15}")

    print("\n  Pay online at: https://www.irs.gov/payments")
    print("  Select 'Estimated Tax' and tax year when paying")

    # Virginia Quarterly Payments
    print("\n" + "=" * 70)
    print("       VIRGINIA QUARTERLY ESTIMATED TAX PAYMENTS")
    print("=" * 70)

    if results["va_quarterly"] > 0:
        print(f"\n  VA Tax Liability:           {format_currency(results['va']['va_tax']):>15}")
        print(f"  VA Withholding:            -{format_currency(results['va_withholding']):>14}")
        print(f"  VA Estimated Tax Needed:    {format_currency(results['va_estimated_total']):>15}")
        print(f"  Per Quarter:                {format_currency(results['va_quarterly']):>15}")

        print("\n  Payment Schedule:")
        print("  " + "-" * 50)
        for i, due_date in enumerate(results["va_due_dates"], 1):
            print(f"  Q{i}: {due_date:25} {format_currency(results['va_quarterly']):>15}")
        print("  " + "-" * 50)
        print(f"  Total:                               {format_currency(results['va_estimated_total']):>15}")
    else:
        print("\n  No Virginia estimated payments needed.")
        print(f"  VA withholding ({format_currency(results['va_withholding'])}) covers VA tax ({format_currency(results['va']['va_tax'])}).")

    print("\n  Pay online at: https://www.individual.tax.virginia.gov/")

    print("\n" + "=" * 70)
    print("DISCLAIMER: This is an estimate only. Consult a tax professional")
    print("for advice specific to your situation. Tax laws change frequently.")
    print("=" * 70 + "\n")


def create_sample_config(path: str):
    """Create a sample configuration file."""
    sample = """# Estimated Tax Calculator Configuration
# ========================================
# Edit these values to match your expected income for the tax year.
# All monetary values are in dollars (no commas or $ signs needed).

# Filing Status
# Options: single, married_filing_jointly, married_filing_separately, head_of_household
filing_status: single

# W-2 Employment Income
# ---------------------
w2_wages: 150000                    # Total expected W-2 wages
w2_federal_withholding: 25000       # Federal tax withheld (0 = auto-estimate from brackets)

# RSU Income (Restricted Stock Units)
# -----------------------------------
# RSU income is typically withheld at a flat 22% supplemental rate,
# which may be less than your marginal tax rate.
rsu_income: 50000                   # Total expected RSU vesting value
rsu_withholding: 0                  # Leave at 0 to auto-calculate at 22%
                                    # Or enter actual withholding if different

# Investment Income (Taxable Brokerage)
# -------------------------------------
qualified_dividends: 5000           # Dividends eligible for lower tax rates
ordinary_dividends: 1000            # Non-qualified dividends (taxed as ordinary income)
interest_income: 2000               # Interest from savings, bonds, etc.
short_term_capital_gains: 0         # Gains on assets held < 1 year
long_term_capital_gains: 0          # Gains on assets held >= 1 year

# Other Income
# ------------
other_income: 0                     # Freelance, rental, etc.

# Deductions
# ----------
use_standard_deduction: true        # Set to false to use itemized deductions
itemized_deductions: 0              # Only used if use_standard_deduction is false
above_line_deductions: 23000        # 401(k), HSA, IRA contributions, etc.

# Tax Credits
# -----------
tax_credits: 0                      # Child tax credit, education credits, etc.

# Prior Year Tax (for Safe Harbor Calculation)
# --------------------------------------------
# Safe harbor: Avoid penalties by paying 100% of prior year tax
# (or 110% if prior year AGI exceeded $150,000)
prior_year_tax: 30000               # Total tax from prior year's return (line 24)
prior_year_agi: 180000              # AGI from prior year's return

# Estimated Payments Already Made
# -------------------------------
estimated_payments_made: 0          # Estimated tax payments already made this year

# Virginia State Tax
# ------------------
va_withholding: 0                   # VA state withholding (0 = auto-estimate from brackets)
"""
    with open(path, "w") as f:
        f.write(sample)
    print(f"Sample configuration file created: {path}")
    print("Edit this file with your expected income and run the calculator again.")


def main():
    """Main entry point."""
    # Determine config file path
    if len(sys.argv) > 1:
        config_path = sys.argv[1]
    else:
        config_path = "tax_config.yaml"

    # Check if config exists
    if not Path(config_path).exists():
        print(f"Configuration file not found: {config_path}")
        print()
        create_response = input("Would you like to create a sample configuration file? [Y/n] ")
        if create_response.lower() != "n":
            create_sample_config(config_path)
        return

    try:
        # Load configuration
        config = load_config(config_path)

        # Calculate quarterly payments
        results = calculate_quarterly_payments(config)

        # Print results
        print_results(results, config)

    except yaml.YAMLError as e:
        print(f"Error parsing configuration file: {e}")
        sys.exit(1)
    except ValueError as e:
        print(f"Configuration error: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
