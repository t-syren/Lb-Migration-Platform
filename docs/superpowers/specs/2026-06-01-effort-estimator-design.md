# Effort Estimator — Design Spec
**Date:** 2026-06-01  
**Status:** Approved  
**Location:** `EffortEstimator/` (standalone, sibling to `Lb-Migration-Platform/`)

---

## 1. Overview

A standalone Streamlit app that ingests a Lakebridge analyzer Excel output, applies Syren's migration rate card, and produces a phased effort estimation. Matches SyrenBridge dark theme. Deployed independently as its own Databricks App or run locally.

---

## 2. Directory Structure

```
EffortEstimator/
├── app.py
├── requirements.txt
├── .streamlit/
│   └── config.toml           # Dark theme matching SyrenBridge
└── modules/
    ├── __init__.py
    ├── rate_card.py           # All 35+ dialect mappings (source of truth from screenshots)
    ├── analyzer_parser.py     # Reads Lakebridge Excel → InventoryResult
    ├── effort_calculator.py   # Applies rates → PhaseBreakdown
    └── report_generator.py    # InventoryResult + PhaseBreakdown → markdown string
```

---

## 3. Data Models

```python
# analyzer_parser.py
@dataclass
class InventoryResult:
    total_scripts: int
    total_loc: int
    total_statements: int
    total_ddls: int
    total_tables: int
    complexity: dict          # {"LOW": 81, "MEDIUM": 3, "HIGH": 1, "VERY_HIGH": 7}
    functions: dict           # {"TRUNC": 200, "CAST": 226, ...}
    special_patterns: list    # ["Correlated sub-query (11 scripts)", ...]
    source_file: str          # original filename

# effort_calculator.py
@dataclass
class PhaseBreakdown:
    phases: list[dict]        # [{"name": "...", "days": x, "notes": "..."}, ...]
    total_days: float
    total_weeks: float        # total_days / 5 / team_size (2 engineers assumed)
    code_conversion_days: float

@dataclass
class EstimationResult:
    scenario_label: str       # "With SyrenBridge" or "Manual"
    rates_used: dict          # {"LOW": 0.5, "MEDIUM": 1.0, ...}
    complexity_table: list    # [{"tier": "LOW", "count": 81, "rate": 0.5, "days": 40.5}, ...]
    breakdown: PhaseBreakdown
    person_day_cost: float | None
```

---

## 4. Rate Card (`rate_card.py`)

Single source of truth. Dict keyed by mapping name (e.g. `"Teradata > DBSQL"`). Each entry has:
- `source`, `target`, `type` (SQL / ETL / Workflow / Validation)
- `transpile_automation`: int % or `None`
- `reconcile_automation`: bool (all False for current mappings — reconciliation always manual)
- `rates_with_transpiler`: `{LOW, MEDIUM, COMPLEX, VERY_COMPLEX}` — applied when toggle is ON
- `rates_manual`: `{LOW, MEDIUM, COMPLEX, VERY_COMPLEX}` — applied when toggle is OFF

Every mapping has **both** rate sets. For mappings without a transpiler (manual-only), both sets are identical.

**Key rates extracted from Syren rate card screenshots:**

| Mapping | Transpile % | LOW | MED | COMPLEX | VERY COMPLEX |
|---|---|---|---|---|---|
| Teradata > DBSQL (with) | 60% | 0.5 | 1.0 | 2.0 | 4.0 |
| Teradata > DBSQL (manual) | — | 1.28 | 2.16 | 3.44 | 4.88 |
| Hive > DBSQL | — | 0.25 | 0.5 | 1.0 | 2.0 |
| AzureSynapse > DBSQL (with) | 60% | 0.5 | 1.0 | 2.0 | 4.0 |
| Snowflake > DBSQL | — | 0.5 | 1.0 | 2.0 | 4.0 |
| Cloudera (Impala) > DBSQL | — | 0.5 | 1.0 | 1.5 | 4.0 |
| EMR 3.0 > PySpark | — | 0.64 | 1.28 | 2.56 | 3.6 |
| Generic SQL (default) | — | 0.5 | 1.0 | 2.0 | 4.0 |
| Generic ETL | — | 1.3 | 2.5 | 3.7 | 5.2 |
| Most others (BigQuery, Oracle, Netezza, IBM DB2, etc.) | — | 1.28 | 2.16 | 3.44 | 4.88 |

Full list in implementation includes: ADF, Alteryx, Athena, AzureSynapse, BigQuery, Cloudera, Datastage, EMR 2.0/3.0, ETL_Workflows, Generic ETL/SQL/Validation/Workflow, Greenplum, Hive, IBM DB2, Informatica (Big Data/PC/Cloud) × multiple targets, MS SQL Server, Netezza, Oracle, Snowflake, Synapse, Teradata.

---

## 5. Analyzer Parser (`analyzer_parser.py`)

Reads standard Lakebridge Excel output (openpyxl). Sheets used:
- `Summary` → total scripts, LOC, DDLs, tables
- `SQL Programs` → complexity distribution from column E (LOW/MEDIUM/HIGH/VERY_HIGH), filter `Included == YES`
- `Functions` → function name + call count
- `SQL Special Patterns` → special pattern descriptions

Returns `InventoryResult`. Fails gracefully if a sheet is missing (uses 0 for that field, logs warning).

Lakebridge complexity tier mapping → rate card tier:
- `LOW` → `LOW`
- `MEDIUM` → `MEDIUM`  
- `HIGH` → `COMPLEX`
- `VERY_HIGH` → `VERY_COMPLEX`

---

## 6. Effort Calculator (`effort_calculator.py`)

`calculate(inventory, mapping_key, use_transpiler, overrides, person_day_cost) → EstimationResult`

**Code conversion:** sum of `count × rate` for each complexity tier.

**Standard phases** (all configurable via `overrides` dict):

| Phase | Default Logic |
|---|---|
| Architecture & Planning | Fixed 10 days |
| Data Migration | `max(10, total_ddls × 0.06)` days |
| Code Conversion | Calculated from rate card × complexity counts |
| B&R Testing & Reconciliation | `code_conversion_days × 0.34` |
| Technical Reconciliation / UAT | `total_project_days × 0.065` |
| Production Deployment | Fixed 8 days |
| Program Management | `subtotal × 0.11` |

Timeline estimate: `total_days / 5 / 2` weeks (2 engineers, 5-day weeks). Rounded to nearest 0.5.

---

## 7. UI Layout (`app.py`)

### Header
Syren logo + title "Effort Estimator" + subtitle.

### Section 1 — Input (always visible)
- File uploader: Lakebridge analyzer Excel (.xlsx)
- Dialect dropdown: grouped by type (SQL / ETL / Workflow)
- Toggle: "Include SyrenBridge transpiler comparison"

### Section 2 — Configuration (st.expander, collapsed by default)
- Rate inputs: LOW / MEDIUM / COMPLEX / VERY COMPLEX (pre-filled from rate card for selected dialect)
- Phase overrides: Planning days, Testing % of conversion, PM % (number inputs)
- Person day cost: optional float input, placeholder "Leave blank to omit cost"
- "Reset to rate card defaults" button

### Section 3 — Results (shown after "Generate Estimate" button click)

**Toggle OFF (manual only):**
- 4 metric cards: Total Scripts | Total Effort | Timeline | Complexity split
- Complexity breakdown table
- Phase breakdown table (days per phase + % of total)
- Inventory summary (LOC, statements, DDLs, special patterns, top 10 functions)
- Download .md button

**Toggle ON (comparison mode):**
- Side-by-side metric cards: With SyrenBridge | Manual | Delta (days saved, weeks saved)
- Side-by-side complexity tables
- Side-by-side phase breakdown tables with delta column
- Inventory summary (shared — same regardless of scenario)
- Download .md button (report includes both scenarios + comparison table)

---

## 8. Report Generator (`report_generator.py`)

`generate(inventory, results, client_name, project_name) → str`

Single function. Returns complete markdown string. Structure mirrors the PLDT document we already built:
- Header (client, date, prepared by Syren)
- Executive Summary (with comparison table if two scenarios)
- Inventory & Complexity Distribution
- Rate Card Applied
- Scenario A (if transpiler) / Single Scenario (if manual)
- Scenario B (if transpiler)
- Side-by-side comparison (if transpiler)
- Phase Detail
- Risk Register (generic, based on special patterns from analyzer)
- Assumptions & Exclusions
- Timeline summary

Client name and project name are text inputs in the UI header area (optional, default "Client" / "Migration Project").

---

## 9. Non-Goals

- PDF export (out of scope)
- Saving/loading sessions
- Multi-file uploads
- Historical estimates comparison
- Integration with SyrenBridge transpiler run

---

## 10. Dependencies

```
streamlit
openpyxl
pandas
```

No PySpark, no sqlglot, no databricks-sdk needed.
