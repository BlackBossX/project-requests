#!/usr/bin/env python3
"""
SCSSA Excel Report Generator
Downloads requests/projects.csv from the repo via GitHub API,
converts it to a formatted .xlsx file, and writes it locally
so the workflow can upload it as a downloadable artifact.
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
    from openpyxl.styles import (
        Alignment,
        Border,
        Font,
        PatternFill,
        Side,
    )
    from openpyxl.utils import get_column_letter
except ImportError:
    print("Error: openpyxl is not installed. Run: pip install openpyxl", file=sys.stderr)
    sys.exit(1)

CSV_PATH = "requests/projects.csv"
XLSX_PATH = "requests/projects.xlsx"

# ── Colour palette ───────────────────────────────────────────────────────────
HEADER_FILL  = PatternFill("solid", fgColor="1F3864")   # dark navy
GROUP_FILL   = PatternFill("solid", fgColor="D6E4F0")   # light blue (even rows)
ACCENT_FILL  = PatternFill("solid", fgColor="EBF5FB")   # very light blue (odd rows)
HEADER_FONT  = Font(name="Calibri", bold=True, color="FFFFFF", size=11)
BODY_FONT    = Font(name="Calibri", size=10)
THIN = Side(style="thin", color="B0BEC5")
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)

# Column widths (characters)
COL_WIDTHS = {
    "Group No":            10,
    "Repo Name":           38,
    "Repo Link":           55,
    "Project Title":       22,
    "Module":              10,
    "Batch":               8,
    "Member1 Student No":  18,
    "Member1 Name":        20,
    "Member1 GitHub":      18,
    "Member2 Student No":  18,
    "Member2 Name":        20,
    "Member2 GitHub":      18,
    "Member3 Student No":  18,
    "Member3 Name":        20,
    "Member3 GitHub":      18,
    "Member4 Student No":  18,
    "Member4 Name":        20,
    "Member4 GitHub":      18,
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


def fetch_csv(repo_full_name: str, token: str) -> list[dict]:
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
    return list(reader), reader.fieldnames


def build_xlsx(rows: list[dict], headers: list[str]):
    """Builds a formatted openpyxl workbook from the CSV rows."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Project Proposals"

    # ── Freeze pane below header ──────────────────────────────────────────────
    ws.freeze_panes = "A2"

    # ── Header row ───────────────────────────────────────────────────────────
    for col_idx, col_name in enumerate(headers, start=1):
        cell = ws.cell(row=1, column=col_idx, value=col_name)
        cell.font = HEADER_FONT
        cell.fill = HEADER_FILL
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border = BORDER
    ws.row_dimensions[1].height = 30

    # ── Data rows ────────────────────────────────────────────────────────────
    for row_idx, row in enumerate(rows, start=2):
        fill = GROUP_FILL if row_idx % 2 == 0 else ACCENT_FILL
        for col_idx, col_name in enumerate(headers, start=1):
            value = row.get(col_name, "")

            # Make Repo Link a clickable hyperlink
            if col_name == "Repo Link" and value.startswith("http"):
                cell = ws.cell(row=row_idx, column=col_idx, value=value)
                cell.hyperlink = value
                cell.font = Font(name="Calibri", size=10, color="0563C1", underline="single")
            else:
                cell = ws.cell(row=row_idx, column=col_idx, value=value)
                cell.font = BODY_FONT

            cell.fill = fill
            cell.border = BORDER
            cell.alignment = Alignment(vertical="center", wrap_text=False)

    # ── Column widths ─────────────────────────────────────────────────────────
    for col_idx, col_name in enumerate(headers, start=1):
        width = COL_WIDTHS.get(col_name, 15)
        ws.column_dimensions[get_column_letter(col_idx)].width = width

    # ── Auto-filter on header ─────────────────────────────────────────────────
    ws.auto_filter.ref = ws.dimensions

    return wb


def main():
    token = os.environ.get("ISSUE_TOKEN") or os.environ.get("GITHUB_TOKEN", "")
    repo_full_name = os.environ.get("REPO_FULL_NAME", "")

    if not token or not repo_full_name:
        print("Error: ISSUE_TOKEN and REPO_FULL_NAME must be set.", file=sys.stderr)
        sys.exit(1)

    print(f"Fetching '{CSV_PATH}' from '{repo_full_name}'...")
    rows, headers = fetch_csv(repo_full_name, token)

    if not rows:
        print("CSV exists but has no data rows. Generating empty report with headers only.")

    print(f"Building Excel workbook ({len(rows)} group(s))...")
    wb = build_xlsx(rows, list(headers))

    os.makedirs(os.path.dirname(XLSX_PATH), exist_ok=True)
    wb.save(XLSX_PATH)
    print(f"Excel report saved: {XLSX_PATH}")


if __name__ == "__main__":
    main()
