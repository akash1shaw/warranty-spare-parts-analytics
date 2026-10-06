"""
genai_assistant.py
Natural-language Q&A over the warranty database (text-to-SQL + summary).

Setup:  pip install anthropic
        export ANTHROPIC_API_KEY=your_key      (Windows: set ANTHROPIC_API_KEY=your_key)
Run:    python genai_assistant.py
Ask:    "Which parts caused the most warranty cost?"
"""
import os, re, sqlite3
import pandas as pd

MODEL = "claude-sonnet-5-5"   # check docs.claude.com for the current model name

SCHEMA = """
products(product_id, product_name, category, unit_price, base_failure_rate)
parts(part_id, part_name, product_id, supplier_id, unit_cost, lead_time_days)
sales(month 'YYYY-MM', product_id, region, units_sold)
warranty_claims(claim_id, claim_date 'YYYY-MM-DD', product_id, part_id, region,
                failure_cause, claim_cost_inr, repair_days, stockout_flag)
inventory_monthly(month 'YYYY-MM', part_id, demand, opening_stock, fulfilled,
                  stockout_units, closing_stock, units_ordered)
Data covers 2022-01 to 2024-12. Currency is INR. SQLite dialect.
"""

def is_safe(sql: str) -> bool:
    """Allow a single read-only SELECT/WITH statement only."""
    s = sql.strip().rstrip(";")
    if ";" in s:
        return False
    if not re.match(r"(?is)^(select|with)\b", s):
        return False
    return not re.search(r"(?i)\b(insert|update|delete|drop|alter|create|attach|pragma|replace)\b", s)

def ask(question: str, con, client) -> str:
    sql = client.messages.create(
        model=MODEL, max_tokens=500,
        system="You write one SQLite SELECT query for the schema below. "
               "Return ONLY the SQL, no markdown, no explanation.\n" + SCHEMA,
        messages=[{"role": "user", "content": question}],
    ).content[0].text.strip().strip("`")
    sql = re.sub(r"(?i)^sql\s*", "", sql)
    if not is_safe(sql):
        return f"Blocked: generated query was not a safe read-only SELECT.\n{sql}"
    try:
        df = pd.read_sql(sql, con)
    except Exception as e:
        return f"Query failed: {e}\nSQL: {sql}"
    answer = client.messages.create(
        model=MODEL, max_tokens=400,
        system="You are a service-operations analyst. Answer the question in 2-4 sentences "
               "using ONLY the query result provided. Mention numbers and units.",
        messages=[{"role": "user",
                   "content": f"Question: {question}\n\nResult:\n{df.head(20).to_string(index=False)}"}],
    ).content[0].text
    return f"{answer}\n\n[SQL used]\n{sql}"

if __name__ == "__main__":
    import anthropic
    con = sqlite3.connect("warranty.db")
    client = anthropic.Anthropic()          # reads ANTHROPIC_API_KEY
    print("Warranty analytics assistant. Type 'exit' to quit.")
    while (q := input("\nAsk> ").strip()).lower() not in {"exit", "quit"}:
        print(ask(q, con, client))
