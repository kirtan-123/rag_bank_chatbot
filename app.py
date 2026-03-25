import os

from flask import Flask, jsonify, render_template, request, session
from dotenv import load_dotenv

from aws_notifications import enqueue_login_event
from chatbot import chatbot, get_customer_account_type, register_customer, validate_login

load_dotenv()

app = Flask(__name__)
app.config["SECRET_KEY"] = os.getenv("FLASK_SECRET_KEY", "dev-secret")


@app.get("/")
def index():
    return render_template("index.html")


@app.post("/chat")
def chat():
    logged_in_user = session.get("customer_name")
    if not logged_in_user:
        return jsonify({"error": "Please login first"}), 401

    payload = request.get_json(silent=True) or {}
    message = str(payload.get("message", "")).strip()

    if not message:
        return jsonify({"error": "Message is required"}), 400

    answer = chatbot(message, user=logged_in_user)
    return jsonify({"reply": answer, "user": logged_in_user})


@app.post("/login")
def login():
    payload = request.get_json(silent=True) or {}
    name = str(payload.get("name", "")).strip()
    password = str(payload.get("password", "")).strip()

    is_valid, message = validate_login(name, password)
    if not is_valid:
        return jsonify({"error": message}), 401

    account_type = get_customer_account_type(name)
    session["customer_name"] = name
    notification_result = enqueue_login_event(name, account_type)
    return jsonify({
        "message": "Login successful",
        "user": name,
        "account_type": account_type,
        "notification": notification_result,
    })


@app.post("/logout")
def logout():
    session.pop("customer_name", None)
    return jsonify({"message": "Logged out"})


@app.post("/register")
def register():
    payload = request.get_json(silent=True) or {}
    name = str(payload.get("name", "")).strip()
    balance = payload.get("balance", "")
    ac_type = str(payload.get("ac_type", "")).strip()

    ok, message, customer_id = register_customer(name, balance, ac_type)
    if not ok:
        return jsonify({"error": message}), 400

    return jsonify({
        "message": message,
        "customer_id": customer_id,
        "default_password": f"{name}@123",
    })


if __name__ == "__main__":
    debug_mode = os.getenv("FLASK_DEBUG", "false").strip().lower() == "true"
    app.run(host="127.0.0.1", port=5000, debug=debug_mode)
