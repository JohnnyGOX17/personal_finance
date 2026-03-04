# Python for Personal Finance

Python scripts and helper methods for Personal Finance, especially around US Taxes.

> [!CAUTION]
> This calculator provides estimates only. Tax laws are complex and change frequently. Consult a qualified tax professional for advice specific to your situation.

## Estimated Tax Calculator

Calculates quarterly estimated tax payments based on IRS Form 1040-ES guidelines. Designed for taxpayers with income from:
- W-2 wages
- RSU vesting (with supplemental 22% flat withholding)
- Dividends and interest from taxable brokerage accounts
- Capital gains

### Features

- **2026 Tax Year Brackets** - Federal income tax brackets, standard deductions, qualified dividend/LTCG rates
- **RSU Underwithholding Analysis** - Shows the gap between 22% supplemental withholding and your actual marginal rate
- **Safe Harbor Calculation** - Determines minimum payment to avoid underpayment penalties (90% of current year OR 100%/110% of prior year tax)
- **Net Investment Income Tax (NIIT)** - Automatically applies 3.8% surtax when AGI exceeds thresholds ($200K single, $250K MFJ)
- **Preferential Tax Rates** - Qualified dividends and long-term capital gains taxed at 0%/15%/20% based on income
- **Virginia State Tax** - Calculates VA income tax with progressive brackets, standard deduction, and personal exemptions
- **Auto-Estimated Withholding** - Optionally estimates federal and VA state withholding from wages using tax brackets when not provided
- **Quarterly Payment Schedule** - Shows federal and VA state payment amounts with 2026 due dates

### Installation

```bash
# Using uv (recommended)
uv sync
```

### Usage

```bash
# Run with default config (tax_config.yaml in current directory)
uv run python estimated_tax_calculator.py

# Run with a specific config file
uv run python estimated_tax_calculator.py my_config.yaml
```

If no config file exists, the script will offer to create a sample `tax_config.yaml` for you.

### Configuration Schema

Create a YAML file with the following fields:

```yaml
# =============================================================================
# FILING STATUS (required)
# =============================================================================
# Options: single, married_filing_jointly, married_filing_separately, head_of_household
filing_status: single

# =============================================================================
# W-2 EMPLOYMENT INCOME
# =============================================================================
w2_wages: 150000                    # Total expected W-2 wages for the year
w2_federal_withholding: 0           # Federal tax withheld (0 = auto-estimate from brackets)
                                    # Or enter actual amount from pay stubs / YTD

# =============================================================================
# RSU INCOME (Restricted Stock Units)
# =============================================================================
# RSUs are typically withheld at a flat 22% "supplemental wage" rate,
# which is often less than your marginal tax bracket.
rsu_income: 50000                   # Total expected RSU vesting value for the year
rsu_withholding: 0                  # Leave at 0 to auto-calculate at 22%
                                    # Or enter actual withholding if your employer
                                    # uses a different rate

# =============================================================================
# INVESTMENT INCOME (Taxable Brokerage Accounts)
# =============================================================================
# Qualified dividends: Most US stock dividends; taxed at preferential 0/15/20% rates
# Ordinary dividends: REITs, money market funds, short-term holdings; taxed as ordinary income
qualified_dividends: 5000
ordinary_dividends: 1000

# Interest income: Savings accounts, CDs, bonds, money market funds
interest_income: 2000

# Capital gains from selling investments
short_term_capital_gains: 0         # Assets held < 1 year (taxed as ordinary income)
long_term_capital_gains: 0          # Assets held >= 1 year (taxed at 0/15/20%)

# =============================================================================
# OTHER INCOME
# =============================================================================
other_income: 0                     # Freelance, rental income, etc.

# =============================================================================
# DEDUCTIONS
# =============================================================================
use_standard_deduction: true        # true = use standard deduction
                                    # false = use itemized_deductions value below

itemized_deductions: 0              # Only used if use_standard_deduction is false
                                    # (SALT, mortgage interest, charitable, etc.)

# Above-the-line deductions reduce AGI directly
above_line_deductions: 23000        # 401(k) contributions (employee portion)
                                    # Traditional IRA contributions
                                    # HSA contributions
                                    # Student loan interest
                                    # Self-employment deductions

# =============================================================================
# TAX CREDITS
# =============================================================================
tax_credits: 0                      # Child tax credit, education credits,
                                    # energy credits, etc.

# =============================================================================
# PRIOR YEAR TAX (for Safe Harbor Calculation)
# =============================================================================
# Safe harbor rule: You won't owe penalties if you pay either:
#   - 90% of current year tax, OR
#   - 100% of prior year tax (110% if prior year AGI > $150,000)
#
# Find these on your prior year Form 1040:
prior_year_tax: 30000               # Line 24 (Total Tax) from prior year return
prior_year_agi: 180000              # Line 11 (Adjusted Gross Income) from prior year

# =============================================================================
# ESTIMATED PAYMENTS ALREADY MADE
# =============================================================================
estimated_payments_made: 0          # Quarterly estimated payments already sent to IRS
                                    # this tax year (useful for mid-year calculations)

# =============================================================================
# VIRGINIA STATE TAX
# =============================================================================
va_withholding: 0                   # VA state withholding (0 = auto-estimate from brackets)
                                    # Or enter actual amount from pay stubs / YTD
```

### Output

The calculator provides:

1. **Income Summary** - Breakdown of all income sources and AGI calculation
2. **Tax Calculation** - Ordinary income tax, qualified dividend/LTCG tax, and NIIT
3. **Virginia State Tax** - VA income tax with deductions, exemptions, and liability
4. **Withholding Summary** - Federal and VA state withholding from all sources
5. **Safe Harbor Analysis** - Minimum required payment to avoid penalties
6. **RSU Underwithholding Analysis** - Gap between 22% withholding and marginal rate
7. **Federal Quarterly Payments** - Four federal payment amounts with due dates
8. **Virginia Quarterly Payments** - Four VA state payment amounts with due dates

### Quarterly Due Dates (2026)

**Federal (IRS):**

| Quarter | Due Date |
|---------|----------|
| Q1 | April 15, 2026 |
| Q2 | June 15, 2026 |
| Q3 | September 15, 2026 |
| Q4 | January 15, 2027 |

**Virginia:**

| Quarter | Due Date |
|---------|----------|
| Q1 | May 1, 2026 |
| Q2 | June 15, 2026 |
| Q3 | September 15, 2026 |
| Q4 | January 15, 2027 |

### Paying Estimated Taxes

**Federal:** Pay online at [IRS Direct Pay](https://www.irs.gov/payments):
1. Select "Estimated Tax" as the reason for payment
2. Select the appropriate tax year
3. Enter payment amount and bank information

**Virginia:** Pay online at [Virginia Tax](https://www.individual.tax.virginia.gov/)


## References

- [IRS Form 1040-ES](https://www.irs.gov/pub/irs-pdf/f1040es.pdf)
