#!/usr/bin/env python3
"""
Startup script for Telegram Bot API
Handles graceful initialization and error recovery
"""

import os
import sys
import time
import traceback
from api_simple import app, socketio

def main():
    """Main startup function with error handling"""
    try:
        # Get port from environment
        port = int(os.environ.get('PORT', 5001))
        
        print(f"🚀 Starting Simplified Telegram Bot API on port {port}")
        print(f"🌐 API URL: https://joingroup-8835.onrender.com")
        print(f"📋 Note: This is a simplified version without bot features")
        
        # Start Flask-SocketIO with production settings
        socketio.run(app, port=port, debug=False, host='0.0.0.0', allow_unsafe_werkzeug=True)
        
    except Exception as e:
        print(f"❌ Startup error: {e}")
        print(f"📋 Traceback: {traceback.format_exc()}")
        sys.exit(1)

if __name__ == '__main__':
    main() 
