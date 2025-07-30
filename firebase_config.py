import firebase_admin
from firebase_admin import credentials, firestore, db
import os
import datetime
import json

# Firebase configuration - Load from JSON file
def load_firebase_config():
    """Load Firebase configuration from JSON file"""
    try:
        json_file = "firebase-service-account.json"
        if os.path.exists(json_file):
            with open(json_file, 'r') as f:
                config = json.load(f)
            print(f"✅ Loaded Firebase config from {json_file}")
            return config
        else:
            print(f"⚠️ {json_file} not found, using default config")
            return None
    except Exception as e:
        print(f"❌ Error loading Firebase config: {e}")
        return None

# Load Firebase config
FIREBASE_CONFIG = load_firebase_config()

# Initialize Firebase
def initialize_firebase():
    """Initialize Firebase with service account"""
    try:
        # Check if Firebase is already initialized
        if not firebase_admin._apps:
            if FIREBASE_CONFIG:
                try:
                    cred = credentials.Certificate(FIREBASE_CONFIG)
                    firebase_admin.initialize_app(cred, {
                        'databaseURL': f"https://{FIREBASE_CONFIG['project_id']}-default-rtdb.firebaseio.com"
                    })
                    print("✅ Firebase initialized successfully from JSON file")
                    return True
                except Exception as cert_error:
                    print(f"❌ Firebase certificate error: {cert_error}")
                    print("📝 Please check your Firebase credentials")
                    return False
            else:
                print("⚠️ Firebase not configured - no JSON file found")
                print("📝 Please ensure firebase-service-account.json exists")
                return False
        else:
            print("✅ Firebase already initialized")
            return True
            
    except Exception as e:
        print(f"❌ Firebase initialization failed: {e}")
        return False

# Get Firestore database
def get_firestore():
    """Get Firestore database instance"""
    try:
        return firestore.client()
    except Exception as e:
        print(f"❌ Error getting Firestore: {e}")
        return None

# Get Realtime Database
def get_realtime_db():
    """Get Realtime Database instance"""
    try:
        return db.reference()
    except Exception as e:
        print(f"❌ Error getting Realtime Database: {e}")
        return None

# User management functions
def add_user_to_firebase(user_id, full_name, username, join_date, invite_link=None, photo_url=None, label=None):
    """Add user to Firebase"""
    try:
        db = get_firestore()
        if not db:
            return False
            
        user_data = {
            'user_id': user_id,
            'full_name': full_name,
            'username': username,
            'join_date': join_date,
            'invite_link': invite_link,
            'photo_url': photo_url,
            'label': label,
            'created_at': firestore.SERVER_TIMESTAMP,
            'updated_at': firestore.SERVER_TIMESTAMP
        }
        
        db.collection('users').document(str(user_id)).set(user_data)
        print(f"✅ User {user_id} added to Firebase")
        return True
    except Exception as e:
        print(f"❌ Error adding user to Firebase: {e}")
        return False

def get_user_from_firebase(user_id):
    """Get user from Firebase"""
    try:
        db = get_firestore()
        if not db:
            return None
            
        doc = db.collection('users').document(str(user_id)).get()
        if doc.exists:
            return doc.to_dict()
        return None
    except Exception as e:
        print(f"❌ Error getting user from Firebase: {e}")
        return None

def get_all_users_from_firebase():
    """Get all users from Firebase"""
    try:
        db = get_firestore()
        if not db:
            return []
            
        users = []
        docs = db.collection('users').order_by('join_date', direction=firestore.Query.DESCENDING).stream()
        
        for doc in docs:
            user_data = doc.to_dict()
            users.append(user_data)
            
        return users
    except Exception as e:
        print(f"❌ Error getting users from Firebase: {e}")
        return []

def update_user_label(user_id, label):
    """Update user label in Firebase"""
    try:
        db = get_firestore()
        if not db:
            return False
            
        db.collection('users').document(str(user_id)).update({
            'label': label,
            'updated_at': firestore.SERVER_TIMESTAMP
        })
        print(f"✅ User {user_id} label updated to {label}")
        return True
    except Exception as e:
        print(f"❌ Error updating user label: {e}")
        return False

# Message management functions
def save_message_to_firebase(user_id, sender, message, timestamp=None):
    """Save message to Firebase"""
    try:
        db = get_firestore()
        if not db:
            return False
            
        if timestamp is None:
            timestamp = datetime.datetime.now().isoformat()
            
        message_data = {
            'user_id': user_id,
            'sender': sender,
            'message': message,
            'timestamp': timestamp,
            'created_at': firestore.SERVER_TIMESTAMP
        }
        
        db.collection('messages').add(message_data)
        print(f"✅ Message saved to Firebase for user {user_id}")
        return True
    except Exception as e:
        print(f"❌ Error saving message to Firebase: {e}")
        return False

def get_messages_for_user_from_firebase(user_id, limit=100):
    """Get messages for user from Firebase"""
    try:
        db = get_firestore()
        if not db:
            return []
            
        messages = []
        docs = db.collection('messages').where('user_id', '==', user_id).order_by('timestamp').limit(limit).stream()
        
        for doc in docs:
            msg_data = doc.to_dict()
            messages.append((
                msg_data.get('sender', ''),
                msg_data.get('message', ''),
                msg_data.get('timestamp', '')
            ))
            
        return messages
    except Exception as e:
        print(f"❌ Error getting messages from Firebase: {e}")
        return []

def get_all_messages_from_firebase(limit=100):
    """Get all messages from Firebase"""
    try:
        db = get_firestore()
        if not db:
            return []
            
        messages = []
        docs = db.collection('messages').order_by('timestamp', direction=firestore.Query.DESCENDING).limit(limit).stream()
        
        for doc in docs:
            msg_data = doc.to_dict()
            messages.append({
                'user_id': msg_data.get('user_id', ''),
                'sender': msg_data.get('sender', ''),
                'message': msg_data.get('message', ''),
                'timestamp': msg_data.get('timestamp', '')
            })
            
        return messages
    except Exception as e:
        print(f"❌ Error getting all messages from Firebase: {e}")
        return []

# Statistics functions
def get_total_users_from_firebase():
    """Get total users count from Firebase"""
    try:
        db = get_firestore()
        if not db:
            return 0
            
        docs = db.collection('users').stream()
        return len(list(docs))
    except Exception as e:
        print(f"❌ Error getting total users from Firebase: {e}")
        return 0

def get_total_messages_from_firebase():
    """Get total messages count from Firebase"""
    try:
        db = get_firestore()
        if not db:
            return 0
            
        docs = db.collection('messages').stream()
        return len(list(docs))
    except Exception as e:
        print(f"❌ Error getting total messages from Firebase: {e}")
        return 0

def get_active_users_from_firebase(minutes=60):
    """Get active users count from Firebase"""
    try:
        db = get_firestore()
        if not db:
            return 0
            
        since = datetime.datetime.now() - datetime.timedelta(minutes=minutes)
        
        # Get unique user IDs from recent messages
        docs = db.collection('messages').where('timestamp', '>=', since.isoformat()).stream()
        user_ids = set()
        
        for doc in docs:
            msg_data = doc.to_dict()
            user_ids.add(msg_data.get('user_id', ''))
            
        return len(user_ids)
    except Exception as e:
        print(f"❌ Error getting active users from Firebase: {e}")
        return 0

def get_new_joins_today_from_firebase():
    """Get new joins today count from Firebase"""
    try:
        db = get_firestore()
        if not db:
            return 0
            
        today = datetime.datetime.now().date().isoformat()
        
        docs = db.collection('users').where('join_date', '>=', today).stream()
        return len(list(docs))
    except Exception as e:
        print(f"❌ Error getting new joins from Firebase: {e}")
        return 0

# Real-time database functions (alternative to Firestore)
def save_message_to_realtime_db(user_id, sender, message, timestamp=None):
    """Save message to Realtime Database"""
    try:
        db = get_realtime_db()
        if not db:
            return False
            
        if timestamp is None:
            timestamp = datetime.datetime.now().isoformat()
            
        message_data = {
            'user_id': user_id,
            'sender': sender,
            'message': message,
            'timestamp': timestamp
        }
        
        db.child('messages').push(message_data)
        print(f"✅ Message saved to Realtime DB for user {user_id}")
        return True
    except Exception as e:
        print(f"❌ Error saving message to Realtime DB: {e}")
        return False

def get_messages_for_user_from_realtime_db(user_id, limit=100):
    """Get messages for user from Realtime Database"""
    try:
        db = get_realtime_db()
        if not db:
            return []
            
        messages = []
        data = db.child('messages').order_by_child('user_id').equal_to(user_id).get()
        
        if data:
            for key, value in data.items():
                messages.append((
                    value.get('sender', ''),
                    value.get('message', ''),
                    value.get('timestamp', '')
                ))
                
        return messages[-limit:]  # Get last N messages
    except Exception as e:
        print(f"❌ Error getting messages from Realtime DB: {e}")
        return []

# Migration function from SQLite to Firebase
def migrate_sqlite_to_firebase():
    """Migrate data from SQLite to Firebase"""
    try:
        import sqlite3
        
        # Connect to SQLite
        sqlite_conn = sqlite3.connect('users.db')
        sqlite_cursor = sqlite_conn.cursor()
        
        # Migrate users
        sqlite_cursor.execute('SELECT * FROM users')
        users = sqlite_cursor.fetchall()
        
        for user in users:
            user_id, full_name, username, join_date, invite_link, photo_url, label = user
            add_user_to_firebase(user_id, full_name, username, join_date, invite_link, photo_url, label)
        
        # Migrate messages
        sqlite_cursor.execute('SELECT * FROM messages')
        messages = sqlite_cursor.fetchall()
        
        for message in messages:
            msg_id, user_id, sender, message_text, timestamp = message
            save_message_to_firebase(user_id, sender, message_text, timestamp)
        
        sqlite_conn.close()
        print("✅ Migration completed successfully")
        return True
    except Exception as e:
        print(f"❌ Migration failed: {e}")
        return False 