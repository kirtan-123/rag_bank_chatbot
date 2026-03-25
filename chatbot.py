"""Simple banking chatbot with MySQL + FAQ retrieval.

This version intentionally avoids heavyweight embedding/vector dependencies
so it runs reliably in lightweight local environments.
"""

# -----------------------------
# IMPORTS
# -----------------------------
from pathlib import Path
import re

import mysql.connector
from mysql.connector import Error

# -----------------------------
# MYSQL CONFIG (EMBEDDED)
# -----------------------------
DB_HOST = "bankdb-instance.c52mywewe7ia.ap-south-1.rds.amazonaws.com"
DB_USER = "root"
DB_PASSWORD = "Root1234!"   # your password
DB_NAME = "bankdb"

FAQ_CANDIDATE_FILES = [Path("bank_faq.txt"), Path("data.txt")]


def _expected_password(name):
    return f"{name}@123"


def parse_transaction_command(query):
    normalized = (query or "").strip().lower()
    if not normalized:
        return None

    credit_keywords = {
        "credit",
        "deposit",
        "deposite",
        "add",
        "added",
        "receive",
        "received",
    }
    debit_keywords = {
        "debit",
        "withdraw",
        "withdrawal",
        "spent",
        "deduct",
        "deducted",
        "pay",
        "paid",
    }

    amount_match = re.search(r"₹?\s*([\d,]+)", normalized)
    if not amount_match:
        return None

    amount_text = amount_match.group(1).replace(",", "")
    if not amount_text.isdigit():
        return None

    amount = int(amount_text)
    if amount <= 0:
        return None

    words = set(re.findall(r"[a-z]+", normalized))
    has_credit_word = bool(words & credit_keywords)
    has_debit_word = bool(words & debit_keywords)

    if has_credit_word and not has_debit_word:
        return "credit", amount
    if has_debit_word and not has_credit_word:
        return "debit", amount

    # Backward-compatible explicit format support.
    explicit_match = re.fullmatch(r"\s*(credit|debit)\s+₹?\s*([\d,]+)\s*", normalized)
    if explicit_match:
        return explicit_match.group(1), int(explicit_match.group(2).replace(",", ""))

    return None

def get_connection():
    return mysql.connector.connect(
        host=DB_HOST,
        user=DB_USER,
        password=DB_PASSWORD,
        database=DB_NAME
    )


def validate_login(name, password):
    clean_name = (name or "").strip()
    clean_password = (password or "").strip()
    if not clean_name or not clean_password:
        return False, "Name and password are required"

    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM customers WHERE name=%s", (clean_name,))
        result = cursor.fetchone()
        conn.close()
    except Error as exc:
        return False, f"Database error: {exc}"

    if not result:
        return False, "User not found"

    if clean_password != _expected_password(clean_name):
        return False, "Invalid password"

    return True, "Login successful"


def register_customer(name, balance, ac_type):
    clean_name = (name or "").strip()
    clean_ac_type = (ac_type or "").strip().lower()

    if not clean_name:
        return False, "Name is required", None

    if not clean_ac_type:
        return False, "Account type is required", None

    try:
        numeric_balance = float(balance)
    except (TypeError, ValueError):
        return False, "Balance must be a valid number", None

    conn = None
    try:
        conn = get_connection()
        conn.start_transaction()
        cursor = conn.cursor()

        cursor.execute("SELECT id FROM customers WHERE name=%s", (clean_name,))
        if cursor.fetchone():
            conn.rollback()
            return False, "User already exists", None

        cursor.execute("SELECT COALESCE(MAX(id), 0) + 1 FROM customers")
        next_id = int(cursor.fetchone()[0])

        cursor.execute(
            "INSERT INTO customers (id, name, balance, ac_type) VALUES (%s, %s, %s, %s)",
            (next_id, clean_name, numeric_balance, clean_ac_type),
        )

        conn.commit()
        return True, "Registration successful", next_id
    except Error as exc:
        if conn:
            conn.rollback()
        return False, f"Database error: {exc}", None
    finally:
        if conn:
            conn.close()


def get_customer_account_type(name):
    clean_name = (name or "").strip()
    if not clean_name:
        return None

    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT ac_type FROM customers WHERE name=%s", (clean_name,))
        result = cursor.fetchone()
        conn.close()
    except Error:
        return None

    if not result:
        return None

    return result[0]


def _get_customer_balance_value(name):
    clean_name = (name or "").strip()
    if not clean_name:
        return None, "User not found"

    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT balance FROM customers WHERE name=%s", (clean_name,))
        result = cursor.fetchone()
        conn.close()
    except Error as exc:
        return None, f"Database error: {exc}"

    if not result:
        return None, "User not found"

    return float(result[0]), None


def _is_interest_query(query):
    normalized = query.lower()
    has_interest = "interest" in normalized
    has_period = any(term in normalized for term in ["monthly", "montly", "annual"])
    return has_interest and has_period


def get_loan_interest_reply(name, query):
    account_type = get_customer_account_type(name)
    if not account_type or str(account_type).strip().lower() != "loan":
        return "Interest calculation is available only for loan accounts."

    balance, error = _get_customer_balance_value(name)
    if error:
        return error

    principal = abs(balance)
    if principal == 0:
        return "Your balance is 0, so monthly and annual interest are 0 rupees."

    annual_rate = 0.12
    annual_interest = principal * annual_rate
    monthly_interest = annual_interest / 12

    normalized = query.lower()
    wants_monthly = "monthly" in normalized or "montly" in normalized
    wants_annual = "annual" in normalized

    if wants_monthly and not wants_annual:
        return (
            f"At 12% annual rate, your monthly interest on {principal:.2f} rupees "
            f"is {monthly_interest:.2f} rupees"
        )

    if wants_annual and not wants_monthly:
        return (
            f"At 12% annual rate, your annual interest on {principal:.2f} rupees "
            f"is {annual_interest:.2f} rupees"
        )

    return (
        f"At 12% annual rate on {principal:.2f} rupees: "
        f"monthly interest is {monthly_interest:.2f} rupees and annual interest is "
        f"{annual_interest:.2f} rupees"
    )

# -----------------------------
# DATABASE FUNCTIONS
# -----------------------------
def get_balance(name):
    try:
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT balance FROM customers WHERE name=%s", (name,))
        result = cursor.fetchone()

        conn.close()
    except Error as exc:
        return f"Database error: {exc}"

    if result:
        return f"Your balance is {result[0]} rupees"
    return "User not found"


def get_transactions(name):
    try:
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT t.amount, t.type
            FROM transactions t
            JOIN customers c ON t.customer_id = c.id
            WHERE c.name = %s
        """, (name,))

        results = cursor.fetchall()
        conn.close()
    except Error as exc:
        return f"Database error: {exc}"

    if results:
        return "\n".join([f"{t[1]}: {t[0]}" for t in results])
    return "No transactions found"


def _get_transaction_columns(cursor):
    cursor.execute("SHOW COLUMNS FROM transactions")
    rows = cursor.fetchall()
    return {row[0] for row in rows}


def add_transaction(name, txn_type, amount):
    conn = None
    try:
        conn = get_connection()
        conn.start_transaction()
        cursor = conn.cursor()

        cursor.execute("SELECT id, balance FROM customers WHERE name=%s", (name,))
        customer = cursor.fetchone()
        if not customer:
            conn.rollback()
            return "User not found"

        customer_id, old_balance = customer
        new_balance = old_balance + amount if txn_type == "credit" else old_balance - amount

        if txn_type == "debit" and new_balance < 0:
            conn.rollback()
            return "Insufficient balance for this debit transaction"

        transaction_columns = _get_transaction_columns(cursor)
        insert_columns = []
        insert_values = []
        params = []

        if "customer_id" in transaction_columns:
            insert_columns.append("customer_id")
            insert_values.append("%s")
            params.append(customer_id)
        if "amount" in transaction_columns:
            insert_columns.append("amount")
            insert_values.append("%s")
            params.append(amount)
        if "type" in transaction_columns:
            insert_columns.append("type")
            insert_values.append("%s")
            params.append(txn_type)
        if "description" in transaction_columns:
            insert_columns.append("description")
            insert_values.append("%s")
            params.append("Added via chatbot")
        elif "desc" in transaction_columns:
            insert_columns.append("desc")
            insert_values.append("%s")
            params.append("Added via chatbot")

        if not insert_columns:
            conn.rollback()
            return "Could not add transaction: transactions table has unsupported schema"

        insert_query = (
            f"INSERT INTO transactions ({', '.join(insert_columns)}) "
            f"VALUES ({', '.join(insert_values)})"
        )
        cursor.execute(insert_query, tuple(params))

        cursor.execute(
            "UPDATE customers SET balance=%s WHERE id=%s",
            (new_balance, customer_id),
        )

        conn.commit()
        return (
            f"Transaction added: {txn_type} {amount} rupees. "
            f"New balance is {new_balance} rupees"
        )
    except Error as exc:
        if conn:
            conn.rollback()
        return f"Database error: {exc}"
    finally:
        if conn:
            conn.close()


# -----------------------------
# LOAD FAQ DATA
# -----------------------------
def _find_faq_file():
    for path in FAQ_CANDIDATE_FILES:
        if path.exists():
            return path
    return None


def _load_faq_chunks():
    faq_path = _find_faq_file()
    if faq_path is None:
        return []

    content = faq_path.read_text(encoding="utf-8", errors="ignore")
    raw_chunks = re.split(r"\n\s*\n|(?<=\.)\s+", content)
    chunks = [chunk.strip() for chunk in raw_chunks if chunk.strip()]
    return chunks


FAQ_CHUNKS = _load_faq_chunks()


def _simple_retrieve(query):
    if not FAQ_CHUNKS:
        return None

    tokens = set(re.findall(r"\w+", query.lower()))
    if not tokens:
        return FAQ_CHUNKS[0]

    best_chunk = None
    best_score = 0
    for chunk in FAQ_CHUNKS:
        chunk_tokens = set(re.findall(r"\w+", chunk.lower()))
        score = len(tokens & chunk_tokens)
        if score > best_score:
            best_score = score
            best_chunk = chunk

    return best_chunk if best_score > 0 else None

# -----------------------------
# CHATBOT LOGIC
# -----------------------------
def chatbot(query, user="Jaya"):
    transaction_command = parse_transaction_command(query)
    if transaction_command:
        txn_type, amount = transaction_command
        return add_transaction(user, txn_type, amount)

    query = query.lower()

    if _is_interest_query(query):
        return get_loan_interest_reply(user, query)

    # PERSONAL QUERIES → MYSQL
    if "my balance" in query or query.strip() == "balance":
        return get_balance(user)

    elif "transaction" in query:
        return get_transactions(user)

    # GENERAL QUERIES → FAQ
    answer = _simple_retrieve(query)
    if not answer:
        if not FAQ_CHUNKS:
            return "No FAQ file found. Add data.txt or bank_faq.txt."
        return "Sorry, I don't know."

    return answer


# -----------------------------
# RUN CHATBOT (CLI)
# -----------------------------
def run_cli():
    print("Banking Chatbot (MySQL + FAQ) Ready")

    logged_in_user = None
    while logged_in_user is None:
        try:
            name = input("Customer name: ").strip()
            password = input("Password: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nExiting chatbot.")
            return

        is_valid, message = validate_login(name, password)
        if is_valid:
            logged_in_user = name
            print(f"Login successful. Welcome {logged_in_user}.")
            account_type = get_customer_account_type(logged_in_user)
            if account_type:
                print(f"Account type: {account_type}")
        else:
            print(f"Login failed: {message}")

    while True:
        try:
            query = input("You: ")
        except (EOFError, KeyboardInterrupt):
            print("\nExiting chatbot.")
            break

        if query.lower() == "exit":
            break

        answer = chatbot(query, user=logged_in_user)
        print("Bot:", answer)


if __name__ == "__main__":
    run_cli()