import streamlit as st
import pandas as pd
import numpy as np
import requests
from datetime import datetime, timedelta
import sqlite3
import plotly.express as px   # ← THIS LINE WAS MISSING – NOW ADDED!

# =============================================
# BUDGETBUDDY – Sparziel-Tracker für Schweizer Studierende
# =============================================
# Dies ist die komplette App in EINER Datei
# Erfüllt ALLE 6 Kriterien mit minimalem Code

st.set_page_config(page_title="BudgetBuddy", page_icon="💰", layout="centered")

# ====================== DATABASE ======================
def init_db():
    conn = sqlite3.connect("budget.db")
    c = conn.cursor()
    
    c.execute('''
        CREATE TABLE IF NOT EXISTS expenses (
            id INTEGER PRIMARY KEY,
            date TEXT,
            category TEXT,
            original_amount REAL,
            currency TEXT,
            amount_chf REAL
        )
    ''')
    
    c.execute('''
        CREATE TABLE IF NOT EXISTS settings (
            id INTEGER PRIMARY KEY,
            monthly_income REAL DEFAULT 3000.0,
            savings_goal REAL DEFAULT 10000.0,
            current_balance REAL DEFAULT 0.0
        )
    ''')
    
    c.execute("SELECT COUNT(*) FROM settings")
    if c.fetchone()[0] == 0:
        c.execute("INSERT INTO settings (monthly_income, savings_goal, current_balance) VALUES (3000.0, 10000.0, 0.0)")
    
    conn.commit()
    conn.close()

def load_expenses():
    conn = sqlite3.connect("budget.db")
    df = pd.read_sql_query("SELECT * FROM expenses ORDER BY date DESC", conn)
    conn.close()
    if not df.empty:
        df['date'] = pd.to_datetime(df['date'])
    return df

def load_settings():
    conn = sqlite3.connect("budget.db")
    df = pd.read_sql_query("SELECT * FROM settings LIMIT 1", conn)
    conn.close()
    if df.empty:
        return {"monthly_income": 3000.0, "savings_goal": 10000.0, "current_balance": 0.0}
    return df.iloc[0].to_dict()

def save_settings(income, goal, balance):
    conn = sqlite3.connect("budget.db")
    c = conn.cursor()
    c.execute("UPDATE settings SET monthly_income=?, savings_goal=?, current_balance=? WHERE id=1",
              (income, goal, balance))
    conn.commit()
    conn.close()

def add_expense(date, category, original_amount, currency, amount_chf):
    conn = sqlite3.connect("budget.db")
    c = conn.cursor()
    c.execute("INSERT INTO expenses (date, category, original_amount, currency, amount_chf) VALUES (?, ?, ?, ?, ?)",
              (date.strftime("%Y-%m-%d"), category, original_amount, currency, amount_chf))
    conn.commit()
    conn.close()

def delete_last_expense():
    conn = sqlite3.connect("budget.db")
    c = conn.cursor()
    c.execute("DELETE FROM expenses WHERE id = (SELECT MAX(id) FROM expenses)")
    conn.commit()
    conn.close()

def add_monthly_income():
    settings = load_settings()
    new_balance = settings["current_balance"] + settings["monthly_income"]
    save_settings(settings["monthly_income"], settings["savings_goal"], new_balance)

# ====================== CURRENCY API ======================
def convert_to_chf(amount, from_currency):
    if from_currency == "CHF":
        return amount
    try:
        url = f"https://api.frankfurter.app/latest?from={from_currency}&to=CHF"
        response = requests.get(url, timeout=5)
        data = response.json()
        rate = data["rates"]["CHF"]
        return round(amount * rate, 2)
    except Exception:
        st.warning(f"API-Fehler: Konnte {from_currency} nicht umrechnen.")
        return amount

# ====================== MACHINE LEARNING (selbst geschrieben) ======================
def linear_regression_from_scratch(x, y):
    n = len(x)
    if n < 2:
        return None, None
    sum_x = sum(x)
    sum_y = sum(y)
    sum_xy = sum(xi * yi for xi, yi in zip(x, y))
    sum_x2 = sum(xi**2 for xi in x)
    denominator = n * sum_x2 - sum_x**2
    if denominator == 0:
        return None, None
    a = (n * sum_xy - sum_x * sum_y) / denominator
    b = (sum_y - a * sum_x) / n
    return a, b

def predict_next_month_spending(df):
    if df.empty:
        return 0.0, "Noch keine Daten"
    df_monthly = df.copy()
    df_monthly['month'] = df_monthly['date'].dt.to_period('M')
    monthly = df_monthly.groupby('month')['amount_chf'].sum().reset_index()
    monthly = monthly.sort_values('month')
    if len(monthly) < 2:
        avg = monthly['amount_chf'].mean()
        return avg, "Nur 1 Monat → Durchschnitt verwendet"
    x = list(range(1, len(monthly) + 1))
    y = monthly['amount_chf'].tolist()
    a, b = linear_regression_from_scratch(x, y)
    if a is None:
        return sum(y)/len(y), "Fallback: Durchschnitt"
    next_month_x = len(monthly) + 1
    prediction = a * next_month_x + b
    return max(0, round(prediction, 2)), f"Trend-basiert"

# ====================== SAVINGS GOAL ======================
def calculate_time_to_goal(settings, predicted_spending):
    net_monthly = settings["monthly_income"] - predicted_spending
    remaining = settings["savings_goal"] - settings["current_balance"]
    if net_monthly <= 0:
        return "Nie (du sparst nicht)", None
    if remaining <= 0:
        return "Bereits erreicht! 🎉", None
    months = remaining / net_monthly
    days = months * 30
    today = datetime.today()
    target_date = today + timedelta(days=days)
    return f"{months:.1f} Monate → ca. {target_date.strftime('%d. %B %Y')}", round(months, 1)

def heavy_purchase_warning(amount_chf, settings, predicted_spending):
    if settings["savings_goal"] <= 0:
        return None
    threshold = 0.02 * settings["savings_goal"]
    if amount_chf > threshold:
        net_monthly = settings["monthly_income"] - predicted_spending
        if net_monthly <= 0:
            return "Dieser Kauf ist sehr groß – du sparst aktuell nicht!"
        setback_months = amount_chf / net_monthly
        setback_days = setback_months * 30
        return f"⚠️ Dieser Kauf setzt dich um ca. {setback_days:.0f} Tage zurück!"
    return None

# ====================== APP ======================
init_db()
settings = load_settings()
df = load_expenses()

st.title("💰 BudgetBuddy – Sparziel-Tracker (Schweiz)")
st.markdown("**Dein persönlicher Helfer gegen Geldsorgen** – mit selbst geschriebener KI-Vorhersage!")

with st.sidebar:
    st.header("⚙️ Einstellungen")
    with st.expander("Sparziel & Einkommen ändern", expanded=True):
        new_income = st.number_input("Monatliches Einkommen (CHF)", value=settings["monthly_income"], step=100.0)
        new_goal = st.number_input("Sparziel (CHF)", value=settings["savings_goal"], step=500.0)
        new_balance = st.number_input("Aktuelles Guthaben (CHF)", value=settings["current_balance"], step=50.0)
        if st.button("💾 Einstellungen speichern"):
            save_settings(new_income, new_goal, new_balance)
            st.success("Gespeichert!")
            st.rerun()
    if st.button("📅 Monatliches Einkommen erhalten"):
        add_monthly_income()
        st.success(f"+{settings['monthly_income']} CHF hinzugefügt!")
        st.rerun()

st.header("➕ Neue Ausgabe hinzufügen")
col1, col2, col3, col4 = st.columns([2, 1.5, 1.5, 1])
with col1:
    date = st.date_input("Datum", value=datetime.today())
with col2:
    category = st.selectbox("Kategorie", ["Lebensmittel", "Transport", "Miete", "Freizeit", "Studium", "Sonstiges"])
with col3:
    original_amount = st.number_input("Betrag", min_value=0.01, step=1.0)
    currency = st.selectbox("Währung", ["CHF", "EUR", "USD", "GBP", "JPY"])
with col4:
    if st.button("💾 Ausgabe speichern", type="primary"):
        amount_chf = convert_to_chf(original_amount, currency)
        add_expense(date, category, original_amount, currency, amount_chf)
        settings = load_settings()
        pred, _ = predict_next_month_spending(load_expenses())
        warning = heavy_purchase_warning(amount_chf, settings, pred)
        if warning:
            st.warning(warning)
        else:
            st.success(f"{amount_chf} CHF gespeichert!")
        st.rerun()

st.header("📊 Übersicht")
col_a, col_b, col_c = st.columns(3)
total_spent = df["amount_chf"].sum() if not df.empty else 0
col_a.metric("Gesamt ausgegeben", f"CHF {total_spent:,.0f}")
col_b.metric("Aktuelles Guthaben", f"CHF {settings['current_balance']:,.0f}")
col_c.metric("Sparziel", f"CHF {settings['savings_goal']:,.0f}")

st.subheader("Filter")
col_f1, col_f2 = st.columns(2)
date_from = col_f1.date_input("Von", value=datetime.today() - timedelta(days=90), key="from")
date_to = col_f2.date_input("Bis", value=datetime.today(), key="to")
filtered_df = df.copy()
if not filtered_df.empty:
    filtered_df = filtered_df[(filtered_df['date'].dt.date >= date_from) & 
                              (filtered_df['date'].dt.date <= date_to)]

if not filtered_df.empty:
    cat_sum = filtered_df.groupby("category")["amount_chf"].sum().reset_index()
    fig_bar = px.bar(cat_sum, x="category", y="amount_chf", title="Ausgaben nach Kategorie (CHF)", color="category")
    st.plotly_chart(fig_bar, use_container_width=True)
    
    filtered_df['month'] = filtered_df['date'].dt.to_period('M').astype(str)
    trend = filtered_df.groupby("month")["amount_chf"].sum().reset_index()
    fig_line = px.line(trend, x="month", y="amount_chf", title="Monatlicher Ausgabentrend", markers=True)
    st.plotly_chart(fig_line, use_container_width=True)
else:
    st.info("Füge Ausgaben hinzu, um Diagramme zu sehen!")

st.header("🔮 KI-Vorhersagen (selbst geschrieben)")
if st.button("📈 Vorhersage aktualisieren"):
    st.rerun()
predicted_spending, info = predict_next_month_spending(df)
time_to_goal_str, _ = calculate_time_to_goal(settings, predicted_spending)
col_p1, col_p2 = st.columns(2)
col_p1.metric("Vorhergesagte Ausgaben nächsten Monat", f"CHF {predicted_spending:,.0f}")
col_p2.metric("Wann erreichst du dein Sparziel?", time_to_goal_str)
progress = min(100, (settings["current_balance"] / settings["savings_goal"]) * 100) if settings["savings_goal"] > 0 else 0
st.progress(progress / 100)
st.caption(f"Fortschritt: {progress:.1f}%")

st.header("📋 Deine Ausgaben")
if not df.empty:
    display_df = df.copy()
    display_df['date'] = display_df['date'].dt.date
    display_df = display_df[['date', 'category', 'original_amount', 'currency', 'amount_chf']]
    st.dataframe(display_df, use_container_width=True)
    if st.button("🗑️ Letzte Ausgabe löschen"):
        delete_last_expense()
        st.success("Gelöscht!")
        st.rerun()
else:
    st.info("Noch keine Ausgaben – starte mit dem Formular oben!")

st.caption("BudgetBuddy © 2026 | Lineare Regression selbst implementiert | Perfekt für deine CS-Lecture!")