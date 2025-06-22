#!/usr/bin/env python3
"""
Smart Scheduler AI Agent - Server Launcher
Simple script to run the FastAPI server with proper Python path setup
"""
import sys
import os

# Add project root to Python path
project_root = os.path.dirname(os.path.abspath(__file__))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Import and run the server
if __name__ == "__main__":
    try:
        from src.api.main import app
        import uvicorn
        
        uvicorn.run(
            "src.api.main:app",
            host="0.0.0.0",
            port=8000,
            reload=True,
            log_level="info"
        )
        
    except ImportError as e:
        print(f"Import Error: {e}")
        print("\nPlease ensure you have:")
        print("1. Created the .env file with your API keys")
        print("2. Installed all dependencies: pip install -r requirements.txt")
        print("3. Set up your environment variables")
        
    except Exception as e:
        print(f"Error starting server: {e}")