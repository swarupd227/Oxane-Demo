"""Collection account statements for the two auto facilities: the bank statements their
schedules expect each month. They are filed and tracked; no test reads them this cycle."""

from datetime import date
from pathlib import Path
from typing import Any

from reportlab.lib.units import inch
from reportlab.platypus import Spacer

from dealkit.legal_docs import _date
from dealkit.pdfkit import REPORT_BODY, REPORT_HEAD, REPORT_TITLE, SANS, build, table, text

FILES = {
    "bramble": "BAF_Collection_Account_Statement_May_2026.pdf",
    "northmoor": "NMC_Collection_Account_Statement_May_2026.pdf",
}


def build_statement(account: str, holder: str, opening: int, collections: int, sweeps: int,
                    path: Path) -> None:
    closing = opening + collections - sweeps
    story: list[Any] = [
        text("Calderwood Bank plc: account services", REPORT_TITLE),
        text("Statement of account, May 2026", REPORT_HEAD),
        text(f"Account holder: {holder}. Account: {account}. Period: {_date(date(2026, 5, 1))} "
             f"to {_date(date(2026, 5, 31))}.", REPORT_BODY),
        Spacer(1, 0.15 * inch),
        table([["US$", "Amount"],
               ["Opening balance", f"{opening:,.2f}"],
               ["Collections received", f"{collections:,.2f}"],
               ["Transfers to the distribution account", f"({sweeps:,.2f})"],
               ["Closing balance", f"{closing:,.2f}"]], widths=[4.3, 1.7], total_row=True),
    ]
    build(path, story, "Statement of account, May 2026", f"Statement of account: {account}", SANS)


def build_statements(bramble: Path, northmoor: Path) -> None:
    build_statement("CB-COLL-40417", "Bramble Auto Receivables I LLC", 1_284_000, 9_652_300,
                    9_710_000, bramble / FILES["bramble"])
    build_statement("CB-COLL-38852", "Northmoor Motor Credit Trust", 942_500, 6_118_400,
                    6_090_000, northmoor / FILES["northmoor"])
