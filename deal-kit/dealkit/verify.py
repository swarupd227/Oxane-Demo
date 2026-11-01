"""Independently check the built pack against the answer key.

This reads only the files in output/ and deliberately imports nothing from the
generators, so a mistake there cannot hide itself here.

    python -m dealkit.verify
"""

import csv
import json
import re
import sys
from collections import Counter, defaultdict
from decimal import Decimal
from pathlib import Path

import pdfplumber
from openpyxl import load_workbook

OUTPUT = Path(__file__).resolve().parent.parent / "output"
PACK = OUTPUT / "pack"
KEY = OUTPUT / "answer-key"
ZERO = Decimal(0)
TOLERANCE = Decimal("0.02")
STATES = set(
    "AL AK AZ AR CA CO CT DE FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV NH NJ NM "
    "NY NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY DC".split()
)

checks: list[tuple[bool, str]] = []


def check(passed: bool, label: str) -> None:
    checks.append((bool(passed), label))


def key(name: str):
    return json.loads((KEY / f"{name}.json").read_text(encoding="utf-8"))


def close(left: Decimal | float, right: Decimal | float) -> bool:
    return abs(Decimal(str(left)) - Decimal(str(right))) <= TOLERANCE


def read_tape(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def rule_failures(row: dict[str, str], vins: Counter[str]) -> set[str]:
    balance = Decimal(row["CurrBal"])
    apr = Decimal(row["NoteRate"])
    origination_year = int(row["OrigDate"][-4:])
    failed = set()
    if int(row["DPD"]) > 30:
        failed.add("E1")
    if row["LoanStatus"] in ("CHARGED_OFF", "REPO"):
        failed.add("E2")
    if int(row["OrigTerm"]) > 84:
        failed.add("E3")
    if int(row["CreditScore"]) < 540:
        failed.add("E4")
    if balance > 75000:
        failed.add("E5")
    if row["BorrState"] not in STATES:
        failed.add("E6")
    if int(row["ModCount"]) > 1:
        failed.add("E8")
    if not Decimal("6.00") <= apr <= Decimal("29.99"):
        failed.add("E9")
    if origination_year - int(row["ModelYr"]) > 10:
        failed.add("E10")
    if int(row["PmtsMade"]) < 1:
        failed.add("E11")
    if vins[row["VIN"]] != 1:
        failed.add("E12")
    return failed


def base(pool: Decimal, excess: Decimal, rate: Decimal = Decimal("0.825")) -> Decimal:
    return (pool - excess) * rate - pool * Decimal("0.01")


def check_tape(rows: list[dict[str, str]], calc: dict, rules: dict, exceptions: dict) -> None:
    check(len(rows) == 2400, "Tape has 2,400 rows")
    check(len(rows[0]) == 38, "Tape has 38 columns")

    vins = Counter(row["VIN"] for row in rows)
    results = {row["LoanNumber"]: rule_failures(row, vins) for row in rows}
    failed_by_rule: defaultdict[str, set[str]] = defaultdict(set)
    for loan, failed in results.items():
        for rule in failed:
            failed_by_rule[rule].add(loan)
    for rule, expected in rules.items():
        if expected["status"] == "evaluated":
            check(failed_by_rule[rule] == set(expected["loan_ids"]),
                  f"{rule}: {len(failed_by_rule[rule])} failures match the key")
    check(rules["E7"]["status"] == "not_evaluated", "E7 is marked not evaluated")

    balances = {row["LoanNumber"]: Decimal(row["CurrBal"]) for row in rows}
    eligible = [row for row in rows if not results[row["LoanNumber"]]]
    pool = sum((Decimal(row["CurrBal"]) for row in eligible), ZERO)
    system = calc["system_before_dealer_match"]
    after = calc["system_after_dealer_match"]
    borrower = calc["borrower_certificate"]
    check(close(pool, system["eligible_pool"]), f"System eligible pool recalculates to {pool:,}")
    check(close(base(pool, ZERO), system["borrowing_base"]), "System borrowing base recalculates")

    dealers: defaultdict[str, Decimal] = defaultdict(Decimal)
    states: defaultdict[str, Decimal] = defaultdict(Decimal)
    for row in eligible:
        dealers[row["DealerName"]] += Decimal(row["CurrBal"])
        states[row["BorrState"]] += Decimal(row["CurrBal"])
    limit = pool * Decimal("0.05")
    check(all(value <= limit for value in dealers.values()),
          "Before the match, no single dealer name breaches 5%")
    check(max(states.values()) <= pool * Decimal("0.20"), "No state breaches 20%")
    long_term = sum((Decimal(r["CurrBal"]) for r in eligible if int(r["OrigTerm"]) > 72), ZERO)
    low_fico = sum((Decimal(r["CurrBal"]) for r in eligible if int(r["CreditScore"]) < 600), ZERO)
    used = sum((Decimal(r["CurrBal"]) for r in eligible if r["NewUsed"] == "USED"), ZERO)
    check(long_term <= pool * Decimal("0.25"), "Long-term loans are under 25%")
    check(low_fico <= pool * Decimal("0.35"), "FICO below 600 is under 35%")
    check(used <= pool * Decimal("0.70"), "Used vehicles are under 70%")

    late = [row for row in rows if int(row["DPD"]) > 0]
    check(all(row["NextDueDate"] < row["CutoffDate"] for row in late),
          "Every past-due loan has a next due date before the cut-off")
    current = [row for row in rows if int(row["DPD"]) == 0]
    check(all(row["NextDueDate"] > row["CutoffDate"] for row in current),
          "Every current loan has a next due date after the cut-off")
    check(all(row["LastPmtDate"] < row["NextDueDate"] for row in rows),
          "Every last payment comes before the next due date")
    prefixes = defaultdict(set)
    for row in rows:
        prefixes[row["BorrZip3"]].add(row["BorrState"])
    check(all(len(states) == 1 for code, states in prefixes.items() if code),
          "No ZIP prefix appears in two states")

    x4 = exceptions["X4"]
    total_x4 = sum((balances[i] for i in x4["loan_ids"]), ZERO)
    check(x4["loans"] == 41, "X4: 41 loans")
    check(all(31 <= int(r["DPD"]) <= 60 for r in rows if r["LoanNumber"] in set(x4["loan_ids"])),
          "X4: every loan is 31 to 60 days past due")
    check(all(balances[i] <= 75000 for i in x4["loan_ids"]), "X4: every loan is within the cap")
    check(Decimal(1050000) <= total_x4 <= Decimal(1150000),
          f"X4: gap is about US$1.1m ({total_x4:,})")
    only_e1 = all(results[i] == {"E1"} for i in x4["loan_ids"])
    check(only_e1, "X4: these loans fail only the past-due test")

    x5 = exceptions["X5"]
    shared = [vin for vin, count in vins.items() if count > 1]
    check(len(shared) == 3 and all(vins[vin] == 2 for vin in shared), "X5: 3 VINs across 6 loans")
    check(sorted(shared) == sorted(c["vin"] for c in x5["clusters"]), "X5: VINs match the key")

    bridge = calc["eligible_pool_bridge"]
    gap = Decimal(str(borrower["eligible_pool"])) - pool
    check(close(gap, total_x4 + sum((balances[i] for c in x5["clusters"]
                                     for i in c["loan_ids"]), ZERO)),
          f"Bridge: gap of {gap:,} is fully explained by X4 and X5")
    check(close(bridge["borrower"] + bridge["past_due_loans"] + bridge["duplicate_vin_loans"],
                bridge["system"]), "Bridge lines sum to the system figure")

    x6 = exceptions["X6"]
    first, second = x6["names"]
    combined = dealers[first] + dealers[second]
    excess = combined - limit
    check(combined > limit, f"X6: the matched dealer breaches 5% ({combined / pool:.2%})")
    check(close(excess, after["excess_concentration"]), "X6: excess matches the key")
    check(close(base(pool, excess), after["borrowing_base"]), "X6: new borrowing base matches")
    check(after["availability"] > 0, "Availability stays positive after the match")

    formats = Counter()
    for row in rows:
        first_part, second_part, _ = row["OrigDate"].split("/")
        if int(second_part) > 12:
            formats["month_first"] += 1
        elif int(first_part) > 12:
            formats["day_first"] += 1
    check(formats["day_first"] > 0 and formats["month_first"] > 0,
          f"X9: both date formats are present ({formats['day_first']} clearly day-first)")
    check(exceptions["X9"]["rows"] == 120, "X9: 120 rows are planted")


def check_certificate(calc: dict) -> None:
    sheet = load_workbook(PACK / "Bramble_BBC_April_2026.xlsx")["BBC Summary"]
    borrower = calc["borrower_certificate"]
    check(close(sheet["B7"].value, borrower["eligible_pool"]), "Certificate eligible pool matches")
    check(close(sheet["B11"].value, borrower["borrowing_base"]), "Certificate base matches")
    check(sheet["B9"].value == 0.825, "Certificate uses the amended advance rate")
    check(close(sheet["B13"].value, borrower["availability"]), "Certificate availability matches")
    check(borrower["eligible_pool"] > calc["system_before_dealer_match"]["eligible_pool"],
          "Borrower's eligible pool is higher than the system's")


def check_documents(fields: list[dict], pack: dict, exceptions: dict) -> None:
    expected_pages = {"amendment_1": 6, "fee_letter": 2, "servicer_report": 9,
                      "financial_statements": 14}
    pages: dict[str, list[str]] = {}
    for doc, name in pack.items():
        if name.endswith(".pdf"):
            with pdfplumber.open(PACK / name) as pdf:
                pages[doc] = [re.sub(r"\s+", " ", p.extract_text() or "") for p in pdf.pages]
    for doc, count in expected_pages.items():
        check(len(pages[doc]) == count, f"{doc} has {count} pages ({len(pages[doc])})")
    agreement = pages["credit_agreement"]
    check(58 <= len(agreement) <= 72, f"Credit agreement is about 64 pages ({len(agreement)})")

    whole = " ".join(agreement)
    check("Restricted Jurisdiction" in whole, "X2: the agreement uses Restricted Jurisdiction")
    check("each state, territory or other jurisdiction listed in Schedule 4" in whole,
          "X2: the definition points to Schedule 4")
    check(not any("SCHEDULE 4 —" in page or "SCHEDULE 4 - " in page for page in agreement),
          "X2: Schedule 4 itself is not in the pack")
    check('The "Advance Rate" means 85%' in whole, "X1: the agreement states 85%")
    check('"85%" is deleted and replaced with "82.5%"' in " ".join(pages["amendment_1"]),
          "X1: the amendment states 82.5%")
    check("US$250,000,000" not in whole, "X3: the facility limit appears only on the scan")
    check(sum(1 for page in agreement if len(page.strip()) < 60) == 1, "X3: one image-only page")
    check("Tangible Net Worth" in whole and "Solely for the purpose of calculating the Leverage"
          in whole, "X10: the cross-reference is present")
    check(exceptions["X10"]["leverage_without_carve_out"] > 6 >
          exceptions["X10"]["leverage_with_carve_out"], "X10: the carve-out changes the result")

    servicer = " ".join(pages["servicer_report"])
    check("Recoveries (US$)" in servicer, "X7: the recoveries line is present")
    with pdfplumber.open(PACK / pack["servicer_report"]) as pdf:
        lines = [line.strip() for p in pdf.pages for line in (p.extract_text() or "").splitlines()]
    check("Recoveries (US$)" in lines, "X7: April recoveries are blank")
    check(exceptions["X7"]["three_month_average_pct"] < exceptions["X7"]["trigger_pct"],
          "X7: the delinquency trigger can still run and does not trip")

    for field in fields:
        if field["quote"]:
            body = pages[field["document"]][field["page"] - 1]
            check(re.sub(r"\s+", " ", field["quote"]) in body,
                  f"Field '{field['name']}' quote is on page {field['page']}")
    check(len(fields) == 26, "26 fields in the key")
    tiers = Counter(field["tier"] for field in fields)
    check(tiers == {1: 11, 2: 9, 3: 6}, f"Tier counts are 11, 9 and 6 ({dict(tiers)})")


def check_workbook() -> None:
    book = load_workbook(PACK / "Calderwood_Requirements.xlsx")
    names = [row[0].value for row in book["Required Fields"].iter_rows()]
    check("Weighted average APR" in names, "X8: the lender asks for weighted average APR")
    check(book["Alerts"].max_row - 1 == 6, "Six lender alerts")


def main() -> int:
    calc, rules, exceptions = key("calculation"), key("rules"), key("exceptions")
    rows = read_tape(PACK / "BAF_Loan_Tape_2026-04.csv")
    check_tape(rows, calc, rules, exceptions)
    check_certificate(calc)
    check_documents(key("fields"), key("pack"), exceptions)
    check_workbook()
    check("Weighted average APR" not in rows[0], "X8: weighted average APR is not a tape column")
    check(len(exceptions) == 10, "10 exceptions in the key")

    failed = [label for passed, label in checks if not passed]
    for passed, label in checks:
        print(f"{'PASS' if passed else 'FAIL'}  {label}")
    print(f"\n{len(checks) - len(failed)} of {len(checks)} checks passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
