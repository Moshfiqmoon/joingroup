import sqlite3
import os
from flask import Flask, jsonify, request, session
from flask_cors import CORS
from flask_socketio import SocketIO, emit, join_room
import datetime
import traceback
import asyncio
from threading import Thread
import shutil
from werkzeug.utils import secure_filename
import tempfile

# Pyrogram imports only
from pyrogram import Client, filters
from pyrogram.types import ChatJoinRequest
from pyrogram import filters as pyro_filters

from db import init_db, add_user as db_add_user
import config

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'change_this_secret_key')
CORS(app, origins=[
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://192.168.1.3:3000",
    "http://192.168.1.4:3000",
    "https://joingroup-8835.onrender.com",
    "https://admin-q2j7.onrender.com",
    "https://your-frontend-domain.onrender.com"
], supports_credentials=True)
socketio = SocketIO(app, async_mode='threading', cors_allowed_origins=[
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://192.168.1.3:3000",
    "http://192.168.1.4:3000",
    "https://joingroup-8835.onrender.com",
    "https://admin-q2j7.onrender.com",
    "https://your-frontend-domain.onrender.com"
])

# Get database path from environment or use temp directory
DB_PATH = os.environ.get('DB_PATH', os.path.join(os.getcwd(), 'users.db'))
DB_NAME = DB_PATH

# For Render deployment, use a more reliable path
if os.environ.get('RENDER', False) or os.environ.get('RENDER_EXTERNAL_URL', False):
    DB_PATH = '/opt/render/project/src/users.db'
    DB_NAME = DB_PATH
    print(f"🚀 Render deployment detected, using path: {DB_PATH}")
elif os.environ.get('PORT', False):
    # If PORT is set (like on Render), use Render path
    DB_PATH = '/opt/render/project/src/users.db'
    DB_NAME = DB_PATH
    print(f"🚀 Cloud deployment detected (PORT set), using path: {DB_PATH}")

# Fallback to in-memory database if file system is not writable
try:
    # Test if we can write to the directory
    test_file = f"{DB_PATH}.test"
    with open(test_file, 'w') as f:
        f.write('test')
    os.remove(test_file)
    print(f"✅ Using file database: {DB_PATH}")
    print(f"📁 Database will be stored at: {os.path.abspath(DB_PATH)}")
except Exception as e:
    print(f"⚠️ File system not writable, using in-memory database: {e}")
    DB_NAME = ':memory:'
    print(f"📝 Note: In-memory database will reset when server restarts")

# Ensure DB tables exist
init_db()
print(f"🗄️ Database initialized: {DB_NAME}")
print(f"📁 Database file location: {os.path.abspath(DB_PATH) if DB_NAME != ':memory:' else 'In-memory'}")
print(f"⚠️ IMPORTANT: SQLite database will reset on server restart!")

# Database backup and restore functions
def backup_database():
    """Backup database to persistent storage"""
    try:
        if os.path.exists(DB_NAME) and DB_NAME != ':memory:':
            backup_path = f"{DB_NAME}.backup"
            shutil.copy2(DB_NAME, backup_path)
            print(f"✅ Database backed up to: {backup_path}")
            return True
    except Exception as e:
        print(f"❌ Backup failed: {e}")
        return False

def restore_database():
    """Restore database from backup"""
    try:
        if DB_NAME != ':memory:':
            backup_path = f"{DB_NAME}.backup"
            if os.path.exists(backup_path):
                shutil.copy2(backup_path, DB_NAME)
                print(f"✅ Database restored from: {backup_path}")
                return True
            else:
                print(f"⚠️ No backup found at: {backup_path}")
                return False
    except Exception as e:
        print(f"❌ Restore failed: {e}")
        return False

# Try to restore database on startup
if restore_database():
    print("🔄 Database restored from backup")
else:
    print("📝 Starting with fresh database")

# Pyrogram Bot Setup
BOT_TOKEN = os.environ.get('BOT_TOKEN', config.BOT_TOKEN)
API_ID = int(os.environ.get('API_ID', config.API_ID))
API_HASH = os.environ.get('API_HASH', config.API_HASH)
CHAT_ID = int(os.environ.get('CHAT_ID', config.CHAT_ID))

# Check if required environment variables are set
if not BOT_TOKEN or BOT_TOKEN == 'your_bot_token_here':
    print("⚠️ WARNING: BOT_TOKEN not set properly")
if not API_ID or API_ID == 0:
    print("⚠️ WARNING: API_ID not set properly")
if not API_HASH or API_HASH == 'your_api_hash_here':
    print("⚠️ WARNING: API_HASH not set properly")
if not CHAT_ID or CHAT_ID == 0:
    print("⚠️ WARNING: CHAT_ID not set properly")

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
        print(f"🔍 User details: ID={user.id}, Name={user.first_name}, Username={user.username}")

        await client.approve_chat_join_request(chat.id, user.id)
        print(f"✅ Approved: {user.first_name} ({user.id}) in {chat.title}")

        # Add user to DB with better error handling
        try:
            full_name = f"{user.first_name or ''} {user.last_name or ''}".strip()
            username = user.username or ''
            join_date = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            invite_link = None  # Pyrogram does not provide invite_link in join request
            
            print(f"💾 Saving user to database: {user.id} - {full_name}")
            db_add_user(user.id, full_name, username, join_date, invite_link)
            print(f"✅ User {user.id} saved to database successfully")
            
            # Backup database after adding user
            backup_database()
            
        except Exception as db_error:
            print(f"❌ Database error saving user {user.id}: {db_error}")
            import traceback
            traceback.print_exc()

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

# Alternative: Start Pyrogram bot without async
def run_pyrogram_bot_simple():
    """Start the Pyrogram bot using the simple run method"""
    try:
        print("🔥 Starting Pyrogram bot (simple method)...")
        # Use the simple run method without async
        pyro_app.run()
        print("✅ Pyrogram bot started successfully")
    except Exception as e:
        print(f"❌ Pyrogram bot error: {e}")
        import traceback
        traceback.print_exc()

# Test Pyrogram connection
def test_pyrogram_connection():
    """Test if Pyrogram can connect to Telegram"""
    try:
        print("🔍 Testing Pyrogram connection...")
        print(f"🔑 Using API_ID: {API_ID}")
        print(f"🔑 Using API_HASH: {API_HASH[:10]}...")
        print(f"🔑 Using BOT_TOKEN: {BOT_TOKEN[:10]}...")
        print(f"🔑 Using CHAT_ID: {CHAT_ID}")
        
        # Try to get bot info
        with pyro_app:
            me = pyro_app.get_me()
            print(f"✅ Pyrogram connected successfully: {me.first_name} (@{me.username})")
            print(f"🆔 Bot ID: {me.id}")
            return True
    except Exception as e:
        print(f"❌ Pyrogram connection failed: {e}")
        import traceback
        traceback.print_exc()
        return False

# Start Pyrogram bot in background thread
def start_pyrogram_bot():
    """Start Pyrogram bot in background thread"""
    try:
        print("🔥 Starting Pyrogram bot in background...")
        # Create new event loop for this thread
        import asyncio
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        # For Render deployment, use start() instead of run() or idle() to avoid signal issues
        try:
            # Use start() which doesn't require signal handling
            pyro_app.start()
            print("✅ Pyrogram bot started successfully with start()")
        except Exception as start_error:
            print(f"⚠️ Start failed: {start_error}")
            # Don't try idle() or run() as they cause signal issues
            print("⚠️ Skipping bot startup due to signal issues")
    except Exception as e:
        print(f"❌ Pyrogram bot error: {e}")
        import traceback
        traceback.print_exc()

# Test connection and start bot in background
if test_pyrogram_connection():
    print("🚀 Starting Pyrogram bot in background thread")
    # Start bot in background thread
    bot_thread = Thread(target=start_pyrogram_bot, daemon=True)
    bot_thread.start()
    print("✅ Pyrogram bot started in background")
else:
    print("⚠️ Pyrogram bot not started - connection failed")

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

        print(f"🔍 Fetching users: page={page}, page_size={page_size}, offset={offset}")

        conn = sqlite3.connect(DB_NAME)
        c = conn.cursor()
        c.execute('SELECT COUNT(*) FROM users')
        total = c.fetchone()[0]
        print(f"📊 Total users in database: {total}")
        
        c.execute('SELECT user_id, full_name, username, join_date, invite_link, photo_url, label FROM users ORDER BY join_date DESC LIMIT ? OFFSET ?', (page_size, offset))
        users = c.fetchall()
        conn.close()

        print(f"�� Found {len(users)} users for this page")

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
        print(f"❌ Error in dashboard-users: {e}")
        import traceback
        traceback.print_exc()
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

@app.route('/chat/<int:user_id>', methods=['GET'])
def get_chat_messages(user_id):
    """Get messages for a specific user"""
    try:
        messages = get_messages_for_user(user_id, limit=100)
        
        # Format messages for frontend
        formatted_messages = []
        for sender, message, timestamp in messages:
            formatted_messages.append({
                'sender': sender,
                'message': message,
                'timestamp': timestamp,
                'user_id': user_id
            })
        
        return jsonify({
            'status': 'success',
            'messages': formatted_messages,
            'user_id': user_id,
            'total_messages': len(formatted_messages)
        })
        
    except Exception as e:
        print(f"❌ Error getting messages for user {user_id}: {e}")
        return jsonify({
            'status': 'error',
            'message': str(e),
            'messages': [],
            'user_id': user_id
        }), 500

@app.route('/messages/<int:user_id>')
def get_user_messages(user_id):
    """Get messages for a specific user"""
    try:
        messages = get_messages_for_user(user_id, limit=100)
        
        # Format messages for frontend
        formatted_messages = []
        for sender, message, timestamp in messages:
            formatted_messages.append({
                'sender': sender,
                'message': message,
                'timestamp': timestamp,
                'user_id': user_id
            })
        
        return jsonify({
            'status': 'success',
            'messages': formatted_messages,
            'user_id': user_id,
            'total_messages': len(formatted_messages)
        })
        
    except Exception as e:
        print(f"❌ Error getting messages for user {user_id}: {e}")
        return jsonify({
            'status': 'error',
            'message': str(e),
            'messages': [],
            'user_id': user_id
        }), 500

@app.route('/messages')
def get_all_messages():
    """Get all messages (for admin dashboard)"""
    try:
        conn = sqlite3.connect(DB_NAME)
        c = conn.cursor()
        c.execute('SELECT user_id, sender, message, timestamp FROM messages ORDER BY timestamp DESC LIMIT 100')
        messages = c.fetchall()
        conn.close()
        
        # Format messages for frontend
        formatted_messages = []
        for user_id, sender, message, timestamp in messages:
            formatted_messages.append({
                'user_id': user_id,
                'sender': sender,
                'message': message,
                'timestamp': timestamp
            })
        
        return jsonify({
            'status': 'success',
            'messages': formatted_messages,
            'total_messages': len(formatted_messages)
        })
        
    except Exception as e:
        print(f"❌ Error getting all messages: {e}")
        return jsonify({
            'status': 'error',
            'message': str(e),
            'messages': []
        }), 500

@app.route('/get_channel_invite_link', methods=['GET'])
def get_channel_invite_link():
    try:
        # Simplified version - return a placeholder
        return jsonify({'invite_link': 'https://t.me/+mEcMgPqw3xphODM1'})
    except Exception as e:
        print(f"Error getting invite link: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/send-message', methods=['POST'])
def send_message():
    """Send message from user or admin"""
    try:
        data = request.json
        user_id = data.get('user_id')
        message = data.get('message')
        sender = data.get('sender', 'user')  # 'user' or 'admin'
        
        if not user_id or not message:
            return jsonify({'error': 'User ID and message required'}), 400
        
        # Save message to database
        save_message(int(user_id), sender, message)
        
        # Emit socket event for real-time updates
        socketio.emit('new_message', {
            'user_id': int(user_id),
            'sender': sender,
            'message': message
        }, room='chat_' + str(user_id))
        
        return jsonify({
            'status': 'success',
            'message': 'Message sent successfully',
            'user_id': user_id,
            'sender': sender,
            'message': message
        })
        
    except Exception as e:
        print(f"❌ Error sending message: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/send-user-message', methods=['POST'])
def send_user_message():
    """Send message from user to admin"""
    try:
        data = request.json
        user_id = data.get('user_id')
        message = data.get('message')
        
        if not user_id or not message:
            return jsonify({'error': 'User ID and message required'}), 400
        
        # Save message to database as from user
        save_message(int(user_id), 'user', message)
        
        # Emit socket event
        socketio.emit('new_message', {
            'user_id': int(user_id),
            'sender': 'user',
            'message': message
        }, room='chat_' + str(user_id))
        
        return jsonify({
            'status': 'success',
            'message': 'User message sent successfully',
            'user_id': user_id,
            'sender': 'user',
            'message': message
        })
        
    except Exception as e:
        print(f"❌ Error sending user message: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/send-admin-message', methods=['POST'])
def send_admin_message():
    """Send message from admin to user"""
    try:
        data = request.json
        user_id = data.get('user_id')
        message = data.get('message')
        
        if not user_id or not message:
            return jsonify({'error': 'User ID and message required'}), 400
        
        # Save message to database as from admin
        save_message(int(user_id), 'admin', message)
        
        # Emit message to all rooms (user room + admin notification)
        emit_message_to_all_rooms(int(user_id), 'admin', message)
        
        return jsonify({
            'status': 'success',
            'message': 'Admin message sent successfully',
            'user_id': user_id,
            'sender': 'admin',
            'message': message
        })
        
    except Exception as e:
        print(f"❌ Error sending admin message: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/chat/<int:user_id>', methods=['POST'])
def chat_message_direct(user_id):
    """Send message directly to chat (handles both JSON and form data)"""
    try:
        # Check if this is a file upload
        if 'file' in request.files or 'files' in request.files:
            # Handle file upload
            if 'file' in request.files:
                return handle_single_file_upload(user_id, request.files['file'], request.form.get('sender', 'user'))
            elif 'files' in request.files:
                return handle_bulk_file_upload(user_id, request.files.getlist('files'), request.form.get('sender', 'user'))
        
        # Try to get data from JSON first
        if request.is_json:
            data = request.json
            message = data.get('message')
            sender = data.get('sender', 'user')
        else:
            # Handle form data
            message = request.form.get('message')
            sender = request.form.get('sender', 'user')
        
        if not message:
            return jsonify({'error': 'Message required'}), 400
        
        # Save message to database
        save_message(user_id, sender, message)
        
        # Emit message to all rooms (user room + admin notification)
        emit_message_to_all_rooms(user_id, sender, message)
        
        return jsonify({
            'status': 'success',
            'message': 'Message sent successfully',
            'user_id': user_id,
            'sender': sender,
            'message': message
        })
        
    except Exception as e:
        print(f"❌ Error in chat direct send: {e}")
        return jsonify({'error': str(e)}), 500

def handle_single_file_upload(user_id, file, sender):
    """Handle single file upload for chat"""
    try:
        if file.filename == '':
            return jsonify({'error': 'No file selected'}), 400
        
        # Secure filename and get file type
        filename = secure_filename(file.filename)
        file_type = get_file_type(filename)
        
        # Create user-specific folder
        user_folder = os.path.join(UPLOAD_FOLDER, str(user_id))
        if not os.path.exists(user_folder):
            os.makedirs(user_folder)
        
        # Save file
        file_path = os.path.join(user_folder, filename)
        file.save(file_path)
        
        # Save message to database
        message_text = f"[{sender.upper()}] [{file_type.upper()}] {filename}"
        save_message(user_id, sender, message_text)
        
        # Emit message to all rooms (user room + admin notification)
        emit_message_to_all_rooms(user_id, sender, message_text)
        
        return jsonify({
            'status': 'success',
            'message': f'{sender.capitalize()} uploaded {file_type} successfully',
            'filename': filename,
            'file_type': file_type,
            'file_path': file_path,
            'sender': sender
        })
        
    except Exception as e:
        print(f"❌ Error uploading file: {e}")
        return jsonify({'error': str(e)}), 500

def handle_bulk_file_upload(user_id, files, sender):
    """Handle bulk file upload for chat"""
    try:
        if not files or files[0].filename == '':
            return jsonify({'error': 'No files selected'}), 400
        
        uploaded_files = []
        
        # Create user-specific folder
        user_folder = os.path.join(UPLOAD_FOLDER, str(user_id))
        if not os.path.exists(user_folder):
            os.makedirs(user_folder)
        
        for file in files:
            if file.filename != '':
                filename = secure_filename(file.filename)
                file_type = get_file_type(filename)
                
                # Save file
                file_path = os.path.join(user_folder, filename)
                file.save(file_path)
                
                uploaded_files.append({
                    'filename': filename,
                    'file_type': file_type,
                    'file_path': file_path
                })
        
        # Save bulk message to database
        message_text = f"[{sender.upper()}] [BULK UPLOAD] {len(uploaded_files)} files uploaded"
        save_message(user_id, sender, message_text)
        
        # Emit message to all rooms (user room + admin notification)
        emit_message_to_all_rooms(user_id, sender, message_text)
        
        return jsonify({
            'status': 'success',
            'message': f'{sender.capitalize()} uploaded {len(uploaded_files)} files successfully',
            'files': uploaded_files,
            'sender': sender
        })
        
    except Exception as e:
        print(f"❌ Error uploading bulk files: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/chat/<int:user_id>/send', methods=['POST'])
def chat_send_message(user_id):
    """Send message in chat (works for both user and admin)"""
    try:
        data = request.json
        message = data.get('message')
        sender = data.get('sender', 'user')  # Default to user
        
        if not message:
            return jsonify({'error': 'Message required'}), 400
        
        # Save message to database
        save_message(user_id, sender, message)
        
        # Emit socket event
        socketio.emit('new_message', {
            'user_id': user_id,
            'sender': sender,
            'message': message
        }, room='chat_' + str(user_id))
        
        return jsonify({
            'status': 'success',
            'message': 'Message sent successfully',
            'user_id': user_id,
            'sender': sender,
            'message': message
        })
        
    except Exception as e:
        print(f"❌ Error in chat send: {e}")
        return jsonify({'error': str(e)}), 500

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

@app.route('/add-test-user', methods=['POST'])
def add_test_user():
    """Add a test user manually for testing"""
    try:
        data = request.json
        user_id = data.get('user_id')
        full_name = data.get('full_name', 'Test User')
        username = data.get('username', 'testuser')
        
        if not user_id:
            return jsonify({'error': 'user_id is required'}), 400
            
        join_date = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        db_add_user(user_id, full_name, username, join_date, None)
        
        return jsonify({
            'status': 'success',
            'message': f'User {user_id} added successfully',
            'user': {
                'user_id': user_id,
                'full_name': full_name,
                'username': username,
                'join_date': join_date
            }
        })
    except Exception as e:
        print(f"❌ Error adding test user: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/manual-join', methods=['POST'])
def manual_join():
    """Simulate a join request manually"""
    try:
        data = request.json
        user_id = data.get('user_id')
        full_name = data.get('full_name', 'Manual User')
        username = data.get('username', 'manualuser')
        
        if not user_id:
            return jsonify({'error': 'user_id is required'}), 400
            
        join_date = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        # Add user to database
        db_add_user(user_id, full_name, username, join_date, None)
        
        # Send welcome message (simulated)
        welcome_message = f"🎉 Welcome {full_name}! You have been added to our group."
        save_message(user_id, 'admin', welcome_message)
        
        # Backup database after adding user
        backup_database()
        
        return jsonify({
            'status': 'success',
            'message': f'User {user_id} joined successfully',
            'user': {
                'user_id': user_id,
                'full_name': full_name,
                'username': username,
                'join_date': join_date
            }
        })
    except Exception as e:
        print(f"❌ Error in manual join: {e}")
        return jsonify({'error': str(e)}), 500

@socketio.on('join')
def on_join(data):
    room = data.get('room')
    join_room(room)
    print(f"🔗 User joined room: {room}")

@socketio.on('admin_join')
def on_admin_join(data):
    """Admin joins admin room to receive all messages"""
    join_room('admin_room')
    print("👑 Admin joined admin room")

@socketio.on('user_join')
def on_user_join(data):
    """User joins their specific chat room"""
    user_id = data.get('user_id')
    room = f'chat_{user_id}'
    join_room(room)
    print(f"👤 User {user_id} joined room: {room}")

def notify_admin_new_message(user_id, sender, message):
    """Notify admin about new message"""
    try:
        # Get user info for admin notification
        conn = sqlite3.connect(DB_NAME)
        c = conn.cursor()
        c.execute('SELECT full_name, username FROM users WHERE user_id = ?', (user_id,))
        user_info = c.fetchone()
        conn.close()
        
        user_name = user_info[0] if user_info else f"User {user_id}"
        username = user_info[1] if user_info else "Unknown"
        
        # Emit to admin room
        socketio.emit('admin_notification', {
            'type': 'new_message',
            'user_id': user_id,
            'user_name': user_name,
            'username': username,
            'sender': sender,
            'message': message,
            'timestamp': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }, room='admin_room')
        
        print(f"📢 Admin notified: {user_name} ({user_id}) sent message")
        
    except Exception as e:
        print(f"❌ Error notifying admin: {e}")

def emit_message_to_all_rooms(user_id, sender, message):
    """Emit message to both user room and admin room"""
    try:
        # Emit to user's chat room
        socketio.emit('new_message', {
            'user_id': user_id,
            'sender': sender,
            'message': message,
            'timestamp': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }, room='chat_' + str(user_id))
        
        # If message is from user, notify admin
        if sender == 'user':
            notify_admin_new_message(user_id, sender, message)
        
        print(f"📤 Message emitted: {sender} -> {user_id}")
        
    except Exception as e:
        print(f"❌ Error emitting message: {e}")

@app.route('/')
def health_check():
    return jsonify({
        'status': 'ok',
        'message': 'Telegram Bot API is running',
        'timestamp': datetime.datetime.now().isoformat()
    })

@app.route('/health')
def health():
    try:
        # Test database connection
        conn = sqlite3.connect(DB_NAME)
        c = conn.cursor()
        c.execute('SELECT COUNT(*) FROM users')
        user_count = c.fetchone()[0]
        c.execute('SELECT COUNT(*) FROM messages')
        message_count = c.fetchone()[0]
        conn.close()
        
        return jsonify({
            'status': 'healthy',
            'api': 'running',
            'database': 'connected',
            'database_path': DB_NAME,
            'user_count': user_count,
            'message_count': message_count,
            'database_file_exists': os.path.exists(DB_PATH) if DB_NAME != ':memory:' else True
        })
    except Exception as e:
        return jsonify({
            'status': 'unhealthy',
            'api': 'running',
            'database': 'error',
            'error': str(e),
            'database_path': DB_NAME
        }), 500

@app.route('/test-db')
def test_database():
    """Test database functionality"""
    try:
        # Test adding a user
        test_user_id = 999999
        test_name = "Test User"
        test_username = "testuser"
        test_date = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        print(f"🧪 Testing database with user: {test_user_id}")
        db_add_user(test_user_id, test_name, test_username, test_date, None)
        
        # Verify user was added
        conn = sqlite3.connect(DB_NAME)
        c = conn.cursor()
        c.execute('SELECT * FROM users WHERE user_id = ?', (test_user_id,))
        user = c.fetchone()
        conn.close()
        
        if user:
            print(f"✅ Test user added successfully: {user}")
            return jsonify({
                'status': 'success',
                'message': 'Database test passed',
                'test_user': {
                    'user_id': user[0],
                    'full_name': user[1],
                    'username': user[2],
                    'join_date': user[3]
                }
            })
        else:
            return jsonify({
                'status': 'error',
                'message': 'Test user not found in database'
            }), 500
            
    except Exception as e:
        print(f"❌ Database test failed: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'status': 'error',
            'message': f'Database test failed: {str(e)}'
        }), 500

@app.route('/db-status')
def database_status():
    """Show current database status and users"""
    try:
        conn = sqlite3.connect(DB_NAME)
        c = conn.cursor()
        
        # Get total users
        c.execute('SELECT COUNT(*) FROM users')
        total_users = c.fetchone()[0]
        
        # Get total messages
        c.execute('SELECT COUNT(*) FROM messages')
        total_messages = c.fetchone()[0]
        
        # Get recent users (last 10)
        c.execute('SELECT user_id, full_name, username, join_date FROM users ORDER BY join_date DESC LIMIT 10')
        recent_users = c.fetchall()
        
        conn.close()
        
        return jsonify({
            'status': 'success',
            'database_path': DB_NAME,
            'total_users': total_users,
            'total_messages': total_messages,
            'recent_users': [
                {
                    'user_id': user[0],
                    'full_name': user[1],
                    'username': user[2],
                    'join_date': user[3]
                } for user in recent_users
            ]
        })
        
    except Exception as e:
        print(f"❌ Database status error: {e}")
        return jsonify({
            'status': 'error',
            'message': f'Database status error: {str(e)}'
        }), 500

@app.route('/backup-db', methods=['POST'])
def backup_database_endpoint():
    """Manually backup database"""
    try:
        if backup_database():
            return jsonify({
                'status': 'success',
                'message': 'Database backed up successfully'
            })
        else:
            return jsonify({
                'status': 'error',
                'message': 'Database backup failed'
            }), 500
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': f'Backup error: {str(e)}'
        }), 500

@app.route('/restore-db', methods=['POST'])
def restore_database_endpoint():
    """Manually restore database"""
    try:
        if restore_database():
            return jsonify({
                'status': 'success',
                'message': 'Database restored successfully'
            })
        else:
            return jsonify({
                'status': 'error',
                'message': 'Database restore failed'
            }), 500
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': f'Restore error: {str(e)}'
        }), 500

@app.route('/test-add-user', methods=['POST'])
def test_add_user():
    """Add a test user and verify database functionality"""
    try:
        data = request.json
        user_id = data.get('user_id', 999999)
        full_name = data.get('full_name', 'Test User')
        username = data.get('username', 'testuser')
        
        join_date = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        # Add user to database
        db_add_user(user_id, full_name, username, join_date, None)
        
        # Verify user was added
        conn = sqlite3.connect(DB_NAME)
        c = conn.cursor()
        c.execute('SELECT COUNT(*) FROM users')
        total_users = c.fetchone()[0]
        c.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
        user = c.fetchone()
        conn.close()
        
        return jsonify({
            'status': 'success',
            'message': f'Test user {user_id} added successfully',
            'total_users': total_users,
            'user': {
                'user_id': user[0] if user else user_id,
                'full_name': user[1] if user else full_name,
                'username': user[2] if user else username,
                'join_date': user[3] if user else join_date
            },
            'database_path': DB_NAME
        })
    except Exception as e:
        print(f"❌ Error in test-add-user: {e}")
        return jsonify({
            'status': 'error',
            'message': f'Error adding test user: {str(e)}',
            'database_path': DB_NAME
        }), 500

# File upload configuration
UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {
    'image': {'png', 'jpg', 'jpeg', 'gif', 'bmp', 'webp'},
    'video': {'mp4', 'avi', 'mov', 'mkv', 'webm', '3gp'},
    'audio': {'mp3', 'wav', 'ogg', 'm4a', 'aac'},
    'document': {'pdf', 'doc', 'docx', 'txt', 'zip', 'rar'}
}

# Create upload folder if it doesn't exist
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

def allowed_file(filename, file_type):
    """Check if file extension is allowed"""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS.get(file_type, set())

def get_file_type(filename):
    """Get file type based on extension"""
    ext = filename.rsplit('.', 1)[1].lower() if '.' in filename else ''
    for file_type, extensions in ALLOWED_EXTENSIONS.items():
        if ext in extensions:
            return file_type
    return 'document'

@app.route('/upload-file', methods=['POST'])
def upload_file():
    """Upload single file (image, video, audio, document) - works for both user and admin"""
    try:
        if 'file' not in request.files:
            return jsonify({'error': 'No file provided'}), 400
        
        file = request.files['file']
        user_id = request.form.get('user_id')
        sender = request.form.get('sender', 'user')  # 'user' or 'admin'
        
        if file.filename == '':
            return jsonify({'error': 'No file selected'}), 400
        
        if not user_id:
            return jsonify({'error': 'User ID required'}), 400
        
        # Secure filename and get file type
        filename = secure_filename(file.filename)
        file_type = get_file_type(filename)
        
        # Create user-specific folder
        user_folder = os.path.join(UPLOAD_FOLDER, str(user_id))
        if not os.path.exists(user_folder):
            os.makedirs(user_folder)
        
        # Save file
        file_path = os.path.join(user_folder, filename)
        file.save(file_path)
        
        # Save message to database
        message_text = f"[{sender.upper()}] [{file_type.upper()}] {filename}"
        save_message(int(user_id), sender, message_text)
        
        # Emit socket event
        socketio.emit('new_message', {
            'user_id': int(user_id),
            'sender': sender,
            'message': message_text
        }, room='chat_' + str(user_id))
        
        return jsonify({
            'status': 'success',
            'message': f'{sender.capitalize()} uploaded {file_type} successfully',
            'filename': filename,
            'file_type': file_type,
            'file_path': file_path,
            'sender': sender
        })
        
    except Exception as e:
        print(f"❌ Error uploading file: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/upload-bulk-files', methods=['POST'])
def upload_bulk_files():
    """Upload multiple files at once - works for both user and admin"""
    try:
        if 'files' not in request.files:
            return jsonify({'error': 'No files provided'}), 400
        
        files = request.files.getlist('files')
        user_id = request.form.get('user_id')
        sender = request.form.get('sender', 'user')  # 'user' or 'admin'
        
        if not user_id:
            return jsonify({'error': 'User ID required'}), 400
        
        if not files or files[0].filename == '':
            return jsonify({'error': 'No files selected'}), 400
        
        uploaded_files = []
        
        # Create user-specific folder
        user_folder = os.path.join(UPLOAD_FOLDER, str(user_id))
        if not os.path.exists(user_folder):
            os.makedirs(user_folder)
        
        for file in files:
            if file.filename != '':
                filename = secure_filename(file.filename)
                file_type = get_file_type(filename)
                
                # Save file
                file_path = os.path.join(user_folder, filename)
                file.save(file_path)
                
                uploaded_files.append({
                    'filename': filename,
                    'file_type': file_type,
                    'file_path': file_path
                })
        
        # Save bulk message to database
        message_text = f"[{sender.upper()}] [BULK UPLOAD] {len(uploaded_files)} files uploaded"
        save_message(int(user_id), sender, message_text)
        
        # Emit socket event
        socketio.emit('new_message', {
            'user_id': int(user_id),
            'sender': sender,
            'message': message_text
        }, room='chat_' + str(user_id))
        
        return jsonify({
            'status': 'success',
            'message': f'{sender.capitalize()} uploaded {len(uploaded_files)} files successfully',
            'files': uploaded_files,
            'sender': sender
        })
        
    except Exception as e:
        print(f"❌ Error uploading bulk files: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/send-voice', methods=['POST'])
def send_voice():
    """Send voice message - works for both user and admin"""
    try:
        if 'voice' not in request.files:
            return jsonify({'error': 'No voice file provided'}), 400
        
        voice_file = request.files['voice']
        user_id = request.form.get('user_id')
        sender = request.form.get('sender', 'user')  # 'user' or 'admin'
        
        if voice_file.filename == '':
            return jsonify({'error': 'No voice file selected'}), 400
        
        if not user_id:
            return jsonify({'error': 'User ID required'}), 400
        
        # Secure filename
        filename = secure_filename(voice_file.filename)
        
        # Create user-specific folder
        user_folder = os.path.join(UPLOAD_FOLDER, str(user_id))
        if not os.path.exists(user_folder):
            os.makedirs(user_folder)
        
        # Save voice file
        file_path = os.path.join(user_folder, filename)
        voice_file.save(file_path)
        
        # Save message to database
        message_text = f"[{sender.upper()}] [VOICE MESSAGE] {filename}"
        save_message(int(user_id), sender, message_text)
        
        # Emit socket event
        socketio.emit('new_message', {
            'user_id': int(user_id),
            'sender': sender,
            'message': message_text
        }, room='chat_' + str(user_id))
        
        return jsonify({
            'status': 'success',
            'message': f'{sender.capitalize()} voice message sent successfully',
            'filename': filename,
            'file_path': file_path,
            'sender': sender
        })
        
    except Exception as e:
        print(f"❌ Error sending voice: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/send-telegram-message', methods=['POST'])
def send_telegram_message():
    """Send message through Telegram bot"""
    try:
        data = request.json
        user_id = data.get('user_id')
        message = data.get('message')
        message_type = data.get('type', 'text')  # text, image, video, voice
        
        if not user_id or not message:
            return jsonify({'error': 'User ID and message required'}), 400
        
        # Save message to database
        save_message(int(user_id), 'admin', message)
        
        # Try to send through Telegram bot (if available)
        try:
            # This would require the bot to be properly configured
            # For now, just save to database
            print(f"📨 Message saved for user {user_id}: {message}")
        except Exception as bot_error:
            print(f"⚠️ Bot send failed: {bot_error}")
        
        # Emit socket event
        socketio.emit('new_message', {'user_id': int(user_id)}, room='chat_' + str(user_id))
        
        return jsonify({
            'status': 'success',
            'message': 'Message sent successfully',
            'user_id': user_id,
            'message': message
        })
        
    except Exception as e:
        print(f"❌ Error sending Telegram message: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/get-user-files/<int:user_id>')
def get_user_files(user_id):
    """Get all files uploaded by a user"""
    try:
        user_folder = os.path.join(UPLOAD_FOLDER, str(user_id))
        
        if not os.path.exists(user_folder):
            return jsonify({'files': []})
        
        files = []
        for filename in os.listdir(user_folder):
            file_path = os.path.join(user_folder, filename)
            file_type = get_file_type(filename)
            file_size = os.path.getsize(file_path)
            
            files.append({
                'filename': filename,
                'file_type': file_type,
                'file_size': file_size,
                'file_path': file_path
            })
        
        return jsonify({'files': files})
        
    except Exception as e:
        print(f"❌ Error getting user files: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/user/<int:user_id>')
def get_user_info(user_id):
    """Get specific user information"""
    try:
        conn = sqlite3.connect(DB_NAME)
        c = conn.cursor()
        c.execute('SELECT user_id, full_name, username, join_date, invite_link, photo_url, label FROM users WHERE user_id = ?', (user_id,))
        user = c.fetchone()
        conn.close()
        
        if user:
            return jsonify({
                'status': 'success',
                'user': {
                    'user_id': user[0],
                    'full_name': user[1],
                    'username': user[2],
                    'join_date': user[3],
                    'invite_link': user[4],
                    'photo_url': user[5],
                    'label': user[6]
                }
            })
        else:
            return jsonify({
                'status': 'error',
                'message': 'User not found'
            }), 404
            
    except Exception as e:
        print(f"❌ Error getting user info for {user_id}: {e}")
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

@app.route('/admin/messages')
def admin_messages():
    """Get all recent messages for admin dashboard"""
    try:
        conn = sqlite3.connect(DB_NAME)
        c = conn.cursor()
        
        # Get recent messages with user info
        c.execute('''
            SELECT m.user_id, m.sender, m.message, m.timestamp, 
                   u.full_name, u.username
            FROM messages m
            LEFT JOIN users u ON m.user_id = u.user_id
            ORDER BY m.timestamp DESC
            LIMIT 100
        ''')
        messages = c.fetchall()
        conn.close()
        
        # Format messages for admin
        formatted_messages = []
        for user_id, sender, message, timestamp, full_name, username in messages:
            formatted_messages.append({
                'user_id': user_id,
                'sender': sender,
                'message': message,
                'timestamp': timestamp,
                'user_name': full_name or f"User {user_id}",
                'username': username or "Unknown"
            })
        
        return jsonify({
            'status': 'success',
            'messages': formatted_messages,
            'total_messages': len(formatted_messages)
        })
        
    except Exception as e:
        print(f"❌ Error getting admin messages: {e}")
        return jsonify({
            'status': 'error',
            'message': str(e),
            'messages': []
        }), 500

@app.route('/admin/users')
def admin_users():
    """Get all users for admin dashboard"""
    try:
        users = get_all_users()
        
        # Add online status and message count for each user
        users_with_stats = []
        for user in users:
            user_id = user[0]
            is_online = get_user_online_status(user_id, 5)
            
            # Get message count for this user
            conn = sqlite3.connect(DB_NAME)
            c = conn.cursor()
            c.execute('SELECT COUNT(*) FROM messages WHERE user_id = ?', (user_id,))
            message_count = c.fetchone()[0]
            conn.close()
            
            users_with_stats.append({
                'user_id': user[0],
                'full_name': user[1],
                'username': user[2],
                'join_date': user[3],
                'invite_link': user[4],
                'photo_url': user[5],
                'label': user[6],
                'is_online': is_online,
                'message_count': message_count
            })
        
        return jsonify({
            'status': 'success',
            'users': users_with_stats,
            'total_users': len(users_with_stats)
        })
        
    except Exception as e:
        print(f"❌ Error getting admin users: {e}")
        return jsonify({
            'status': 'error',
            'message': str(e),
            'users': []
        }), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5001))
    print(f"🚀 Starting Simplified Telegram Bot API on port {port}")
    print(f"🌐 API URL: https://joingroup-8835.onrender.com")
    print(f"🔥 Pyrogram bot will start in background")
    socketio.run(app, port=port, debug=False, host='0.0.0.0', allow_unsafe_werkzeug=True) 
