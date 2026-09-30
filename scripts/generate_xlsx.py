#!/usr/bin/env python3
"""
SCSSA Excel Report Generator
Downloads requests/projects.csv from the repo via GitHub API,
converts it to a formatted .xlsx file, and writes it locally
so the workflow can upload it as a downloadable artifact.

Excel layout: 1 row per group. Member Student Nos, Names, and
GitHub Usernames are stacked inside single cells (one per line).
"""

import base64
import csv
import io
import json
import os
import sys
import urllib.error
import urllib.request

try:
    import openpyxl
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.utils import get_column_letter
except ImportError:
    print("Error: openpyxl is not installed. Run: pip install openpyxl", file=sys.stderr)
    sys.exit(1)

CSV_PATH  = "requests/projects.csv"
XLSX_PATH = "requests/projects.xlsx"

# ── Colour palette ────────────────────────────────────────────────────────────
HEADER_FILL = PatternFill("solid", fgColor="1F3864")   # dark navy
EVEN_FILL   = PatternFill("solid", fgColor="D6E4F0")   # light blue
ODD_FILL    = PatternFill("solid", fgColor="EBF5FB")   # very light blue
HEADER_FONT = Font(name="Calibri", bold=True, color="FFFFFF", size=11)
BODY_FONT   = Font(name="Calibri", size=10)
LINK_FONT   = Font(name="Calibri", size=10, color="0563C1", underline="single")
THIN        = Side(style="thin", color="B0BEC5")
BORDER      = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)

# ── Excel columns (display order) ─────────────────────────────────────────────
# Consolidated view: member data stacked inside 3 cells per row
EXCEL_HEADERS = [
    "Group No",
    "Repo Name",
    "Repo Link",
    "Project Title",
    "Module",
    "Batch",
    "Student Numbers",   # all members' student nos, one per line
    "Names",             # all members' full names, one per line
    "GitHub Usernames",  # all members' GitHub handles, one per line
]

COL_WIDTHS = {
    "Group No":         10,
    "Repo Name":        38,
    "Repo Link":        52,
    "Project Title":    22,
    "Module":           10,
    "Batch":             8,
    "Student Numbers":  20,
    "Names":            24,
    "GitHub Usernames": 22,
}

# CSV columns that hold per-member data (in member order)
MEMBER_FIELDS = {
    "Student Numbers": ["Member1 Student No", "Member2 Student No",
                        "Member3 Student No", "Member4 Student No"],
    "Names":           ["Member1 Name",       "Member2 Name",
                        "Member3 Name",       "Member4 Name"],
    "GitHub Usernames":["Member1 GitHub",     "Member2 GitHub",
                        "Member3 GitHub",     "Member4 GitHub"],
}


def api_request(method: str, endpoint: str, token: str):
    url = f"https://api.github.com/{endpoint.lstrip('/')}"
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "scssa-xlsx-generator",
        "Authorization": f"Bearer {token}",
    }
    req = urllib.request.Request(url, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req) as resp:
            content = resp.read().decode("utf-8")
            return resp.status, json.loads(content) if content else {}
    except urllib.error.HTTPError as e:
        return e.code, {}
    except Exception as e:
        return 500, {"message": str(e)}


def fetch_csv(repo_full_name: str, token: str):
    """Fetches and parses projects.csv from the repo via GitHub API."""
    status, resp = api_request("GET", f"/repos/{repo_full_name}/contents/{CSV_PATH}", token)
    if status == 404:
        print(f"CSV not found at '{CSV_PATH}' — no Excel report to generate.", file=sys.stderr)
        sys.exit(0)
    if status != 200:
        print(f"Error fetching CSV ({status}): {resp}", file=sys.stderr)
        sys.exit(1)

    raw = base64.b64decode(resp["content"].replace("\n", "")).decode("utf-8")
    reader = csv.DictReader(io.StringIO(raw))
    return list(reader)


def consolidate_row(csv_row: dict) -> dict:
    """
    Converts a flat CSV row (18 columns) into a consolidated Excel row (9 columns).
    Member data is joined with newlines so each cell stacks values vertically.
    """
    def stack(fields):
        return "\n".join(
            csv_row.get(f, "").strip()
            for f in fields
            if csv_row.get(f, "").strip()
        )

    return {
        "Group No":         csv_row.get("Group No", ""),
        "Repo Name":        csv_row.get("Repo Name", ""),
        "Repo Link":        csv_row.get("Repo Link", ""),
        "Project Title":    csv_row.get("Project Title", ""),
        "Module":           csv_row.get("Module", ""),
        "Batch":            csv_row.get("Batch", ""),
        "Student Numbers":  stack(MEMBER_FIELDS["Student Numbers"]),
        "Names":            stack(MEMBER_FIELDS["Names"]),
        "GitHub Usernames": stack(MEMBER_FIELDS["GitHub Usernames"]),
    }


def build_xlsx(csv_rows: list):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Project Proposals"
    ws.freeze_panes = "A2"

    # ── Header row ────────────────────────────────────────────────────────────
    for col_idx, col_name in enumerate(EXCEL_HEADERS, start=1):
        cell = ws.cell(row=1, column=col_idx, value=col_name)
        cell.font      = HEADER_FONT
        cell.fill      = HEADER_FILL
        cell.border    = BORDER
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    ws.row_dimensions[1].height = 30

    # ── Data rows ─────────────────────────────────────────────────────────────
    for row_idx, csv_row in enumerate(csv_rows, start=2):
        row = consolidate_row(csv_row)
        fill = EVEN_FILL if row_idx % 2 == 0 else ODD_FILL

        # Determine row height based on how many members are stacked
        member_count = len([
            v for v in csv_row.get("Member1 Student No", "") +
                        csv_row.get("Member2 Student No", "") +
                        csv_row.get("Member3 Student No", "") +
                        csv_row.get("Member4 Student No", "")
            if v
        ])
        # Simple heuristic: count newlines in the stacked student numbers cell
        lines = row["Student Numbers"].count("\n") + 1
        ws.row_dimensions[row_idx].height = max(18, lines * 18)

        for col_idx, col_name in enumerate(EXCEL_HEADERS, start=1):
            value = row.get(col_name, "")

            if col_name == "Repo Link" and value.startswith("http"):
                cell = ws.cell(row=row_idx, column=col_idx, value=value)
                cell.hyperlink = value
                cell.font = LINK_FONT
            else:
                cell = ws.cell(row=row_idx, column=col_idx, value=value)
                cell.font = BODY_FONT

            cell.fill   = fill
            cell.border = BORDER

            # Stacked member cells: top-aligned + wrap
            if col_name in ("Student Numbers", "Names", "GitHub Usernames"):
                cell.alignment = Alignment(vertical="top", wrap_text=True)
            else:
                cell.alignment = Alignment(vertical="center", wrap_text=False)

    # ── Column widths & auto-filter ───────────────────────────────────────────
    for col_idx, col_name in enumerate(EXCEL_HEADERS, start=1):
        ws.column_dimensions[get_column_letter(col_idx)].width = COL_WIDTHS.get(col_name, 15)

    ws.auto_filter.ref = ws.dimensions
    return wb


def main():
    token           = os.environ.get("ISSUE_TOKEN") or os.environ.get("GITHUB_TOKEN", "")
    repo_full_name  = os.environ.get("REPO_FULL_NAME", "")

    if not token or not repo_full_name:
        print("Error: ISSUE_TOKEN and REPO_FULL_NAME must be set.", file=sys.stderr)
        sys.exit(1)

    print(f"Fetching '{CSV_PATH}' from '{repo_full_name}'...")
    rows = fetch_csv(repo_full_name, token)

    if not rows:
        print("CSV exists but has no data rows. Generating empty report with headers only.")

    print(f"Building Excel workbook ({len(rows)} group(s))...")
    wb = build_xlsx(rows)

    os.makedirs(os.path.dirname(XLSX_PATH), exist_ok=True)
    wb.save(XLSX_PATH)
    print(f"Excel report saved: {XLSX_PATH}")


if __name__ == "__main__":
    main()
