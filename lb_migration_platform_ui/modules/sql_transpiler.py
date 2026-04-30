"""Hive SQL → Databricks SQL transpiler utilities."""
import logging
import re
from typing import Dict, Tuple

import sqlglot
import sqlglot.errors
from sqlglot import parse_one, exp
from pathlib import Path
from modules.llm_converter import LLMConverter

logger = logging.getLogger(__name__)

# Hive-specific clauses that have no Spark SQL equivalent
_STRIP_PATTERNS = [
    r"ROW\s+FORMAT\s+(?:DELIMITED(?:\s+FIELDS\s+TERMINATED\s+BY\s+'[^']*')?(?:\s+LINES\s+TERMINATED\s+BY\s+'[^']*')?|SERDE\s+'[^']*'(?:\s+WITH\s+SERDEPROPERTIES\s*\([^)]*\))?)",
    r"STORED\s+AS\s+(?:TEXTFILE|ORC|PARQUET|AVRO|SEQUENCEFILE|RCFILE)",
    r"TBLPROPERTIES\s*\([^)]*\)",
    r"LOCATION\s+'hdfs://[^']*'",
]

def split_sql_statements(sql: str):
    statements = []
    current = []

    in_single = False
    in_double = False
    in_backtick = False
    in_line_comment = False
    in_block_comment = False

    line_number = 1
    start_line = 1

    i = 0

    while i < len(sql):
        char = sql[i]
        next_char = sql[i + 1] if i + 1 < len(sql) else ""

        # ---- Track line number ----
        if char == "\n":
            line_number += 1

        # ----- Handle comment START -----
        if not (in_single or in_double or in_backtick):
            if not in_block_comment and not in_line_comment:
                if char == "-" and next_char == "-":
                    in_line_comment = True
                    i += 2
                    continue
                elif char == "/" and next_char == "*":
                    in_block_comment = True
                    i += 2
                    continue

        # ----- Handle comment END -----
        if in_line_comment:
            if char == "\n":
                in_line_comment = False
            i += 1
            continue

        if in_block_comment:
            if char == "*" and next_char == "/":
                in_block_comment = False
                i += 2
            else:
                i += 1
            continue

        # ----- Handle quotes -----
        if char == "'" and not in_double and not in_backtick:
            in_single = not in_single
        elif char == '"' and not in_single and not in_backtick:
            in_double = not in_double
        elif char == "`" and not in_single and not in_double:
            in_backtick = not in_backtick

        # ----- Split on semicolon -----
        if char == ";" and not (in_single or in_double or in_backtick):
            stmt = "".join(current).strip()
            if stmt:
                statements.append((stmt, start_line))
            current = []
            start_line = line_number  # next statement starts here
        else:
            current.append(char)

        i += 1

    # ----- Last statement -----
    last = "".join(current).strip()
    if last:
        statements.append((last, start_line))

    return statements

# ==========================================
# 🔥 VARIABLE HANDLER (CLEAN VERSION)
# ==========================================
def handle_hive_variables(content: str):

    # -------------------------------
    # 1. Extract inline variables
    # ${var}, ${hivevar:var}
    # -------------------------------
    vars_inline = re.findall(r"\$\{(?:hivevar:)?(\w+)\}",content,flags=re.IGNORECASE)

    # -------------------------------
    # 2. Extract SET statements
    # -------------------------------
    # vars_set_raw = re.findall(r"SET\s+([\w\.]+)\s*=\s*([^;]+)",content,flags=re.IGNORECASE)
    # -------------------------------
    # 2. Extract SET statements (NORMAL + hivevar)
    # -------------------------------
    vars_set_raw = re.findall(
        r"SET\s+((?:hivevar:)?[\w\.]+)\s*=\s*([^;]+)",
        content,
        flags=re.IGNORECASE
    )
    # -------------------------------
    # 3. Filter ONLY real variables
    # remove engine configs
    # -------------------------------
    CONFIG_PREFIXES = ("spark.", "hive.", "mapreduce.")
    vars_set = []
    for name, val in vars_set_raw:        
        # 🔥 Normalize hivevar
        if name.lower().startswith("hivevar:"):
            name = name.split(":", 1)[1]   # hivevar:region → region

        # ❌ Skip configs
        if "." in name or name.lower().startswith(CONFIG_PREFIXES):
            continue

        vars_set.append((name, val.strip()))


    # -------------------------------
    # 4. Collect variable names
    # -------------------------------
    var_names = list(dict.fromkeys(vars_inline + [v[0] for v in vars_set]))

    # -------------------------------
    # 5. Extract variable values
    # -------------------------------
    var_values = {}

    for name, val in vars_set:
        val = val.strip()

        # Fix date-like values (prevent 2025 - 01 - 01 bug)
        if re.match(r"\d{4}-\d{2}-\d{2}", val):
            val = f"'{val}'"

        # Quote if not already quoted
        if not val.startswith("'"):
            val = f"'{val.replace(chr(39), chr(39) + chr(39))}'"

        var_values[name] = val

    # -------------------------------
    # 6. Generate SQL variable declarations
    # -------------------------------
    declared_vars = []

    for v in var_names:
        value = var_values.get(v, "'UNKNOWN'")
        declared_vars.append(
            f"DECLARE OR REPLACE VARIABLE `{v}` STRING DEFAULT {value};"
        )

    # -------------------------------
    # 7. REMOVE SET statements completely
    # -------------------------------
    content = re.sub(
        r"SET\s+[\w\.:]+\s*=\s*[^;]+;",
        "",
        content,
        flags=re.IGNORECASE
    )

    # -------------------------------
    # 8. Normalize variables in SQL
    # -------------------------------

    # ${hivevar:x} → x
    content = re.sub(
        r"\$\{hivevar:(\w+)\}",
        r"\1",
        content,
        flags=re.IGNORECASE
    )

    # ${x} → x
    content = re.sub(
        r"\$\{(\w+)\}",
        r"\1",
        content
    )

    # :x → x
    content = re.sub(
        r":(\w+)",
        r"\1",
        content
    )

    # -------------------------------
    # 9. Fix quoted variables (important)
    # '${run_dt}' → run_dt
    # -------------------------------
    # Only unquote known variable names
    for var_name in var_names:
        content = re.sub(rf"'{re.escape(var_name)}'", var_name, content)
    # content = re.sub(r"'(\w+)'",r"\1",content)

    # -------------------------------
    # 10. Cleanup formatting
    # -------------------------------
    content = re.sub(r"\n\s*\n+", "\n\n", content)

    return content.strip(), declared_vars


def _split_top_level_csv(value: str) -> list[str]:
    parts = []
    current = []
    paren_depth = 0
    angle_depth = 0
    in_single = False
    in_double = False
    in_backtick = False

    for char in value:
        if char == "'" and not in_double and not in_backtick:
            in_single = not in_single
        elif char == '"' and not in_single and not in_backtick:
            in_double = not in_double
        elif char == "`" and not in_single and not in_double:
            in_backtick = not in_backtick
        elif not (in_single or in_double or in_backtick):
            if char == "(":
                paren_depth += 1
            elif char == ")" and paren_depth:
                paren_depth -= 1
            elif char == "<":
                angle_depth += 1
            elif char == ">" and angle_depth:
                angle_depth -= 1

        if char == "," and paren_depth == 0 and angle_depth == 0 and not (in_single or in_double or in_backtick):
            part = "".join(current).strip()
            if part:
                parts.append(part)
            current = []
        else:
            current.append(char)

    part = "".join(current).strip()
    if part:
        parts.append(part)
    return parts


def _partition_column_names(stmt: str) -> set[str]:
    match = re.search(r"\bPARTITIONED\s+BY\s*\((.*?)\)", stmt, re.I | re.S)
    if not match:
        return set()

    names = set()
    for col_def in _split_top_level_csv(match.group(1)):
        name_match = re.match(r"`?([A-Za-z_][\w]*)`?", col_def.strip())
        if name_match:
            names.add(name_match.group(1).lower())
    return names


def _remove_partition_columns_from_schema(stmt: str) -> str:
    partition_cols = _partition_column_names(stmt)
    if not partition_cols:
        return stmt

    match = re.search(r"(CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?[\w\.]+)\s*\(", stmt, re.I)
    if not match:
        return stmt

    open_pos = match.end() - 1
    depth = 0
    close_pos = None
    for pos in range(open_pos, len(stmt)):
        char = stmt[pos]
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                close_pos = pos
                break

    if close_pos is None:
        return stmt

    schema = stmt[open_pos + 1:close_pos]
    columns = _split_top_level_csv(schema)
    kept_columns = []
    removed = False
    for col_def in columns:
        name_match = re.match(r"`?([A-Za-z_][\w]*)`?", col_def.strip())
        if name_match and name_match.group(1).lower() in partition_cols:
            removed = True
            continue
        kept_columns.append(col_def)

    if not removed:
        return stmt

    new_schema = ",\n    ".join(kept_columns)
    return f"{stmt[:open_pos + 1]}\n    {new_schema}\n{stmt[close_pos:]}"


def create_table_handler(stmt: str, location: str|None = None) -> str:
    original_stmt = stmt
    # Process only CREATE TABLE
    if not re.search(r"CREATE\s+(EXTERNAL\s+)?TABLE", stmt, re.I):
        return stmt

    is_external = bool(re.search(r"CREATE\s+EXTERNAL\s+TABLE", stmt, re.I))

    # 1. Normalize EXTERNAL → TABLE
    stmt = re.sub(r"CREATE\s+EXTERNAL\s+TABLE", "CREATE TABLE", stmt, flags=re.I)

    # 2. Remove existing USING / LOCATION (clean state)
    stmt = re.sub(r"\bUSING\s+DELTA\b", "", stmt, flags=re.I)
    stmt = re.sub(r"\bLOCATION\s+'[^']+'", "", stmt, flags=re.I)
    stmt = _remove_partition_columns_from_schema(stmt)

    # -----------------------------------
    # 3. Detect CTAS
    # -----------------------------------
    is_ctas = bool(re.search(r"\bAS\s+SELECT\b", stmt, re.I))

    # -----------------------------------
    # 4. CTAS handling
    # -----------------------------------
    if is_ctas:
        # Remove schema ONLY if directly after table name
        stmt = re.sub(
            r"(CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?[\w\.]+)\s*\([^)]*\)",
            r"\1",
            stmt,
            count=1,
            flags=re.I
        )

        # Add USING DELTA before AS
        stmt = re.sub(
            r"(CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?[\w\.]+)",
            r"\1\nUSING DELTA",
            stmt,
            flags=re.I
        )

        stmt = re.sub(r"USING DELTA\s*AS", "USING DELTA\nAS", stmt, flags=re.I)

    # -----------------------------------
    # 5. Normal CREATE TABLE
    # -----------------------------------
    else:
        if "USING DELTA" not in stmt.upper():
            stmt = re.sub(
                r"\)\s*(?=(COMMENT|PARTITIONED BY|$))",
                r")\nUSING DELTA\n",
                stmt,
                count=1,
                flags=re.I
            )

    # -----------------------------------
    # 6. LOCATION handling (single source)
    # -----------------------------------
    stmt = stmt.rstrip().rstrip(";")

    if location:
        location_clean = location.strip().strip("'").strip('"')
        if not re.search(
            rf"LOCATION\s+['\"]{re.escape(location_clean)}['\"]",
            stmt,
            re.IGNORECASE
        ):
            stmt += f"\nLOCATION '{location_clean}'"

    # -----------------------------------
    # 7. Ensure USING exists if LOCATION exists
    # -----------------------------------
    if "LOCATION" in stmt.upper() and "USING DELTA" not in stmt.upper():
        stmt = stmt.replace("LOCATION", "USING DELTA\nLOCATION")

    # -----------------------------------
    # 8. EXTERNAL table enforcement (force correct format)
    # -----------------------------------
    if is_external:
        stmt = re.sub(r"\bUSING\s+DELTA\b", "", stmt, flags=re.I)
        stmt = re.sub(r"\bLOCATION\s+'[^']+'", "", stmt, flags=re.I)

        stmt = stmt.rstrip().rstrip(";")

        if location:
            stmt += f"\nUSING DELTA\nLOCATION '{location}'"
        else:
            stmt += "\nUSING DELTA"

    # -----------------------------------
    # 9. Ensure correct ordering
    # -----------------------------------
    stmt = re.sub(
        r"LOCATION\s+('[^']+')\s+USING DELTA",
        r"USING DELTA\nLOCATION \1",
        stmt,
        flags=re.I
    )

    # -----------------------------------
    # 10. Cleanup formatting
    # -----------------------------------
    stmt = re.sub(r"\n{2,}", "\n", stmt).strip()

    # -----------------------------------
    # 11. Safety fallback
    # -----------------------------------
    if not stmt:
        return original_stmt

    return stmt


def add_global_issue(issues, category, message, pattern, content, severity="WARNING"):
    lines = []
    for i, line in enumerate(content.splitlines(), start=1):
        if re.search(pattern, line, re.IGNORECASE):
            lines.append(i)

    issues.append({
        "category": category,
        "severity": severity,
        "message": message,
        "statement": "GLOBAL",
        "lines": lines,      # 🔥 multiple lines
        "count": len(lines),
        "pattern": pattern
    })

def add_statement_issue(issues, category, message, stmt, line_no, stmt_index, severity="WARNING"):
    issues.append({
        "category": category,
        "severity": severity,
        "message": message,
        "statement": stmt.strip(),
        "line": line_no,
        "idx": stmt_index
    })

def run_hive_transpiler(
    src_dir: str,
    out_dir: str,
    err_file: str,
    target: str,
    catalog: str = "",
    schema: str = "",
    llm_endpoint=None,
    llm_api_key=None,
) -> tuple[bool, str, str]:

    import sqlglot
    import re
    from pathlib import Path

    src_root = Path(src_dir)
    out_root = Path(out_dir)
    hive_exts = {".hql", ".hive", ".sql", ".ddl", ".dml"}

    errors = []
    log_lines = []
    processed = 0
    generated = 0
    llm_files_attempted = 0
    llm_statements_replaced = 0
    llm_failures = 0

    TRANSFORM_RULES = [
        (r"\bNVL\s*\(", "COALESCE("),
        # (r"\bFROM_UNIXTIME\s*\(", "TIMESTAMP_SECONDS("),
        # 1. TWO-ARG version (must come first)
        (r"\bFROM_UNIXTIME\s*\(\s*([^,]+?)\s*,\s*([^)]+?)\s*\)",
            r"DATE_FORMAT(TIMESTAMP_SECONDS(\1), \2)"),
        (r"\bFROM_UNIXTIME\s*\(\s*([^)]+?)\s*\)",r"TIMESTAMP_SECONDS(\1)"),
        (r"\bUNIX_TIMESTAMP\s*\(\s*\)", "CURRENT_TIMESTAMP()"),
        # (r"LATERAL\s+VIEW\s+EXPLODE\s*\(([^)]+)\)\s+\w+\s+AS\s+(\w+)", r", explode(\1) AS \2"),
        (r"\bDISTRIBUTE\s+BY\s+[\w,\s]+", ""),
        (r"\bSORT\s+BY\s+[\w,\s]+", ""),
        # (r"`([^`]*)`", r"\1"), # Remove backticks from identifiers 
        (r"/\*\+\s*MAPJOIN\((.*?)\)\s*\*/", r"/*+ BROADCAST(\1) */"),
    ]

    STRIP_PATTERNS = [
        r"ROW\s+FORMAT\s+DELIMITED.*?(?=\)|$)",
        r"ROW\s+FORMAT\s+SERDE\s+'[^']*'.*?(?=\)|$)",
        r"STORED\s+AS\s+\w+",
        r"TBLPROPERTIES\s*\([^)]*\)",
        # r"LOCATION\s+'hdfs://[^']*'",
        r"CLUSTERED\s+BY\s*\([^)]*\)\s+INTO\s+\d+\s+BUCKETS",
        r"SORTED\s+BY\s*\([^)]*\)",
        r"SKEWED\s+BY\s*\([^)]*\)\s+ON\s*\([^)]*\).*?",
        r"INPUTFORMAT\s+'[^']*'",
        r"OUTPUTFORMAT\s+'[^']*'",
    ]

    def is_valid_sql(stmt: str) -> bool:
        try:
            sqlglot.parse_one(stmt)
            return True
        except Exception:
            return False  # just ensure not empty
    for src_file in sorted(src_root.rglob("*")):
        if not src_file.is_file() or src_file.suffix.lower() not in hive_exts:
            continue

        processed += 1
        rel_path = src_file.relative_to(src_root)

        try:
            content = src_file.read_text(encoding="utf-8", errors="replace")
        except Exception as exc:
            errors.append(f"{rel_path}: read error — {exc}")
            continue

        issues = []

        # ===============================
        # 🔥 PRE-PROCESSING on whole content  (BEFORE splitting)
        # ===============================
        
        # --- UDF JAR detection ---
        if re.search(r"\bADD\s+JAR\b", content, re.IGNORECASE):
            add_global_issue(
                issues,
                category="UDF",
                severity="BLOCKER",
                message="UDF JAR detected — not supported in Databricks",
                pattern=r"\bADD\s+JAR\b",
                content=content
            )

        # --- TEMP FUNCTION detection ---
        if re.search(r"\bCREATE\s+TEMPORARY\s+FUNCTION\b", content, re.IGNORECASE):
            add_global_issue(
                issues,
                category="UDF",
                severity="BLOCKER",
                message="Hive temporary UDF detected — requires manual rewrite",
                pattern=r"\bCREATE\s+TEMPORARY\s+FUNCTION\b",
                content=content
            )

        # --- Dynamic variables ---
        if re.search(r"\$\{.*?\}", content):
            add_global_issue(
                issues,
                category="VARIABLE",
                severity="WARNING",
                message="Dynamic variables detected — manual review required",
                pattern=r"\$\{.*?\}",
                content=content
            )
        # Extract hive variables,remove set engine configs and generate declarations
        content, declared_vars = handle_hive_variables(content)

        # Remove UDF definitions
        content = re.sub(r"\bADD\s+JAR\s+[^;]+;?", "", content, flags=re.IGNORECASE)
        content = re.sub(r"CREATE\s+TEMPORARY\s+FUNCTION\s+[^;]+;?", "", content, flags=re.IGNORECASE)
        # Remove CLUSTERED BY ,SORTED BY clauses NOT SUPPORTED IN DATABRICKS
        content = re.sub(r"CLUSTERED\s+BY\s*\([^)]*\)\s+INTO\s+\d+\s+BUCKETS", "", content, flags=re.I)
       
        content = re.sub(r"SORTED\s+BY\s*\(.*?\)", "", content, flags=re.I)
        # Remove EXPLAIN plans (which can break parsing and are not needed in Databricks)
        content = re.sub(r"(?is)\bEXPLAIN\b.*?(;|$)", "", content, flags=re.I)

        # ===============================
        # 🔥 SQLGLOT + LLM (PRODUCTION SAFE)
        # ===============================
        raw_statements = split_sql_statements(content)

        indexed_statements = []
        converted_stmts = []

        llm = None
        if llm_endpoint and llm_api_key:
            llm = LLMConverter(api_key=llm_api_key, endpoint=llm_endpoint)
            log_lines.append(f"{rel_path}: LLM enhancement enabled")
        else:
            log_lines.append(f"{rel_path}: LLM enhancement skipped - credentials not configured")

        # ----------------------------------
        # 🥇 STEP 1 — Process statements + track idx
        # ----------------------------------
        location_map = {}
        for idx, (stmt, line_no) in enumerate(raw_statements):
            stmt_upper = stmt.upper()
            # 🔹 Track statement
            indexed_statements.append({"idx": idx, "original": stmt,"line": line_no})    

            match = re.search(r"LOCATION\s+'([^']+)'", stmt, re.I)
            if match:
                location_map[idx] = match.group(1)
            # 🔹 MSCK REPAIR → REFRESH
            if "MSCK REPAIR" in stmt_upper:
                table_match = re.search(r"MSCK\s+REPAIR\s+TABLE\s+(\w+)", stmt, re.I)
                if table_match:
                    table_name = table_match.group(1)

                    add_statement_issue(
                        issues,
                        category="HIVE_COMMAND",
                        severity="INFO",
                        message="MSCK REPAIR replaced with REFRESH TABLE",
                        stmt=stmt,
                        line_no=line_no,
                        stmt_index=idx
                    )

                    stmt = f"REFRESH TABLE {table_name}"

            # 🔹 MULTI INSERT (flag only, no continue)
            if (("INSERT INTO" in stmt_upper or "INSERT OVERWRITE" in stmt_upper)
                and stmt_upper.count("INSERT") > 1
                and "FROM" in stmt_upper):

                add_statement_issue(
                    issues,
                    category="MULTI_INSERT",
                    severity="BLOCKER",
                    message="Hive multi-insert not supported in Databricks",
                    stmt=stmt,
                    line_no=line_no,
                    stmt_index=idx
                )

            # LOAD DATA (unsupported)
            if re.search(r"\bLOAD\s+DATA\b", stmt_upper):
                add_statement_issue(
                    issues,
                    category="UNSUPPORTED",
                    severity="BLOCKER",
                    message="LOAD DATA not supported in Databricks",
                    stmt=stmt,
                    line_no=line_no,
                    stmt_index=idx
                )

            # 🔹 SQLGLOT transpile
            try:
                out = sqlglot.transpile(
                    stmt,
                    read="hive",
                    write="databricks",
                    pretty=True
                )

                final_sql = next((s for s in out if s.strip()), stmt)

            except Exception as e:
                add_statement_issue(
                    issues,
                    category="PARSE_ERROR",
                    severity="ERROR",
                    message=f"Parse failed: {stmt[:80]} → {e}",
                    stmt=stmt,
                    line_no=line_no,
                    stmt_index=idx
                )
                final_sql = stmt

            converted_stmts.append({
                "idx": idx,
                "sql": final_sql
            })


        # ----------------------------------
        # 🥇 STEP 2 — CLEANING (preserve idx)
        # ----------------------------------
        cleaned_stmts = []

        for obj in converted_stmts:
            idx = obj["idx"]
            stmt = obj["sql"]

            cleaned = stmt

            #  CREATE TABLE FIX (ROBUST)  
            stmt_upper = cleaned.upper()
            cleaned = create_table_handler(cleaned,location=location_map.get(idx))

            # ANALYZE fix
            cleaned = re.sub(
                r"ANALYZE\s+TABLE\s+(\w+)\s+COMPUTE\s+STATISTICS\s+FOR\s+COLUMNS",
                r"ANALYZE TABLE \1 COMPUTE STATISTICS FOR ALL COLUMNS",
                cleaned,
                flags=re.IGNORECASE | re.DOTALL
            )

            # Apply transforms
            for pattern, r in TRANSFORM_RULES:
                cleaned = re.sub(pattern, r, cleaned, flags=re.IGNORECASE)

            # Strip Hive clauses
            for pattern in STRIP_PATTERNS:
                cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE | re.DOTALL)

            original_line = indexed_statements[idx]["line"] if idx < len(indexed_statements) else "unknown"
            stmt_upper = cleaned.upper()
            if "CREATE TABLE" in stmt_upper:
                if "EXTERNAL" in stmt.upper():
                    add_statement_issue(
                        issues,
                        category="DDL_UNSUPPORTED",
                        severity="INFO",
                        message="External table converted to Delta — verify data location and format",
                        stmt=stmt,
                        line_no=original_line,stmt_index=idx)

                elif "LOCATION" not in stmt_upper:
                    add_statement_issue(
                        issues,
                        category="DDL_REVIEW",
                        severity="INFO",
                        message="Table created without explicit LOCATION — verify storage behavior",
                        stmt=stmt,
                        line_no=original_line,stmt_index=idx
                    )

                elif "AS SELECT" in stmt_upper:
                    add_statement_issue(
                        issues,
                        category="CTAS_REVIEW",
                        severity="INFO",
                        message="CTAS converted to Delta — verify query correctness",
                        stmt=stmt,
                        line_no=original_line,stmt_index=idx
                    )
            # -------------------------------
            # Append final statement
            # -------------------------------
            cleaned_stmts.append({
                "idx": idx,
                "sql": cleaned.strip()
            })


        # ----------------------------------
        # 🥇 STEP 3 — LLM (ONLY PROBLEMATIC STATEMENTS)
        # ----------------------------------
        if llm and issues:

            log_lines.append(f"{rel_path}: LLM enhancement check found {len(issues)} issue(s)")

            # 🔹 Collect problematic stmt indexes
            problem_indexes = sorted({
                    i["idx"]
                    for i in issues
                    if isinstance(i, dict)
                    and i.get("idx") is not None
                    and i.get("statement") != "GLOBAL"
                    and i.get("severity") in ("ERROR", "BLOCKER")
                })

            if problem_indexes:
                llm_files_attempted += 1
                log_lines.append(
                    f"{rel_path}: calling LLM for {len(problem_indexes)} problematic statement(s)"
                )
                # 🔹 Build LLM input with markers
                llm_blocks = []
                for idx in problem_indexes:
                    stmt_sql = cleaned_stmts[idx]["sql"]
                    llm_blocks.append(f"-- STATEMENT_ID: {idx}\n{stmt_sql}")

                llm_input = "\n\n".join(llm_blocks)

                # 🔹 Filter issues for LLM
                filtered_issues = [
                    i for i in issues if i.get("idx") in problem_indexes
                ]
                try:
                    llm_output = llm.code_convert_llm(
                        code=llm_input,
                        prompt="lb_migration_platform_ui/modules/prompts/hivesql.yml",
                        issues=filtered_issues
                    )

                    # 🔹 Clean output
                    llm_output = llm_output.replace("```sql", "").replace("```", "").strip()

                    # 🔹 Parse output using markers
                    stmt_map = {}
                    current_id = None
                    buffer = []

                    for line in llm_output.splitlines():
                        marker = re.match(r"^\s*(?:--\s*)?STATEMENT_ID\s*:\s*(\d+)\s*$", line.strip(), re.I)
                        if marker:
                            if current_id is not None:
                                stmt_map[current_id] = "\n".join(buffer).strip()
                                buffer = []

                            current_id = int(marker.group(1))
                        else:
                            buffer.append(line)

                    if current_id is not None:
                        stmt_map[current_id] = "\n".join(buffer).strip()

                    # 🔹 Replace safely
                    if not stmt_map:
                        log_lines.append(
                            f"{rel_path}: LLM output was received but no STATEMENT_ID markers were found"
                        )

                    replaced = 0
                    skipped = 0
                    for idx, new_sql in stmt_map.items():

                        if idx >= len(cleaned_stmts):
                            skipped += 1
                            log_lines.append(
                                f"{rel_path}: LLM output skipped for unknown statement id {idx}"
                            )
                            continue

                        original_sql = cleaned_stmts[idx]["sql"]

                        if len(new_sql) < 10:
                            skipped += 1
                            log_lines.append(
                                f"{rel_path}: LLM output skipped for statement {idx} - output too short"
                            )
                            continue

                        if "INSERT" in original_sql.upper() and "INSERT" not in new_sql.upper():
                            skipped += 1
                            log_lines.append(
                                f"{rel_path}: LLM output skipped for statement {idx} - INSERT guard failed"
                            )
                            continue

                        if "PARTITION" in original_sql.upper() and "PARTITION" not in new_sql.upper():
                            skipped += 1
                            log_lines.append(
                                f"{rel_path}: LLM output skipped for statement {idx} - PARTITION guard failed"
                            )
                            continue

                        cleaned_stmts[idx]["sql"] = new_sql.strip()
                        replaced += 1

                    llm_statements_replaced += replaced
                    log_lines.append(
                        f"{rel_path}: LLM enhanced output applied to {replaced} statement(s), skipped {skipped}"
                    )

                except Exception as e:
                    llm_failures += 1
                    log_lines.append(f"{rel_path}: LLM enhancement failed - {e}")
                    logger.error(f"LLM failed: {e}")
            else:
                log_lines.append(
                    f"{rel_path}: LLM not called - no ERROR/BLOCKER statements found"
                )
        elif llm:
            log_lines.append(f"{rel_path}: LLM enhancement not required - no issues found")
        # ================================           
        # 🔥 OUTPUT 
        # ===============================
        if target == "SPARKSQL":
            out_ext = ".sql"
            lines = [f"-- Transpiled from HiveSQL | {src_file.name}", ""]

            if declared_vars:
                lines += declared_vars + [""]

            if catalog.strip():
                lines.append(f"USE CATALOG {catalog};")

            if schema.strip():
                lines.append(f"USE {schema};")

            for stmt in cleaned_stmts:
                sql = stmt["sql"].rstrip(";") + ";"
                lines.append(sql)

            if issues:
                lines.append("\n-- ⚠️ Issues:")
                for i in issues:
                    lines.append(f"-- {i}")

            out_content = "\n".join(lines)

        else:
            out_ext = ".py"
            lines = [f"# Transpiled from HiveSQL | {src_file.name}", ""
                "from pyspark.sql import SparkSession",
                "spark = SparkSession.builder.getOrCreate()",
                "",
                ]
            if catalog.strip():
                lines.append(f'spark.sql("""USE CATALOG {catalog};""")')

            if schema.strip():
                lines.append(f'spark.sql("""USE {schema};""")')

            for var in declared_vars:
                lines.append(f'spark.sql("""{var}""")')
                # lines.append(f'spark.conf.set("{var}", "{declared_vars[var].strip()}")')

            for stmt in cleaned_stmts:
                statement_parts = split_sql_statements(stmt["sql"])
                if not statement_parts:
                    statement_parts = [(stmt["sql"], 1)]

                for statement_sql, _line_no in statement_parts:
                    sql = statement_sql.strip().rstrip(";") + ";"
                    if sql == ";":
                        continue
                    lines.append(f'spark.sql("""{sql}""")')

            if issues:
                lines.append("\n# ---⚠️ Issues:")
                for each_issue in issues:
                    lines.append(f"# {each_issue}")

            out_content = "\n".join(lines)

        out_file = out_root / rel_path.with_suffix(out_ext)
        out_file.parent.mkdir(parents=True, exist_ok=True)

        try:
            out_file.write_text(out_content, encoding="utf-8")
            generated += 1
        except Exception as exc:
            errors.append(f"{rel_path}: write error — {exc}")

    if errors:
        Path(err_file).write_text("\n".join(errors), encoding="utf-8")

    summary = f"{processed} processed, {generated} generated"
    if llm_endpoint and llm_api_key:
        summary += (
            f"\nLLM enhancement: {llm_files_attempted} file(s) sent, "
            f"{llm_statements_replaced} statement(s) replaced"
        )
        if llm_failures:
            summary += f", {llm_failures} failure(s)"

    if log_lines:
        summary += "\n\nDetails:\n" + "\n".join(log_lines)

    return (
        generated > 0,
        summary,
        "\n".join(errors),
    )


