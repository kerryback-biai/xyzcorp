import re
from pathlib import Path

import duckdb

from app.config import settings

DATA_DIR = settings.data_dir
M = DATA_DIR

# Each enterprise system has its own isolated tables
SYSTEMS = {
    "salesforce": {
        "sf_accounts": M / "salesforce" / "sf_accounts.parquet",
        "sf_contacts": M / "salesforce" / "sf_contacts.parquet",
        "sf_opportunities": M / "salesforce" / "sf_opportunities.parquet",
        "sf_orders": M / "salesforce" / "sf_orders.parquet",
        "sf_order_items": M / "salesforce" / "sf_order_items.parquet",
    },
    "legacy_crm": {
        "clients": M / "legacy_crm" / "clients.parquet",
        "deals": M / "legacy_crm" / "deals.parquet",
        "client_orders": M / "legacy_crm" / "client_orders.parquet",
        "order_details": M / "legacy_crm" / "order_details.parquet",
    },
    "hubspot": {
        "hs_companies": M / "hubspot" / "hs_companies.parquet",
        "hs_deals": M / "hubspot" / "hs_deals.parquet",
        "hs_line_items": M / "hubspot" / "hs_line_items.parquet",
    },
    "netsuite_industrial": {
        "ns_accounts": M / "netsuite_industrial" / "ns_accounts.parquet",
        "ns_transactions": M / "netsuite_industrial" / "ns_transactions.parquet",
        "ns_budget": M / "netsuite_industrial" / "ns_budget.parquet",
    },
    "quickbooks_energy": {
        "qb_accounts": M / "quickbooks_energy" / "qb_accounts.parquet",
        "qb_invoices": M / "quickbooks_energy" / "qb_invoices.parquet",
        "qb_payments": M / "quickbooks_energy" / "qb_payments.parquet",
        "qb_journal": M / "quickbooks_energy" / "qb_journal.parquet",
    },
    "netsuite_corporate": {
        "ns_acct_mapping": M / "netsuite_corporate" / "ns_acct_mapping.parquet",
        "ns_corp_budget": M / "netsuite_corporate" / "ns_corp_budget.parquet",
        "ns_corp_actuals": M / "netsuite_corporate" / "ns_corp_actuals.parquet",
    },
    "sap": {
        "sap_materials": M / "sap" / "sap_materials.parquet",
        "sap_vendors": M / "sap" / "sap_vendors.parquet",
        "sap_purchase_orders": M / "sap" / "sap_purchase_orders.parquet",
        "sap_po_items": M / "sap" / "sap_po_items.parquet",
        "sap_inventory": M / "sap" / "sap_inventory.parquet",
        "sap_deliveries": M / "sap" / "sap_deliveries.parquet",
    },
    "oracle_scm": {
        "ora_items": M / "oracle_scm" / "ora_items.parquet",
        "ora_suppliers": M / "oracle_scm" / "ora_suppliers.parquet",
        "ora_purchase_orders": M / "oracle_scm" / "ora_purchase_orders.parquet",
        "ora_po_lines": M / "oracle_scm" / "ora_po_lines.parquet",
        "ora_shipments": M / "oracle_scm" / "ora_shipments.parquet",
    },
    "workday": {
        "wd_workers": M / "workday" / "wd_workers.parquet",
        "wd_compensation": M / "workday" / "wd_compensation.parquet",
        "wd_reviews": M / "workday" / "wd_reviews.parquet",
        "wd_headcount": M / "workday" / "wd_headcount.parquet",
        "wd_system_ids": M / "workday" / "wd_system_ids.parquet",
    },
    "zendesk": {
        "zd_tickets": M / "zendesk" / "zd_tickets.parquet",
        "zd_ticket_tags": M / "zendesk" / "zd_ticket_tags.parquet",
        "zd_assignees": M / "zendesk" / "zd_assignees.parquet",
    },
}

SYSTEM_NAMES = list(SYSTEMS.keys())

_UNSAFE_PATTERN = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|TRUNCATE|EXEC|EXECUTE|GRANT|REVOKE)\b",
    re.IGNORECASE,
)

MAX_ROWS = 500


def validate_sql(sql: str) -> None:
    stripped = sql.strip().rstrip(";").strip()
    if not stripped.upper().startswith("SELECT") and not stripped.upper().startswith("WITH"):
        raise ValueError("Only SELECT queries are allowed")
    if _UNSAFE_PATTERN.search(stripped):
        raise ValueError("Query contains disallowed SQL keywords")


def execute_query(sql: str, system: str) -> dict:
    """Execute a read-only SQL query against a specific enterprise system."""
    if system not in SYSTEMS:
        return {"error": f"Unknown system: {system}. Available: {SYSTEM_NAMES}"}

    try:
        validate_sql(sql)
    except ValueError as e:
        return {"error": str(e)}

    try:
        con = duckdb.connect()

        for view_name, parquet_path in SYSTEMS[system].items():
            path_str = str(parquet_path).replace("\\", "/")
            con.execute(f"CREATE VIEW {view_name} AS SELECT * FROM read_parquet('{path_str}')")

        sql_upper = sql.strip().upper()
        if "LIMIT" not in sql_upper:
            sql = f"SELECT * FROM ({sql.rstrip(';')}) sub LIMIT {MAX_ROWS}"

        result = con.execute(sql)
        columns = [desc[0] for desc in result.description]
        rows = result.fetchall()
        con.close()

        data = [dict(zip(columns, row)) for row in rows]

        return {
            "columns": columns,
            "data": data,
            "row_count": len(data),
            "truncated": len(data) >= MAX_ROWS,
        }
    except Exception as e:
        return {"error": f"Query error: {str(e)}"}
