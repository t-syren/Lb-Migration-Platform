"""Tests for ssrs_converter module."""
import pytest
from lb_migration_platform_ui.modules.ssrs_converter import (
    parse_rdl,
    assessment_to_sql_notebook,
    convert_ssrs_file_set,
)

# ── Fixtures ──────────────────────────────────────────────────────────────────

_SIMPLE_RDL = """\
<?xml version="1.0" encoding="utf-8"?>
<Report xmlns="http://schemas.microsoft.com/sqlserver/reporting/2010/01/reportdefinition">
  <Name>SalesReport</Name>
  <DataSources>
    <DataSource Name="DS1">
      <ConnectionProperties>
        <DataProvider>SQL</DataProvider>
        <ConnectString>Data Source=myserver;Initial Catalog=SalesDB</ConnectString>
      </ConnectionProperties>
    </DataSource>
  </DataSources>
  <DataSets>
    <DataSet Name="Orders">
      <Query>
        <DataSourceName>DS1</DataSourceName>
        <CommandType>Text</CommandType>
        <CommandText>SELECT order_id, customer_id FROM orders WHERE order_date &gt; @start</CommandText>
        <QueryParameters>
          <QueryParameter Name="@start"/>
        </QueryParameters>
      </Query>
    </DataSet>
  </DataSets>
  <ReportParameters>
    <ReportParameter Name="start">
      <DataType>DateTime</DataType>
    </ReportParameter>
  </ReportParameters>
  <Body>
    <ReportItems>
      <Tablix Name="Table1">
        <DataSetName>Orders</DataSetName>
      </Tablix>
    </ReportItems>
  </Body>
</Report>"""

_SPROC_RDL = """\
<?xml version="1.0" encoding="utf-8"?>
<Report xmlns="http://schemas.microsoft.com/sqlserver/reporting/2010/01/reportdefinition">
  <Name>ProcReport</Name>
  <DataSets>
    <DataSet Name="Summary">
      <Query>
        <CommandType>StoredProcedure</CommandType>
        <CommandText>sp_get_summary</CommandText>
      </Query>
    </DataSet>
  </DataSets>
</Report>"""

_EMPTY_RDL = """\
<?xml version="1.0" encoding="utf-8"?>
<Report xmlns="http://schemas.microsoft.com/sqlserver/reporting/2010/01/reportdefinition">
  <Name>EmptyReport</Name>
</Report>"""

_VB_RDL = """\
<?xml version="1.0" encoding="utf-8"?>
<Report xmlns="http://schemas.microsoft.com/sqlserver/reporting/2010/01/reportdefinition">
  <Name>VbReport</Name>
  <Code>Function FormatCurrency(val As Decimal) As String
    Return Format(val, "C")
  End Function</Code>
  <DataSets>
    <DataSet Name="Sales">
      <Query>
        <CommandType>Text</CommandType>
        <CommandText>SELECT id, amount FROM sales</CommandText>
      </Query>
    </DataSet>
  </DataSets>
</Report>"""

_TSQL_RDL = """\
<?xml version="1.0" encoding="utf-8"?>
<Report xmlns="http://schemas.microsoft.com/sqlserver/reporting/2010/01/reportdefinition">
  <Name>TsqlReport</Name>
  <DataSets>
    <DataSet Name="Dates">
      <Query>
        <CommandType>Text</CommandType>
        <CommandText>SELECT id, GETDATE() as ts, ISNULL(name, 'N/A') FROM events</CommandText>
      </Query>
    </DataSet>
  </DataSets>
</Report>"""


# ── parse_rdl tests ───────────────────────────────────────────────────────────

def test_parse_rdl_report_name():
    result = parse_rdl(_SIMPLE_RDL, filename="SalesReport")
    assert result.report_name == "SalesReport"


def test_parse_rdl_data_sources():
    result = parse_rdl(_SIMPLE_RDL)
    assert len(result.data_sources) == 1
    assert result.data_sources[0].name == "DS1"
    assert result.data_sources[0].data_source_type == "SQL"


def test_parse_rdl_datasets_text():
    result = parse_rdl(_SIMPLE_RDL)
    assert len(result.datasets) == 1
    ds = result.datasets[0]
    assert ds.name == "Orders"
    assert ds.query_language == "Text"
    assert "order_id" in ds.query


def test_parse_rdl_parameters():
    result = parse_rdl(_SIMPLE_RDL)
    assert "start" in result.parameters


def test_parse_rdl_report_items():
    result = parse_rdl(_SIMPLE_RDL)
    assert len(result.report_items) == 1
    assert result.report_items[0].item_type == "Tablix"
    assert result.report_items[0].dataset_name == "Orders"


def test_parse_rdl_auto_convertible_text():
    result = parse_rdl(_SIMPLE_RDL)
    assert result.auto_convertible is True


def test_parse_rdl_stored_procedure_not_auto_convertible():
    result = parse_rdl(_SPROC_RDL)
    assert result.auto_convertible is False


def test_parse_rdl_stored_procedure_warning():
    result = parse_rdl(_SPROC_RDL)
    assert any("stored procedure" in w.lower() for w in result.warnings)


def test_parse_rdl_empty_report_not_auto_convertible():
    result = parse_rdl(_EMPTY_RDL)
    assert result.auto_convertible is False
    assert any("no datasets" in w.lower() for w in result.warnings)


def test_parse_rdl_vb_code_detected():
    result = parse_rdl(_VB_RDL)
    assert len(result.vb_code_blocks) == 1
    assert "FormatCurrency" in result.vb_code_blocks[0]
    assert any("vb" in w.lower() or "code" in w.lower() for w in result.warnings)


def test_parse_rdl_vb_still_auto_convertible_if_text_datasets():
    result = parse_rdl(_VB_RDL)
    assert result.auto_convertible is True


def test_parse_rdl_invalid_xml():
    result = parse_rdl("not xml at all", filename="bad")
    assert result.auto_convertible is False
    assert any("parse error" in w.lower() for w in result.warnings)


def test_parse_rdl_tsql_pattern_warning():
    result = parse_rdl(_TSQL_RDL)
    assert any("T-SQL pattern" in w for w in result.warnings)


def test_parse_rdl_connection_string():
    result = parse_rdl(_SIMPLE_RDL)
    assert "SalesDB" in result.data_sources[0].connection_string


# ── assessment_to_sql_notebook tests ─────────────────────────────────────────

def test_notebook_contains_report_name():
    assessment = parse_rdl(_SIMPLE_RDL, filename="SalesReport")
    sql = assessment_to_sql_notebook(assessment)
    assert "SalesReport" in sql


def test_notebook_contains_sql_query():
    assessment = parse_rdl(_SIMPLE_RDL)
    sql = assessment_to_sql_notebook(assessment)
    assert "order_id" in sql


def test_notebook_contains_dataset_label():
    assessment = parse_rdl(_SIMPLE_RDL)
    sql = assessment_to_sql_notebook(assessment)
    assert "Dataset: Orders" in sql


def test_notebook_sproc_commented_out():
    assessment = parse_rdl(_SPROC_RDL)
    sql = assessment_to_sql_notebook(assessment)
    assert "STORED PROCEDURE" in sql
    assert "sp_get_summary" in sql


def test_notebook_parameter_header():
    assessment = parse_rdl(_SIMPLE_RDL)
    sql = assessment_to_sql_notebook(assessment)
    assert "@start" in sql


def test_notebook_vb_block_commented():
    assessment = parse_rdl(_VB_RDL)
    sql = assessment_to_sql_notebook(assessment)
    assert "FormatCurrency" in sql
    assert "MANUAL MIGRATION REQUIRED" in sql


# ── convert_ssrs_file_set tests ───────────────────────────────────────────────

def test_convert_file_set_no_rdl_files():
    result = convert_ssrs_file_set({"report.txt": "not rdl"})
    assert result["notebooks"] == {}
    assert result["assessments"] == {}
    assert len(result["warnings"]) > 0


def test_convert_file_set_single_rdl():
    result = convert_ssrs_file_set({"SalesReport.rdl": _SIMPLE_RDL})
    assert "SalesReport.sql" in result["notebooks"]
    assert "SalesReport_assessment.json" in result["assessments"]


def test_convert_file_set_assessment_json_structure():
    result = convert_ssrs_file_set({"SalesReport.rdl": _SIMPLE_RDL})
    assessment = result["assessments"]["SalesReport_assessment.json"]
    assert assessment["report_name"] == "SalesReport"
    assert assessment["auto_convertible"] is True
    assert len(assessment["datasets"]) == 1


def test_convert_file_set_sproc_no_notebook():
    result = convert_ssrs_file_set({"ProcReport.rdl": _SPROC_RDL})
    assert "ProcReport.sql" not in result["notebooks"]
    assert "ProcReport_assessment.json" in result["assessments"]
    assert len(result["warnings"]) > 0


def test_convert_file_set_multiple_files():
    result = convert_ssrs_file_set({
        "SalesReport.rdl": _SIMPLE_RDL,
        "ProcReport.rdl": _SPROC_RDL,
    })
    assert "SalesReport.sql" in result["notebooks"]
    assert "ProcReport_assessment.json" in result["assessments"]


def test_convert_file_set_rdlc_extension():
    result = convert_ssrs_file_set({"MyReport.rdlc": _SIMPLE_RDL})
    assert "MyReport.sql" in result["notebooks"]


def test_convert_file_set_rsd_extension():
    result = convert_ssrs_file_set({"SharedDS.rsd": _SIMPLE_RDL})
    assert "SharedDS_assessment.json" in result["assessments"]


def test_convert_file_set_notebook_sql_content():
    result = convert_ssrs_file_set({"SalesReport.rdl": _SIMPLE_RDL})
    notebook_sql = result["notebooks"]["SalesReport.sql"]
    assert "order_id" in notebook_sql
    assert "Dataset: Orders" in notebook_sql
