"""Amendment No. 1 and the fee letter."""

from pathlib import Path
from typing import Any

from reportlab.lib.units import inch
from reportlab.platypus import PageBreak, Spacer

from dealkit.pdfkit import ARTICLE, BODY, CENTERED, INDENT_1, SECTION, TITLE, build, text


def _date(value: Any) -> str:
    return f"{value.day} {value:%B %Y}"


def build_amendment(deal: dict[str, Any], path: Path) -> None:
    terms = deal["terms"]
    borrower, lender = deal["borrower"]["name"], deal["lender"]["name"]
    signed, effective = _date(terms["amendment_signed"]), _date(terms["amendment_effective"])
    original = f"{terms['advance_rate_original_pct']}%"
    amended = f"{terms['advance_rate_amended_pct']}%"
    agreement_date = _date(terms["signing_date"])

    story = [
        Spacer(1, 1.5 * inch),
        text("AMENDMENT NO. 1 TO CREDIT AGREEMENT", TITLE),
        text(f"dated {signed}", CENTERED),
        Spacer(1, 0.3 * inch),
        text("between", CENTERED),
        text(borrower.upper(), CENTERED),
        text("as Borrower", CENTERED),
        text("and", CENTERED),
        text(lender.upper(), CENTERED),
        text("as Lender and Administrative Agent", CENTERED),
        PageBreak(),
        text(f"This Amendment No. 1 (this \"Amendment\") is dated {signed} and is made between "
             f"{borrower} and {lender}. It amends the Credit Agreement dated as of "
             f"{agreement_date} (the \"Credit Agreement\")."),
        text("1. Definitions", SECTION),
        text("Capitalised terms used and not defined in this Amendment have the meanings given "
             "in the Credit Agreement."),
        text("2. Amendments to the Credit Agreement", SECTION),
        text(f"(a) In Section 2.3, \"{original}\" is deleted and replaced with \"{amended}\", "
             f"with effect from {effective}.", INDENT_1),
        text("(b) In Schedule 2, a new row 5 is added after row 4, with effect from "
             f"{effective}, reading as follows: \"5. Receivables with an Obligor FICO score at "
             "origination below 600: 35%\".", INDENT_1),
        text("(c) Each Borrowing Base Certificate for a Collection Period ending on or after "
             f"{effective} shall be calculated using the Credit Agreement as amended by this "
             "Amendment. No Borrowing Base Certificate for an earlier Collection Period is "
             "reopened.", INDENT_1),
        PageBreak(),
        text("3. Conditions to Effectiveness", SECTION),
        text("This Amendment takes effect on the date on which the Lender has received each of "
             "the following in form and substance satisfactory to it:"),
        text("(a) this Amendment, signed by each party;", INDENT_1),
        text("(b) a certificate of a Responsible Officer of the Borrower confirming that the "
             "representations in Section 4 of this Amendment are true;", INDENT_1),
        text("(c) a copy of the resolutions of the Borrower approving this Amendment; and",
             INDENT_1),
        text("(d) payment of all costs and expenses then due under Section 10.3 of the Credit "
             "Agreement.", INDENT_1),
        PageBreak(),
        text("4. Representations", SECTION),
        text("The Borrower represents to the Lender on the date of this Amendment and on "
             f"{effective} that:"),
        text("(a) each representation in Article 4 of the Credit Agreement is true and correct "
             "in all material respects, except to the extent it relates to an earlier date;",
             INDENT_1),
        text("(b) no Default or Event of Default has occurred and is continuing; and", INDENT_1),
        text("(c) it has the power to enter into this Amendment, and this Amendment is its legal, "
             "valid and binding obligation.", INDENT_1),
        PageBreak(),
        text("5. Continuing Effect", SECTION),
        text("Except as expressly amended by this Amendment, the Credit Agreement remains in full "
             "force and effect, and all references to the Credit Agreement in the Transaction "
             "Documents are to the Credit Agreement as amended by this Amendment."),
        text("6. Governing Law and Counterparts", SECTION),
        text(f"This Amendment is governed by the law of the State of {terms['governing_law']}. "
             "It may be signed in counterparts, each of which is an original and all of which "
             "form one instrument. Section 10.10 and Section 10.11 of the Credit Agreement apply "
             "to this Amendment."),
        PageBreak(),
        text("IN WITNESS WHEREOF, the parties have signed this Amendment on the date stated "
             "above."),
        Spacer(1, 0.4 * inch),
        text(f"{borrower.upper()}, as Borrower", BODY),
        text("By: /s/ (signature on file)", BODY),
        Spacer(1, 0.4 * inch),
        text(f"{lender.upper()}, as Lender and Administrative Agent", BODY),
        text("By: /s/ (signature on file)", BODY),
    ]
    build(path, story, "Amendment No. 1", "Amendment No. 1 to Credit Agreement")


def build_fee_letter(deal: dict[str, Any], path: Path) -> None:
    terms = deal["terms"]
    borrower, lender = deal["borrower"]["name"], deal["lender"]["name"]
    story = [
        text(lender, ARTICLE),
        text(deal["lender"]["address"], CENTERED),
        Spacer(1, 0.3 * inch),
        text(_date(terms["signing_date"])),
        text(borrower),
        text(deal["borrower"]["address"]),
        Spacer(1, 0.15 * inch),
        text("Fee Letter: Senior Secured Revolving Warehouse Facility", SECTION),
        text("We refer to the Credit Agreement dated as of the date of this letter between you "
             "and us. Capitalised terms have the meanings given in the Credit Agreement. This "
             "letter is a Transaction Document and is strictly confidential."),
        text("1. Arrangement Fee", SECTION),
        text(f"You shall pay us an arrangement fee of {terms['arrangement_fee_pct']:.2f}% of the "
             "Facility Limit on the Closing Date. The fee is fully earned on payment and is not "
             "refundable."),
        text("2. Unused Fee", SECTION),
        text(f"You shall pay us an Unused Fee of {terms['unused_fee_pct']:.2f}% a year on the "
             "amount by which the Facility Limit exceeds the daily average outstanding principal "
             "amount of the Advances during each Interest Period, calculated on the basis of the "
             "actual number of days elapsed and a year of 360 days and payable monthly in arrears "
             "on each Payment Date."),
        PageBreak(),
        text("3. Payment", SECTION),
        text("All amounts under this letter shall be paid in US dollars in immediately available "
             "funds, without set-off or deduction, and are in addition to any other amount "
             "payable under the Transaction Documents."),
        text("4. Governing Law", SECTION),
        text(f"This letter is governed by the law of the State of {terms['governing_law']}."),
        text("Please confirm your agreement by signing below."),
        Spacer(1, 0.3 * inch),
        text(f"Yours faithfully, for and on behalf of {lender}"),
        text("/s/ (signature on file)"),
        Spacer(1, 0.3 * inch),
        text(f"Agreed and accepted for and on behalf of {borrower}"),
        text("/s/ (signature on file)"),
    ]
    build(path, story, "Fee Letter", "Strictly confidential")
