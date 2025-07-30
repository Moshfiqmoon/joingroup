#!/usr/bin/env python3
"""
Start script for Render deployment
"""

import os
import sys
from api_simple import app, socketio

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5001))
    print(f"🚀 Starting Simplified Telegram Bot API on port {port}")
    print(f"🌐 API URL: https://joingroup-8835.onrender.com")
    print(f"🔥 Pyrogram bot will start in background")
    socketio.run(app, port=port, debug=False, host='0.0.0.0', allow_unsafe_werkzeug=True) 
