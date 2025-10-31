from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
import sqlite3
from datetime import datetime
import os
import secrets
import requests  # For SMS API

app = Flask(__name__)
app.secret_key = 'supersecretkey_for_session_management_and_flash_messages'
app.config['ORGANIZATION_NAME'] = "ማህበረ አርጋብ"
DB_NAME = 'lottery.db'
ADMIN_USERNAME = 'admin'
ADMIN_PASSWORD = 'password123'

# SMS Configuration (Example using Ethio Telecom SMS Gateway)
SMS_API_URL = "https://sms.example.com/api/send"  # Replace with actual SMS gateway URL
SMS_API_KEY = "your_sms_api_key"
TELEBIRR_OWNER = "+251936114505"

# Database setup
def init_db():
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    
    # Drop existing table and recreate with new schema
    cur.execute('DROP TABLE IF EXISTS applications')
    
    cur.execute('''
    CREATE TABLE IF NOT EXISTS applications (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        full_name TEXT NOT NULL,
        phone TEXT NOT NULL,
        draw INTEGER NOT NULL UNIQUE,  -- UNIQUE constraint ensures one ticket per draw
        confirmation_code TEXT NOT NULL UNIQUE,
        payment_method TEXT NOT NULL,
        transaction_id TEXT,
        transaction_validated BOOLEAN DEFAULT FALSE,
        status TEXT DEFAULT 'pending',
        ticket_price INTEGER DEFAULT 10,  -- Ticket price in ETB
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')
    conn.commit()
    conn.close()

init_db()

# Utility Functions
def generate_confirmation_code():
    return secrets.token_urlsafe(8).upper()

def send_sms(phone_number, message):
    """
    Send SMS to user - Integrate with actual SMS gateway
    """
    try:
        # Example SMS integration (replace with actual SMS gateway)
        payload = {
            'api_key': SMS_API_KEY,
            'to': phone_number,
            'message': message,
            'sender': 'LottoWin'
        }
        
        # Uncomment to actually send SMS
        # response = requests.post(SMS_API_URL, json=payload)
        # return response.status_code == 200
        
        # For demo purposes, just print the SMS
        print(f"📱 SMS to {phone_number}: {message}")
        return True
        
    except Exception as e:
        print(f"SMS sending failed: {e}")
        return False

# Context Processor
@app.context_processor
def inject_global_data():
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    
    # Get available draws (not taken yet)
    cur.execute("SELECT draw FROM applications WHERE status != 'cancelled'")
    taken_draws = [row[0] for row in cur.fetchall()]
    available_draws = [i for i in range(1, 301) if i not in taken_draws]
    
    draws_data = [{'id': i, 'name': f"ዕጣ ቁጥር {i}"} for i in available_draws]
    conn.close()
    
    return {
        'current_year': datetime.utcnow().year,
        'organization_name': app.config['ORGANIZATION_NAME'],
        'draws_data': draws_data,
        'ticket_price': 10  # 10 ETB
    }

# Routes
@app.route('/')
def home():
    return render_template('index.html')

@app.route('/apply', methods=['GET', 'POST'])
def apply():
    if request.method == 'POST':
        full_name = request.form['full_name']
        phone = request.form['phone']
        draw = request.form['draw']
        payment_method = request.form['payment_method']
        transaction_id = request.form.get('transaction_id')
        confirmation_code = generate_confirmation_code()

        conn = sqlite3.connect(DB_NAME)
        cur = conn.cursor()
        
        try:
            # Check if draw number is already taken
            cur.execute("SELECT id FROM applications WHERE draw = ?", (draw,))
            if cur.fetchone():
                flash("ይህ የዕጣ ቁጥር አስቀድሞ ተይዟል። እባክዎ ሌላ ቁጥር ይምረጡ።", 'error')
                return redirect(url_for('apply'))

            cur.execute(
                "INSERT INTO applications (full_name, phone, draw, confirmation_code, payment_method, transaction_id, ticket_price) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (full_name, phone, draw, confirmation_code, payment_method, transaction_id, 10)
            )
            conn.commit()
            application_id = cur.lastrowid

            # Send SMS confirmation
            sms_message = f"የዕጣ ትኬት ጥያቄዎ ተቀብለናል። የማረጋገጫ ኮድዎ: {confirmation_code}። ዕጣ: {draw}። ዋጋ: 10 ብር።"
            send_sms(phone, sms_message)

            application_data = {
                'id': application_id,
                'full_name': full_name,
                'phone': phone,
                'draw': draw,
                'confirmation_code': confirmation_code,
                'payment_method': payment_method,
                'ticket_price': 10
            }
            return render_template('confirmation.html', application=application_data)

        except sqlite3.IntegrityError as e:
            if 'UNIQUE constraint failed: applications.draw' in str(e):
                flash("ይህ የዕጣ ቁጥር አስቀድሞ ተይዟል። እባክዎ ሌላ ቁጥር ይምረጡ።", 'error')
            else:
                flash("ስህተት: ተመሳሳይ የማረጋገጫ ኮድ አስቀድሞ አለ። እባክዎ እንደገና ይሞክሩ።", 'error')
            return redirect(url_for('apply'))
        finally:
            conn.close()
    
    return render_template('apply.html')

@app.route('/payment-instructions')
def payment_instructions():
    return render_template('payment_instructions.html')

@app.route('/admin-login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
            session['admin_logged_in'] = True
            flash('እንኳን ደህና መጡ አስተዳዳሪ!', 'success')
            return redirect(url_for('admin_panel'))
        else:
            flash('ትክክል ያልሆነ የተጠቃሚ ስም ወይም የይለፍ ቃል', 'error')
    return render_template('admin_login.html')

@app.route('/admin-logout')
def admin_logout():
    session.pop('admin_logged_in', None)
    flash('በተሳካ ሁኔታ ወጥተዋል', 'info')
    return redirect(url_for('admin_login'))

@app.route('/admin')
def admin_panel():
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin_login'))

    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("SELECT id, full_name, phone, draw, confirmation_code, payment_method, transaction_id, transaction_validated, status, ticket_price, created_at FROM applications ORDER BY created_at DESC")
    
    applications = []
    for row in cur.fetchall():
        app_data = {
            'id': row[0],
            'full_name': row[1],
            'phone': row[2],
            'draw': row[3],
            'confirmation_code': row[4],
            'payment_method': row[5],
            'transaction_id': row[6],
            'transaction_validated': row[7],
            'status': row[8],
            'ticket_price': row[9],
            'created_at': row[10]
        }
        applications.append(app_data)
    
    conn.close()
    return render_template('admin_panel.html', applications=applications)

@app.route('/verify-payment/<int:app_id>')
def verify_payment(app_id):
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin_login'))

    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    
    # Get application details
    cur.execute("SELECT phone, draw FROM applications WHERE id = ?", (app_id,))
    app_data = cur.fetchone()
    
    if app_data:
        phone, draw = app_data
        # Send SMS notification
        sms_message = f"ክፍያዎ ተረጋግጧል! ዕጣ ቁጥር: {draw}። የዕጣ ውጤት በሚገኝ ጊዜ ይጠበቃል።"
        send_sms(phone, sms_message)
    
    cur.execute("UPDATE applications SET status = 'verified' WHERE id = ?", (app_id,))
    conn.commit()
    conn.close()
    
    flash(f'Application {app_id} marked as Verified! SMS sent to user.', 'success')
    return redirect(url_for('admin_panel'))

@app.route('/mark-paid/<int:app_id>')
def mark_paid(app_id):
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin_login'))

    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    
    # Get application details
    cur.execute("SELECT phone, draw FROM applications WHERE id = ?", (app_id,))
    app_data = cur.fetchone()
    
    if app_data:
        phone, draw = app_data
        # Send SMS notification
        sms_message = f"ትኬትዎ ተሞልቷል! ዕጣ ቁጥር: {draw}። የዕጣ ውጤት በሚገኝ ጊዜ ይጠበቃል።"
        send_sms(phone, sms_message)
    
    cur.execute("UPDATE applications SET status = 'paid' WHERE id = ?", (app_id,))
    conn.commit()
    conn.close()
    
    flash(f'Application {app_id} marked as Paid (Ticket Filled)! SMS sent to user.', 'success')
    return redirect(url_for('admin_panel'))

@app.route('/validate-transaction', methods=['POST'])
def validate_transaction_api():
    if not session.get('admin_logged_in'):
        return jsonify({"valid": False, "message": "Unauthorized"}), 401

    data = request.json
    transaction_id = data.get('transaction_id', '').upper()
    payment_method = data.get('payment_method')

    # Simulate transaction validation
    is_valid = False
    message = "ትራንዛክሽን ቁጥር አልተገኘም ወይም ትክክል አይደለም።"
    suggestions = []

    if payment_method == 'telebirr':
        if transaction_id.startswith('TBR') and len(transaction_id) >= 10 and transaction_id != 'TBR123456789':
            is_valid = True
            message = "የTeleBirr ትራንዛክሽን ቁጥር ትክክል ነው!"
        else:
            suggestions.append("የTeleBirr ትራንዛክሽን ቁጥሮች አብዛኛውን ጊዜ በ 'TBR' ይጀምራሉ።")
    elif payment_method == 'cbe_mobile':
        if transaction_id.startswith('CBE') and len(transaction_id) >= 10 and transaction_id != 'CBE123456789':
            is_valid = True
            message = "የCBE Mobile ትራንዛክሽን ቁጥር ትክክል ነው!"
        else:
            suggestions.append("የCBE Mobile ትራንዛክሽን ቁጥሮች አብዛኛውን ጊዜ በ 'CBE' ይጀምራሉ።")

    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    
    if is_valid:
        cur.execute("SELECT id FROM applications WHERE transaction_id = ? AND transaction_validated = TRUE", (transaction_id,))
        if cur.fetchone():
            is_valid = False
            message = "ይህ ትራንዛክሽን ቁጥር አስቀድሞ ተረጋግጦ ጥቅም ላይ ውሏል።"
            suggestions = ["አዲስ ትራንዛክሽን ቁጥር ያስገቡ።"]
        else:
            cur.execute("UPDATE applications SET transaction_validated = TRUE WHERE transaction_id = ?", (transaction_id,))
            conn.commit()
            if cur.rowcount == 0:
                is_valid = False
                message = "ትራንዛክሽን ቁጥሩ ትክክል ቢሆንም በምንም ጥያቄ ላይ አልተገኘም።"
                suggestions = ["ትራንዛክሽን ቁጥሩን በትኬት ጥያቄ ቅጽ ላይ መሙላትዎን ያረጋግጡ።"]

    conn.close()
    return jsonify({"valid": is_valid, "message": message, "suggestions": suggestions})

@app.errorhandler(404)
def page_not_found(e):
    return render_template('404.html'), 404

if __name__ == '__main__':
    app.run(debug=True)