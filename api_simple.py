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

# Fallback to in-memory database if file system is not writable
try:
    # Test if we can write to the directory
    test_file = f"{DB_PATH}.test"
    with open(test_file, 'w') as f:
        f.write('test')
    os.remove(test_file)
    print(f"✅ Using file database: {DB_PATH}")
except Exception as e:
    print(f"⚠️ File system not writable, using in-memory database: {e}")
    DB_NAME = ':memory:'
    print(f"📝 Note: In-memory database will reset when server restarts")

# Ensure DB tables exist
init_db()
print(f"🗄️ Database initialized: {DB_NAME}")
print(f"📁 Database file location: {os.path.abspath(DB_PATH) if DB_NAME != ':memory:' else 'In-memory'}")

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

# Start Pyrogram bot in main thread (simpler approach)
if test_pyrogram_connection():
    print("🚀 Pyrogram bot will start in main thread")
    # Start bot in main thread to avoid async issues
    try:
        pyro_app.run()
    except KeyboardInterrupt:
        print("🛑 Bot stopped by user")
    except Exception as e:
        print(f"❌ Bot error: {e}")
else:
    print("⚠️ Pyrogram bot not started - connection failed")

# Test connection before starting bot
if test_pyrogram_connection():
    print("🚀 Pyrogram bot will start in background")
else:
    print("⚠️ Pyrogram bot will not start due to connection issues")

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

        print(f"📋 Found {len(users)} users for this page")

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

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5001))
    print(f"🚀 Starting Simplified Telegram Bot API on port {port}")
    print(f"🌐 API URL: https://joingroup-8835.onrender.com")
    print(f"🔥 Pyrogram bot will start in background")
    socketio.run(app, port=port, debug=False, host='0.0.0.0', allow_unsafe_werkzeug=True) 
