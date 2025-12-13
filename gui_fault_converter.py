#!/usr/bin/env python3
"""Simple GUI to inspect a CSV and convert Terberg/Venti fault codes to JSON."""
from __future__ import annotations

import json
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Any, Dict, List, Optional

import pandas as pd


# --- Shared helpers ---------------------------------------------------------
def clean(value: Any) -> Optional[str]:
    if value is None or pd.isna(value):
        return None
    text = str(value).strip()
    return text or None


def normalize_alert_code(value: Any) -> Optional[str]:
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
    parts = [f"{label}: {val}" for label, val in fields if val]
    return "\n".join(parts) if parts else None


def is_terberg(df: pd.DataFrame) -> bool:
    return {"SPN", "FMI", "Foutcode", "Omschrijving"}.issubset(df.columns)


def is_venti(df: pd.DataFrame) -> bool:
    return "Alert Fault code #" in df.columns


def normalize_terberg(df: pd.DataFrame) -> List[Dict[str, Any]]:
    records: List[Dict[str, Any]] = []
    for _, row in df.iterrows():
        spn = clean(row.get("SPN"))
        fmi = clean(row.get("FMI"))
        foutcode = clean(row.get("Foutcode"))
        description = clean(row.get("Omschrijving"))
        code_display = f"SPN {spn} FMI {fmi}" if spn and fmi else (f"SPN {spn}" if spn else None)
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
        search_terms = {t for t in [code_display, foutcode, description] if t}
        record["search_terms"] = sorted(search_terms)
        records.append(record)
    return records


def normalize_venti(df: pd.DataFrame) -> List[Dict[str, Any]]:
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
        search_terms = {t for t in [alert_code, title, description, record["cause"], record["category"]] if t}
        record["search_terms"] = sorted(search_terms)
        records.append(record)
    return records


def normalize_dataframe(df: pd.DataFrame) -> List[Dict[str, Any]]:
    if is_terberg(df):
        return normalize_terberg(df)
    if is_venti(df):
        return normalize_venti(df)
    raise ValueError("CSV type not recognized (expected Terberg or Venti columns).")


# --- GUI --------------------------------------------------------------------
class App(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Fault Code CSV -> JSON")
        self.geometry("1000x640")

        self.df: Optional[pd.DataFrame] = None
        self.current_path: Optional[Path] = None

        btn_frame = ttk.Frame(self)
        btn_frame.pack(fill="x", padx=8, pady=6)

        self.load_btn = ttk.Button(btn_frame, text="Select CSV", command=self.load_file)
        self.load_btn.pack(side="left")

        self.convert_btn = ttk.Button(btn_frame, text="Convert to JSON", command=self.convert, state="disabled")
        self.convert_btn.pack(side="left", padx=6)

        self.info_label = ttk.Label(self, text="No file loaded")
        self.info_label.pack(fill="x", padx=8, pady=4)

        # Table area
        table_frame = ttk.Frame(self)
        table_frame.pack(fill="both", expand=True, padx=8, pady=4)

        self.tree = ttk.Treeview(table_frame, show="headings")
        vsb = ttk.Scrollbar(table_frame, orient="vertical", command=self.tree.yview)
        hsb = ttk.Scrollbar(table_frame, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")
        table_frame.rowconfigure(0, weight=1)
        table_frame.columnconfigure(0, weight=1)

        # Summary box
        self.summary = tk.Text(self, height=8, wrap="word")
        self.summary.pack(fill="both", expand=False, padx=8, pady=4)
        self.summary.insert("1.0", "Load a CSV to preview first 200 rows and see a summary.")
        self.summary.config(state="disabled")

    def load_file(self) -> None:
        path_str = filedialog.askopenfilename(
            title="Select fault CSV",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
        )
        if not path_str:
            return
        path = Path(path_str)
        try:
            try:
                df = pd.read_csv(path)
            except UnicodeDecodeError:
                df = pd.read_csv(path, encoding="latin1")
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Error", f"Failed to read CSV: {exc}")
            return

        self.df = df
        self.current_path = path
        self.info_label.config(text=f"Loaded: {path.name} | rows: {len(df)} | cols: {len(df.columns)}")
        self.convert_btn.config(state="normal")
        self.populate_table(df)
        self.populate_summary(df)

    def populate_table(self, df: pd.DataFrame) -> None:
        self.tree.delete(*self.tree.get_children())
        self.tree["columns"] = list(df.columns)
        for col in df.columns:
            self.tree.heading(col, text=col)
            self.tree.column(col, width=120, anchor="w")
        for _, row in df.head(200).iterrows():
            self.tree.insert("", "end", values=[row.get(col) for col in df.columns])

    def populate_summary(self, df: pd.DataFrame) -> None:
        lines: List[str] = []
        lines.append(f"Rows: {len(df)}, Columns: {len(df.columns)}")
        col_lines = []
        for col in df.columns[:20]:  # limit in summary
            non_null = df[col].notna().mean() * 100
            col_lines.append(f"- {col}: non-null {non_null:.1f}% (unique {df[col].nunique(dropna=True)})")
        lines.append("Columns (first 20):")
        lines.extend(col_lines)
        self.summary.config(state="normal")
        self.summary.delete("1.0", "end")
        self.summary.insert("1.0", "\n".join(lines))
        self.summary.config(state="disabled")

    def convert(self) -> None:
        if self.df is None or self.current_path is None:
            return
        try:
            data = normalize_dataframe(self.df)
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Error", f"Conversion failed: {exc}")
            return

        output_path = self.current_path.with_suffix(".json")
        try:
            output_path.write_text(json.dumps(data, indent=2, ensure_ascii=True), encoding="utf-8")
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Error", f"Failed to write JSON: {exc}")
            return
        messagebox.showinfo("Success", f"Wrote {len(data)} records to {output_path.name}")


if __name__ == "__main__":
    App().mainloop()
