#!/usr/bin/env python3
"""
Build a normalized JSON dataset from the Terberg and Venti fault code CSV files.

- Reads fault_code_terberg.csv (UTF-8) and fault_code_venti.csv (Latin-1).
- Normalizes key fields so a frontend can search by code, SPN/FMI, or keywords.
- Writes a single JSON array (default: fault_codes.json).
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd


def clean(value: Any) -> Optional[str]:
    """Strip empty/NaN values to None and stringify the rest."""
    if value is None:
        return None
    if pd.isna(value):
        return None
    text = str(value).strip()
    return text or None


def normalize_alert_code(value: Any) -> Optional[str]:
    """Normalize numeric-like codes to a compact string (e.g., '5' instead of '5.0')."""
    raw = clean(value)
    if raw is None:
        return None
    try:
        num = float(raw)
        if num.is_integer():
            return str(int(num))
        return str(num)
    except ValueError:
        return raw


def join_labeled(fields: List[tuple[str, Optional[str]]]) -> Optional[str]:
    """Join labeled fields, skipping empties."""
    parts = [f"{label}: {val.strip()}" for label, val in fields if val and val.strip()]
    return "\n".join(parts) if parts else None


def load_terberg(path: Path) -> List[Dict[str, Any]]:
    df = pd.read_csv(path)
    records: List[Dict[str, Any]] = []
    for _, row in df.iterrows():
        spn = clean(row.get("SPN"))
        fmi = clean(row.get("FMI"))
        foutcode = clean(row.get("Foutcode"))
        description = clean(row.get("Omschrijving"))
        code_display = None
        if spn and fmi:
            code_display = f"SPN {spn} FMI {fmi}"
        elif spn:
            code_display = f"SPN {spn}"

        record = {
            "source": "terberg",
            "alert_code": None,
            "spn": spn,
            "fmi": fmi,
            "code_display": code_display or foutcode,
            "title": foutcode or code_display,
            "description": description,
            "severity": clean(row.get("Categorie")),
            "category": clean(row.get("Foutcodelijst")),
            "action": clean(row.get("Aangeraden actie")),
            "cause": clean(row.get("Oorzaak")),
            "effect": clean(row.get("Effect")),
            "notes": None,
            "color": None,
            "stop_reason": None,
            "rationale": None,
        }

        # Helpful for search UIs.
        search_terms = {t for t in [code_display, foutcode, description] if t}
        record["search_terms"] = sorted(search_terms)
        records.append(record)
    return records


def load_venti(path: Path) -> List[Dict[str, Any]]:
    df = pd.read_csv(path, encoding="latin1")
    records: List[Dict[str, Any]] = []
    for _, row in df.iterrows():
        alert_code = normalize_alert_code(row.get("Alert Fault code #"))
        title = clean(row.get("Alert message"))
        description = clean(row.get("Meaning"))
        action = join_labeled(
            [
                ("AVC Action", clean(row.get("AVC Action"))),
                ("Remote Operator Action", clean(row.get(" Remote Operator Action"))),
                ("Vehicle immediate response", clean(row.get("Vehicle immediate response"))),
                ("Ops Troubleshoot Guide", clean(row.get("Ops Troubleshoot Guide"))),
            ]
        )

        notes = join_labeled(
            [
                ("Notes", clean(row.get("Notes"))),
                ("Internal Comments", clean(row.get("Internal Comments"))),
            ]
        )

        record = {
            "source": "venti",
            "alert_code": alert_code,
            "spn": None,
            "fmi": None,
            "code_display": alert_code,
            "title": title or alert_code,
            "description": description,
            "severity": clean(row.get("Severity")),
            "category": clean(row.get("Categorization")),
            "action": action,
            "cause": clean(row.get("Associated Reasons")),
            "effect": clean(row.get("Vehicle immediate response")),
            "notes": notes,
            "color": clean(row.get("Color")),
            "stop_reason": clean(row.get("Stop Reason")),
            "rationale": clean(row.get("Rationale")),
        }

        search_terms = {
            t
            for t in [
                alert_code,
                title,
                description,
                record["cause"],
                record["category"],
            ]
            if t
        }
        record["search_terms"] = sorted(search_terms)
        records.append(record)
    return records


def build_dataset(terberg_path: Path, venti_path: Path) -> List[Dict[str, Any]]:
    data: List[Dict[str, Any]] = []
    data.extend(load_terberg(terberg_path))
    data.extend(load_venti(venti_path))
    return data


def main() -> None:
    parser = argparse.ArgumentParser(description="Normalize fault code CSVs into a JSON array.")
    parser.add_argument(
        "--terberg",
        default="fault codes/fault_code_terberg.csv",
        help="Path to Terberg CSV",
    )
    parser.add_argument(
        "--venti",
        default="fault codes/fault_code_venti.csv",
        help="Path to Venti CSV",
    )
    parser.add_argument("-o", "--output", default="fault_codes.json", help="Output JSON path")
    args = parser.parse_args()

    terberg_path = Path(args.terberg)
    venti_path = Path(args.venti)
    output_path = Path(args.output)

    dataset = build_dataset(terberg_path, venti_path)
    output_path.write_text(json.dumps(dataset, indent=2, ensure_ascii=True), encoding="utf-8")
    print(f"Wrote {len(dataset)} records to {output_path}")


if __name__ == "__main__":
    main()
