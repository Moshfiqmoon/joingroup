import sqlite3
import os
from flask import Flask, jsonify, request, session
from flask_cors import CORS
from flask_socketio import SocketIO, emit, join_room
import datetime
import traceback
import asyncio
from threading import Thread

# Pyrogram imports only
from pyrogram import Client, filters
from pyrogram.types import ChatJoinRequest
from pyrogram import filters as pyro_filters

from db import init_db
import config

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'change_this_secret_key')
CORS(app, origins=[
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://192.168.1.3:3000",
    "https://autojoin-d569.onrender.com",
    "https://your-frontend-domain.onrender.com"
], supports_credentials=True)
socketio = SocketIO(app, async_mode='threading', cors_allowed_origins=[
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://192.168.1.3:3000",
    "https://autojoin-d569.onrender.com",
    "https://your-frontend-domain.onrender.com"
])

DB_NAME = 'users.db'

# Ensure DB tables exist
init_db()

# Pyrogram Bot Setup
BOT_TOKEN = os.environ.get('BOT_TOKEN', config.BOT_TOKEN)
API_ID = int(os.environ.get('API_ID', config.API_ID))
API_HASH = os.environ.get('API_HASH', config.API_HASH)
CHAT_ID = int(os.environ.get('CHAT_ID', config.CHAT_ID))

pyro_app = Client(
    "AutoApproveBot",
    bot_token=BOT_TOKEN,
    api_id=API_ID,
    api_hash=API_HASH
)

WELCOME_TEXT = getattr(config, "WELCOME_TEXT", "🎉 Hi {mention}, you are now a member of {title}!")

@pyro_app.on_chat_join_request(pyro_filters.chat(CHAT_ID))
async def approve_and_dm(client: Client, join_request: ChatJoinRequest):
    try:
        user = join_request.from_user
        chat = join_request.chat
        
        print(f"🎯 Join request received from: {user.first_name} ({user.id}) in {chat.title}")

        await client.approve_chat_join_request(chat.id, user.id)
        print(f"✅ Approved: {user.first_name} ({user.id}) in {chat.title}")

        # Add user to DB
        full_name = f"{user.first_name or ''} {user.last_name or ''}".strip()
        username = user.username or ''
        join_date = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        invite_link = None  # Pyrogram does not provide invite_link in join request
        add_user(user.id, full_name, username, join_date, invite_link)

        try:
            await client.send_message(
                user.id,
                WELCOME_TEXT.format(mention=user.mention, title=chat.title)
            )
            print(f"📨 DM sent to {user.first_name} ({user.id})")
        except Exception as e:
            print(f"❌ Failed to send DM to {user.first_name} ({user.id}): {e}")
    except Exception as e:
        print(f"❌ Error in approve_and_dm: {e}")
        import traceback
        traceback.print_exc()

def run_pyrogram_bot():
    """Start the Pyrogram bot in a separate thread"""
    try:
        print("🔥 Starting Pyrogram bot...")
        # Set up event loop for this thread
        import asyncio
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        # Run the bot with proper async context
        loop.run_until_complete(pyro_app.start())
        print("✅ Pyrogram bot started successfully")
        
        # Keep the bot running
        loop.run_forever()
    except Exception as e:
        print(f"❌ Pyrogram bot error: {e}")
        import traceback
        traceback.print_exc()

# Start Pyrogram bot in background thread
pyro_thread = Thread(target=run_pyrogram_bot, daemon=True)
pyro_thread.start()

# --- Database helpers ---
def get_all_users():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('SELECT user_id, full_name, username, join_date, invite_link, photo_url, label FROM users')
    users = c.fetchall()
    conn.close()
    return users

def get_total_users():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('SELECT COUNT(*) FROM users')
    total = c.fetchone()[0]
    conn.close()
    return total

def get_messages_for_user(user_id, limit=100):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('SELECT sender, message, timestamp FROM messages WHERE user_id = ? ORDER BY id ASC LIMIT ?', (user_id, limit))
    messages = c.fetchall()
    conn.close()
    return messages

def save_message(user_id, sender, message):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('INSERT INTO messages (user_id, sender, message, timestamp) VALUES (?, ?, ?, ?)',
              (user_id, sender, message, datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
    conn.commit()
    conn.close()

def add_user(user_id, full_name, username, join_date, invite_link, photo_url=None, label=None):
    try:
        print(f"🔍 Adding user to database: {user_id} - {full_name}")
        conn = sqlite3.connect(DB_NAME)
        c = conn.cursor()
        c.execute('INSERT OR IGNORE INTO users (user_id, full_name, username, join_date, invite_link, photo_url, label) VALUES (?, ?, ?, ?, ?, ?, ?)', (user_id, full_name, username, join_date, invite_link, photo_url, label))
        conn.commit()
        conn.close()
        print(f"✅ User {user_id} added to database successfully")
    except Exception as e:
        print(f"❌ Error adding user {user_id} to database: {e}")
        import traceback
        traceback.print_exc()

def get_active_users(minutes=60):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    since = (datetime.datetime.now() - datetime.timedelta(minutes=minutes)).strftime('%Y-%m-%d %H:%M:%S')
    c.execute('SELECT COUNT(DISTINCT user_id) FROM messages WHERE timestamp >= ?', (since,))
    count = c.fetchone()[0]
    conn.close()
    return count

def get_total_messages():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('SELECT COUNT(*) FROM messages')
    count = c.fetchone()[0]
    conn.close()
    return count

def get_new_joins_today():
    today = datetime.datetime.now().strftime('%Y-%m-%d')
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('SELECT COUNT(*) FROM users WHERE join_date LIKE ?', (f'{today}%',))
    count = c.fetchone()[0]
    conn.close()
    return count

def get_user_online_status(user_id, minutes=5):
    """Check if user has been active in the last N minutes"""
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    since = (datetime.datetime.now() - datetime.timedelta(minutes=minutes)).strftime('%Y-%m-%d %H:%M:%S')
    c.execute('SELECT 1 FROM messages WHERE user_id = ? AND timestamp >= ? LIMIT 1', (user_id, since))
    is_online = c.fetchone() is not None
    conn.close()
    return is_online

# --- Flask API Endpoints ---
@app.route('/dashboard-users')
def dashboard_users():
    try:
        page = int(request.args.get('page', 1))
        page_size = int(request.args.get('page_size', 10))
        offset = (page - 1) * page_size

        conn = sqlite3.connect(DB_NAME)
        c = conn.cursor()
        c.execute('SELECT COUNT(*) FROM users')
        total = c.fetchone()[0]
        c.execute('SELECT user_id, full_name, username, join_date, invite_link, photo_url, label FROM users ORDER BY join_date DESC LIMIT ? OFFSET ?', (page_size, offset))
        users = c.fetchall()
        conn.close()

        users_with_status = []
        for u in users:
            is_online = get_user_online_status(u[0], 5)
            users_with_status.append({
                'user_id': u[0],
                'full_name': u[1],
                'username': u[2],
                'join_date': u[3],
                'invite_link': u[4],
                'photo_url': u[5],
                'is_online': is_online,
                'label': u[6]
            })

        return jsonify({
            'users': users_with_status,
            'total': total,
            'page': page,
            'page_size': page_size
        })
    except Exception as e:
        print(f"Error in dashboard-users: {e}")
        return jsonify({
            'users': [],
            'total': 0,
            'page': 1,
            'page_size': 10,
            'error': str(e)
        }), 500

@app.route('/dashboard-stats')
def dashboard_stats():
    try:
        total_users = get_total_users()
        active_users = get_active_users()
        total_messages = get_total_messages()
        new_joins_today = get_new_joins_today()
        return jsonify({
            'total_users': total_users,
            'active_users': active_users,
            'total_messages': total_messages,
            'new_joins_today': new_joins_today
        })
    except Exception as e:
        print(f"Error in dashboard-stats: {e}")
        return jsonify({
            'total_users': 0,
            'active_users': 0,
            'total_messages': 0,
            'new_joins_today': 0,
            'error': str(e)
        }), 500

@app.route('/chat/<int:user_id>/messages')
def chat_messages(user_id):
    messages = get_messages_for_user(user_id)
    return jsonify([
        [sender, message, timestamp] for sender, message, timestamp in messages
    ])

@app.route('/get_channel_invite_link', methods=['GET'])
def get_channel_invite_link():
    try:
        # Simplified version - return a placeholder
        return jsonify({'invite_link': 'https://t.me/+mEcMgPqw3xphODM1'})
    except Exception as e:
        print(f"Error getting invite link: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/chat/<int:user_id>', methods=['POST'])
def chat_send(user_id):
    print(f"DEBUG: Received request for user {user_id}")
    
    message = request.form.get('message')
    files = request.files.getlist('files')
    sent = False
    response = {'status': 'error', 'message': 'No message or files sent'}

    # Handle text message
    if message:
        print(f"DEBUG: Processing text message")
        save_message(user_id, 'admin', message)
        sent = True
        response = {'status': 'success', 'message': 'Message sent (simulated)'}
        print(f"DEBUG: Message sent successfully")

    # Handle files (simplified)
    if files and len(files) > 0:
        print(f"DEBUG: Processing files")
        for file in files:
            filename = file.filename
            print(f"DEBUG: Received file: {filename}")
            save_message(user_id, 'admin', f"[file]{filename}")
        sent = True
        response = {'status': 'success', 'message': 'Files processed (simulated)'}

    # Emit socket event and return response
    print(f"DEBUG: Final response: {response}")
    socketio.emit('new_message', {'user_id': user_id}, room='chat_' + str(user_id))
    
    if sent:
        return jsonify(response), 200
    else:
        return jsonify(response), 500

@app.route('/send_one', methods=['POST'])
def send_one():
    user_id = request.form.get('user_id')
    message = request.form.get('message')
    if not user_id or not message:
        return {'status': 'error', 'msg': 'Missing user_id or message'}, 400
    save_message(int(user_id), 'admin', message)
    socketio.emit('new_message', {'user_id': int(user_id)}, room='chat_' + str(user_id))
    return {'status': 'ok'}

@app.route('/send_all', methods=['POST'])
def send_all():
    message = request.form.get('message')
    if not message:
        return {'status': 'error', 'msg': 'Missing message'}, 400
    users = get_all_users()
    for u in users:
        save_message(u[0], 'admin', message)
        socketio.emit('new_message', {'user_id': u[0]}, room='chat_' + str(u[0]))
    return {'status': 'ok', 'count': len(users)}

@app.route('/user/<int:user_id>/label', methods=['POST'])
def set_user_label(user_id):
    label = request.json.get('label')
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('UPDATE users SET label = ? WHERE user_id = ?', (label, user_id))
    conn.commit()
    conn.close()
    return jsonify({'status': 'ok', 'user_id': user_id, 'label': label})

@socketio.on('join')
def on_join(data):
    room = data.get('room')
    join_room(room)

@app.route('/')
def health_check():
    return jsonify({
        'status': 'ok',
        'message': 'Telegram Bot API is running',
        'timestamp': datetime.datetime.now().isoformat()
    })

@app.route('/health')
def health():
    return jsonify({
        'status': 'healthy',
        'api': 'running',
        'database': 'connected' if os.path.exists(DB_NAME) else 'not_found'
    })

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5001))
    print(f"🚀 Starting Simplified Telegram Bot API on port {port}")
    print(f"🌐 API URL: https://joingroup-8835.onrender.com")
    print(f"🔥 Pyrogram bot will start in background")
    socketio.run(app, port=port, debug=False, host='0.0.0.0', allow_unsafe_werkzeug=True) 
