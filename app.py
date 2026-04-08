from flask import Flask, render_template, request, jsonify, session
import os
import imaplib
import email
from email.header import decode_header

app = Flask(__name__)
# Secret key for secure login sessions
app.secret_key = os.environ.get('SECRET_KEY', 'default_cyber_secret_123')

# Admin & IMAP Credentials
ADMIN_USER = os.environ.get('ADMIN_USER')
ADMIN_PASS = os.environ.get('ADMIN_PASS')
IMAP_USER = os.environ.get('IMAP_USER')
IMAP_PASS = os.environ.get('IMAP_PASS')

# UPDATE: Switched to Gmail's IMAP server to bypass Outlook's block
IMAP_SERVER = "imap.gmail.com"

def is_admin():
    return session.get('logged_in') is True

def decode_mime_words(s):
    """Helper function to decode weirdly formatted email subjects"""
    if not s: return "(No Subject)"
    decoded_words = decode_header(s)
    try:
        return ''.join([
            word.decode(encoding or 'utf-8') if isinstance(word, bytes) else word
            for word, encoding in decoded_words
        ])
    except:
        return str(s)

@app.route('/')
def index():
    return render_template('index.html')

# --- Admin Auth Routes ---
@app.route('/api/auth/login', methods=['POST'])
def login():
    data = request.json
    if data.get('username') == ADMIN_USER and data.get('password') == ADMIN_PASS:
        session['logged_in'] = True
        return jsonify({"success": True})
    return jsonify({"success": False, "error": "Invalid credentials"}), 401

@app.route('/api/auth/logout', methods=['POST'])
def logout():
    session.pop('logged_in', None)
    return jsonify({"success": True})

@app.route('/api/auth/status')
def auth_status():
    return jsonify({"logged_in": is_admin()})

# --- Custom IMAP Inbox Routes ---
@app.route('/api/account')
def get_account():
    if not is_admin(): return jsonify({"error": "Unauthorized"}), 401
    return jsonify({"email": IMAP_USER})

@app.route('/api/messages')
def get_messages():
    if not is_admin(): return jsonify({"error": "Unauthorized"}), 401
    try:
        # Securely connect to Gmail
        mail = imaplib.IMAP4_SSL(IMAP_SERVER)
        mail.login(IMAP_USER, IMAP_PASS)
        mail.select("inbox")
        
        # Grab the 15 most recent emails
        status, messages = mail.search(None, "ALL")
        if not messages[0]:
            return jsonify([])
            
        email_ids = messages[0].split()[-15:] 
        email_ids.reverse() 
        
        msg_list = []
        for e_id in email_ids:
            # Peek at headers only (so we don't accidentally mark them as read)
            res, msg_data = mail.fetch(e_id, "(BODY.PEEK[HEADER.FIELDS (SUBJECT FROM DATE)])")
            for response_part in msg_data:
                if isinstance(response_part, tuple):
                    msg = email.message_from_bytes(response_part[1])
                    msg_list.append({
                        "id": e_id.decode(),
                        "subject": decode_mime_words(msg["Subject"]),
                        "from": decode_mime_words(msg["From"]),
                        "date": decode_mime_words(msg["Date"])
                    })
        mail.logout()
        return jsonify(msg_list)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/read')
def read_message():
    if not is_admin(): return jsonify({"error": "Unauthorized"}), 401
    msg_id = request.args.get('id')
    try:
        mail = imaplib.IMAP4_SSL(IMAP_SERVER)
        mail.login(IMAP_USER, IMAP_PASS)
        mail.select("inbox")
        
        # Fetch the full raw email
        res, msg_data = mail.fetch(msg_id, "(RFC822)")
        raw_email = msg_data[0][1]
        msg = email.message_from_bytes(raw_email)
        
        html_body, text_body = "", ""
        
        # Decrypt HTML and Plain Text from the email package
        if msg.is_multipart():
            for part in msg.walk():
                content_type = part.get_content_type()
                if "attachment" not in str(part.get("Content-Disposition")):
                    try:
                        body = part.get_payload(decode=True).decode(errors='ignore')
                        if content_type == "text/plain": text_body += body
                        elif content_type == "text/html": html_body += body
                    except: pass
        else:
            try:
                body = msg.get_payload(decode=True).decode(errors='ignore')
                if msg.get_content_type() == "text/html": html_body = body
                else: text_body = body
            except: pass
            
        mail.logout()
        return jsonify({
            "subject": decode_mime_words(msg["Subject"]),
            "from": decode_mime_words(msg["From"]),
            "htmlBody": html_body,
            "textBody": text_body
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
