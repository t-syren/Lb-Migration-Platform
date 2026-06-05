"""Pytest test suite for modules/talend_converter.py.

conftest.py puts lb_migration_platform_ui/ on sys.path so that
`from modules.talend_converter import ...` resolves correctly.
"""
import html
import pytest
from modules.talend_converter import (
    parse_talend_job,
    generate_pyspark,
    convert_talend_file_set,
    _topo_sort,
    _db_type_from_component,
    _df,
    TalendComponent,
    TalendConnection,
)

# ── Minimal XML helpers ────────────────────────────────────────────────────────

def _make_node(comp_name: str, unique: str, params: dict = None, columns: list = None) -> str:
    param_xml = ""
    if params:
        for k, v in params.items():
            # XML-escape so that values containing quotes don't break the attribute
            param_xml += f'<elementParameter name="{k}" value="{html.escape(v)}"/>\n'
    col_xml = ""
    if columns:
        col_xml = '<metadata connector="FLOW">'
        for c in columns:
            col_xml += f'<column name="{c[0]}" type="{c[1]}"/>'
        col_xml += "</metadata>"
    return (
        f'<node componentName="{comp_name}">'
        f'<elementParameter name="UNIQUE_NAME" value="{unique}"/>'
        f"{param_xml}{col_xml}</node>"
    )


def _make_conn(source: str, target: str, ctype: str = "FLOW") -> str:
    return f'<connection source="{source}" target="{target}" connectorName="{ctype}" label="row"/>'


def _job(*nodes_and_conns: str) -> str:
    inner = "\n".join(nodes_and_conns)
    return f"<?xml version='1.0'?><talendfile>{inner}</talendfile>"


# ══════════════════════════════════════════════════════════════════════════════
# parse_talend_job
# ══════════════════════════════════════════════════════════════════════════════

class TestParseTalendJob:
    def test_basic_node_parsed(self):
        xml = _job(_make_node("tHiveInput", "tHiveInput_1", {"TABLE_NAME": '"schema.t"'}))
        comps, conns, warns = parse_talend_job(xml)
        assert "tHiveInput_1" in comps
        assert comps["tHiveInput_1"].component_name == "tHiveInput"

    def test_connection_parsed(self):
        xml = _job(
            _make_node("tHiveInput", "A"),
            _make_node("tHiveOutput", "B"),
            _make_conn("A", "B"),
        )
        _, conns, _ = parse_talend_job(xml)
        assert len(conns) == 1
        assert conns[0].source == "A"
        assert conns[0].target == "B"

    def test_column_schema_parsed(self):
        xml = _job(
            _make_node("tHiveInput", "n1", columns=[("id", "id_Integer"), ("name", "id_String")])
        )
        comps, _, _ = parse_talend_job(xml)
        cols = comps["n1"].columns
        assert len(cols) == 2
        assert cols[0].name == "id"
        assert cols[0].col_type == "id_Integer"

    def test_empty_xml_returns_warning(self):
        comps, _, warns = parse_talend_job("<talendfile/>")
        assert comps == {}
        assert len(warns) >= 1

    def test_malformed_xml_returns_warning(self):
        _, _, warns = parse_talend_job("<<<not xml")
        assert any("parse error" in w.lower() or "XML" in w for w in warns)

    def test_params_extracted(self):
        xml = _job(_make_node("tMysqlInput", "n1", {"HOST": '"db.example.com"', "PORT": '"3306"'}))
        comps, _, _ = parse_talend_job(xml)
        assert comps["n1"].params["HOST"] == '"db.example.com"'


# ══════════════════════════════════════════════════════════════════════════════
# _topo_sort
# ══════════════════════════════════════════════════════════════════════════════

class TestTopoSort:
    def _comp(self, name: str) -> TalendComponent:
        return TalendComponent(unique_name=name, component_name="tHiveInput")

    def test_linear_chain(self):
        comps = {n: self._comp(n) for n in ["A", "B", "C"]}
        conns = [
            TalendConnection("A", "B", "row"),
            TalendConnection("B", "C", "row"),
        ]
        order = _topo_sort(comps, conns)
        assert order.index("A") < order.index("B") < order.index("C")

    def test_no_connections_all_returned(self):
        comps = {n: self._comp(n) for n in ["X", "Y", "Z"]}
        order = _topo_sort(comps, [])
        assert set(order) == {"X", "Y", "Z"}

    def test_fan_out(self):
        comps = {n: self._comp(n) for n in ["src", "dst1", "dst2"]}
        conns = [
            TalendConnection("src", "dst1", "row"),
            TalendConnection("src", "dst2", "row"),
        ]
        order = _topo_sort(comps, conns)
        assert order.index("src") < order.index("dst1")
        assert order.index("src") < order.index("dst2")

    def test_fan_in(self):
        comps = {n: self._comp(n) for n in ["s1", "s2", "join"]}
        conns = [
            TalendConnection("s1", "join", "row"),
            TalendConnection("s2", "join", "row"),
        ]
        order = _topo_sort(comps, conns)
        assert order.index("s1") < order.index("join")
        assert order.index("s2") < order.index("join")


# ══════════════════════════════════════════════════════════════════════════════
# _db_type_from_component
# ══════════════════════════════════════════════════════════════════════════════

class TestDbTypeFromComponent:
    def _comp(self, name: str) -> TalendComponent:
        return TalendComponent(unique_name="n1", component_name=name)

    def test_mysql(self):
        assert _db_type_from_component(self._comp("tMysqlInput")) == "mysql"

    def test_oracle(self):
        assert _db_type_from_component(self._comp("tOracleInput")) == "oracle"

    def test_snowflake(self):
        assert _db_type_from_component(self._comp("tSnowflakeOutput")) == "snowflake"

    def test_mssql(self):
        assert _db_type_from_component(self._comp("tMSSqlInput")) == "mssql"

    def test_postgres(self):
        assert _db_type_from_component(self._comp("tPostgresqlInput")) == "postgresql"

    def test_redshift(self):
        assert _db_type_from_component(self._comp("tRedshiftOutput")) == "redshift"

    def test_teradata(self):
        assert _db_type_from_component(self._comp("tTeradataInput")) == "teradata"

    def test_db_type_param_fallback(self):
        comp = TalendComponent(
            unique_name="n1",
            component_name="tDBInput",
            params={"DB_TYPE": '"netezza"'},
        )
        assert _db_type_from_component(comp) == "netezza"


# ══════════════════════════════════════════════════════════════════════════════
# generate_pyspark — code generation
# ══════════════════════════════════════════════════════════════════════════════

class TestGeneratePyspark:
    def test_header_present(self):
        xml = _job(_make_node("tHiveInput", "n1", {"TABLE_NAME": '"t"'}))
        comps, conns, _ = parse_talend_job(xml)
        code, _ = generate_pyspark("myjob", comps, conns)
        assert "converted from Talend job: myjob" in code

    def test_spark_session_present(self):
        xml = _job(_make_node("tHiveInput", "n1", {"TABLE_NAME": '"t"'}))
        comps, conns, _ = parse_talend_job(xml)
        code, _ = generate_pyspark("j", comps, conns)
        assert "SparkSession.builder.getOrCreate()" in code

    def test_hive_input_generates_spark_table(self):
        xml = _job(_make_node("tHiveInput", "n1", {"TABLE_NAME": '"schema.t"'}))
        comps, conns, _ = parse_talend_job(xml)
        code, _ = generate_pyspark("j", comps, conns)
        assert "spark.table(" in code

    def test_hive_output_generates_save_as_table(self):
        xml = _job(
            _make_node("tHiveInput", "A", {"TABLE_NAME": '"src"'}),
            _make_node("tHiveOutput", "B", {"TABLE_NAME": '"dst"'}),
            _make_conn("A", "B"),
        )
        comps, conns, _ = parse_talend_job(xml)
        code, _ = generate_pyspark("j", comps, conns)
        assert "saveAsTable(" in code or 'format("delta")' in code

    def test_mysql_generates_jdbc_url(self):
        xml = _job(_make_node("tMysqlInput", "n1", {
            "HOST": '"db.example.com"', "PORT": '"3306"',
            "DATABASE": '"sales"', "USERNAME": '"u"', "PASSWORD": '"p"',
            "QUERY": '"SELECT * FROM t"',
        }))
        comps, conns, _ = parse_talend_job(xml)
        code, _ = generate_pyspark("j", comps, conns)
        assert "jdbc:mysql://db.example.com:3306/sales" in code

    def test_oracle_generates_oracle_jdbc_url(self):
        xml = _job(_make_node("tOracleInput", "n1", {
            "HOST": '"oracle.example.com"', "PORT": '"1521"',
            "DBNAME": '"ORCL"', "USERNAME": '"u"', "PASSWORD": '"p"',
            "QUERY": '"SELECT * FROM t"',
        }))
        comps, conns, _ = parse_talend_job(xml)
        code, _ = generate_pyspark("j", comps, conns)
        assert "jdbc:oracle:thin:@oracle.example.com" in code

    def test_csv_input_generates_read_csv(self):
        xml = _job(_make_node("tFileInputDelimited", "n1", {"FILENAME": '"/data/t.csv"'}))
        comps, conns, _ = parse_talend_job(xml)
        code, _ = generate_pyspark("j", comps, conns)
        assert '.format("csv")' in code

    def test_json_input_generates_read_json(self):
        xml = _job(_make_node("tFileInputJSON", "n1", {"FILENAME": '"/data/t.json"'}))
        comps, conns, _ = parse_talend_job(xml)
        code, _ = generate_pyspark("j", comps, conns)
        assert "spark.read.json(" in code

    def test_parquet_input_generates_read_parquet(self):
        xml = _job(_make_node("tFileInputParquet", "n1", {"FILENAME": '"/data/t.parquet"'}))
        comps, conns, _ = parse_talend_job(xml)
        code, _ = generate_pyspark("j", comps, conns)
        assert "spark.read.parquet(" in code

    def test_filter_row_generates_placeholder(self):
        xml = _job(
            _make_node("tHiveInput", "A", {"TABLE_NAME": '"t"'}),
            _make_node("tFilterRow", "B"),
            _make_conn("A", "B"),
        )
        comps, conns, _ = parse_talend_job(xml)
        code, _ = generate_pyspark("j", comps, conns)
        assert ".filter(" in code

    def test_sort_row_generates_order_by(self):
        xml = _job(
            _make_node("tHiveInput", "A", {"TABLE_NAME": '"t"'}),
            _make_node("tSortRow", "B"),
            _make_conn("A", "B"),
        )
        comps, conns, _ = parse_talend_job(xml)
        code, _ = generate_pyspark("j", comps, conns)
        assert ".orderBy()" in code

    def test_tmap_emits_warning(self):
        xml = _job(
            _make_node("tHiveInput", "A", {"TABLE_NAME": '"t"'}),
            _make_node("tMap", "B", {"MAPPING_TYPE": '"STANDARD"'}),
            _make_conn("A", "B"),
        )
        comps, conns, _ = parse_talend_job(xml)
        _, warns = generate_pyspark("j", comps, conns)
        assert any("tMap" in w for w in warns)

    def test_tmap_includes_column_select(self):
        xml = _job(
            _make_node("tHiveInput", "A", {"TABLE_NAME": '"t"'}),
            _make_node("tMap", "B", columns=[("id", "id_Integer"), ("name", "id_String")]),
            _make_conn("A", "B"),
        )
        comps, conns, _ = parse_talend_job(xml)
        code, _ = generate_pyspark("j", comps, conns)
        assert '"id"' in code and '"name"' in code

    def test_unite_generates_union_chain(self):
        xml = _job(
            _make_node("tHiveInput", "A", {"TABLE_NAME": '"t1"'}),
            _make_node("tHiveInput", "B", {"TABLE_NAME": '"t2"'}),
            _make_node("tUnite", "C"),
            _make_conn("A", "C"),
            _make_conn("B", "C"),
        )
        comps, conns, _ = parse_talend_job(xml)
        code, _ = generate_pyspark("j", comps, conns)
        assert ".union(" in code

    def test_unknown_component_generates_passthrough(self):
        xml = _job(_make_node("tSalesforceInput", "n1"))
        comps, conns, _ = parse_talend_job(xml)
        code, warns = generate_pyspark("j", comps, conns)
        assert "n1" in code
        assert any("not fully supported" in w for w in warns)

    def test_topo_order_respected_in_output(self):
        """Source must appear before sink in generated code."""
        xml = _job(
            _make_node("tHiveInput", "src", {"TABLE_NAME": '"t"'}),
            _make_node("tHiveOutput", "dst", {"TABLE_NAME": '"out"'}),
            _make_conn("src", "dst"),
        )
        comps, conns, _ = parse_talend_job(xml)
        code, _ = generate_pyspark("j", comps, conns)
        lines = code.splitlines()
        idx_src = next(i for i, l in enumerate(lines) if "# src:" in l)
        idx_dst = next(i for i, l in enumerate(lines) if "# dst:" in l)
        assert idx_src < idx_dst

    def test_df_variable_threaded_from_source(self):
        """Sink code must reference the source's df_ variable."""
        xml = _job(
            _make_node("tHiveInput", "src", {"TABLE_NAME": '"t"'}),
            _make_node("tHiveOutput", "dst", {"TABLE_NAME": '"out"'}),
            _make_conn("src", "dst"),
        )
        comps, conns, _ = parse_talend_job(xml)
        code, _ = generate_pyspark("j", comps, conns)
        assert "df_src" in code


# ══════════════════════════════════════════════════════════════════════════════
# convert_talend_file_set — public API end-to-end
# ══════════════════════════════════════════════════════════════════════════════

class TestConvertTalendFileSet:
    def test_single_file_produces_notebook(self):
        xml = _job(_make_node("tHiveInput", "n1", {"TABLE_NAME": '"t"'}))
        result = convert_talend_file_set({"job.item": xml})
        assert "job" in result["notebooks"]

    def test_multiple_files(self):
        xml = _job(_make_node("tHiveInput", "n1", {"TABLE_NAME": '"t"'}))
        result = convert_talend_file_set({"a.item": xml, "b.item": xml})
        assert len(result["notebooks"]) == 2

    def test_warnings_list_present(self):
        result = convert_talend_file_set({})
        assert isinstance(result["warnings"], list)

    def test_empty_input_no_notebooks(self):
        result = convert_talend_file_set({})
        assert result["notebooks"] == {}

    def test_malformed_xml_warning(self):
        result = convert_talend_file_set({"bad.item": "<<<not xml"})
        assert any("parse error" in w.lower() or "XML" in w for w in result["warnings"])
        assert result["notebooks"] == {}

    def test_empty_xml_warning(self):
        result = convert_talend_file_set({"empty.item": "<talendfile/>"})
        assert result["notebooks"] == {}
        assert len(result["warnings"]) >= 1

    def test_output_has_pyspark_header(self):
        xml = _job(_make_node("tHiveInput", "n1", {"TABLE_NAME": '"t"'}))
        result = convert_talend_file_set({"job.item": xml})
        code = result["notebooks"]["job"]
        assert "from pyspark.sql import SparkSession" in code

    def test_job_name_from_filename_stem(self):
        xml = _job(_make_node("tHiveInput", "n1", {"TABLE_NAME": '"t"'}))
        result = convert_talend_file_set({"MyETLJob.item": xml})
        assert "MyETLJob" in result["notebooks"]

    def test_sample_files_all_convert(self):
        """Run the 4 real sample .item files to guard against regressions."""
        from pathlib import Path
        sample_dir = Path(__file__).parent.parent / "files" / "sample_talend"
        if not sample_dir.exists():
            pytest.skip("sample_talend directory not found")
        files = {p.name: p.read_text() for p in sorted(sample_dir.glob("*.item"))}
        assert len(files) >= 4, "Expected at least 4 sample .item files"
        result = convert_talend_file_set(files)
        assert len(result["notebooks"]) == len(files), (
            f"Expected {len(files)} notebooks, got {len(result['notebooks'])}: "
            f"{result['warnings']}"
        )
