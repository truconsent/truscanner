import requests
import uuid
import os
import webbrowser
import json
from typing import Dict, Any, Optional
from pathlib import Path
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
import threading
import time

DEFAULT_BACKEND_URL = "https://d987tu7rq4.execute-api.ap-south-1.amazonaws.com"
DEFAULT_DASHBOARD_URL = "https://truscanner-insights.pages.dev"
CALLBACK_PORT = 8765

class CallbackHandler(BaseHTTPRequestHandler):
    """HTTP handler for receiving OAuth callback from browser."""
    
    def log_message(self, format, *args):
        """Suppress default logging."""
        pass
    
    def do_GET(self):
        """Handle GET request with auth token."""
        query = parse_qs(urlparse(self.path).query)
        token = query.get('token', [None])[0]
        
        if token:
            self.server.received_token = token
            self.send_response(200)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            html = """
            <html>
            <head>
                <title>truscanner - Authentication Successful</title>
                <style>
                    * { margin: 0; padding: 0; box-sizing: border-box; }
                    body {
                        font-family: 'Courier New', monospace;
                        background: #000;
                        color: #00ff00;
                        display: flex;
                        align-items: center;
                        justify-center: center;
                        min-height: 100vh;
                        padding: 20px;
                    }
                    .container {
                        text-align: center;
                        max-width: 600px;
                        border: 2px solid #00ff00;
                        padding: 40px;
                        box-shadow: 0 0 40px rgba(0, 255, 0, 0.3);
                        animation: glow 2s ease-in-out infinite alternate;
                    }
                    @keyframes glow {
                        from { box-shadow: 0 0 20px rgba(0, 255, 0, 0.2); }
                        to { box-shadow: 0 0 40px rgba(0, 255, 0, 0.5); }
                    }
                    h1 {
                        font-size: 2.5em;
                        margin-bottom: 20px;
                        text-shadow: 0 0 10px #00ff00;
                    }
                    .checkmark {
                        font-size: 4em;
                        margin-bottom: 20px;
                        animation: pulse 1.5s ease-in-out infinite;
                    }
                    @keyframes pulse {
                        0%, 100% { transform: scale(1); }
                        50% { transform: scale(1.1); }
                    }
                    p {
                        font-size: 1.2em;
                        line-height: 1.6;
                        margin-bottom: 15px;
                    }
                    .terminal {
                        background: #111;
                        border: 1px solid #00ff00;
                        padding: 15px;
                        margin-top: 20px;
                        text-align: left;
                        font-size: 0.9em;
                    }
                    .blink {
                        animation: blink 1s step-start infinite;
                    }
                    @keyframes blink {
                        50% { opacity: 0; }
                    }
                </style>
            </head>
            <body>
                <div class="container">
                    <div class="checkmark">✓</div>
                    <h1>Authentication Successful!</h1>
                    <p>You've been authenticated with truscanner.</p>
                    <div class="terminal">
                        <div>> Authentication complete</div>
                        <div>> Token received and saved</div>
                        <div>> Returning to terminal<span class="blink">_</span></div>
                    </div>
                    <p style="margin-top: 30px; font-size: 0.9em;">
                        You can now close this window and return to your terminal.
                    </p>
                </div>
            </body>
            </html>
            """
            self.wfile.write(html.encode())
        else:
            self.send_response(400)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            html = """
            <html>
            <head>
                <title>truscanner - Authentication Failed</title>
                <style>
                    * { margin: 0; padding: 0; box-sizing: border-box; }
                    body {
                        font-family: 'Courier New', monospace;
                        background: #000;
                        color: #ff0000;
                        display: flex;
                        align-items: center;
                        justify-content: center;
                        min-height: 100vh;
                        padding: 20px;
                    }
                    .container {
                        text-align: center;
                        max-width: 600px;
                        border: 2px solid #ff0000;
                        padding: 40px;
                        box-shadow: 0 0 40px rgba(255, 0, 0, 0.3);
                    }
                    h1 { font-size: 2.5em; margin-bottom: 20px; }
                    p { font-size: 1.2em; line-height: 1.6; }
                </style>
            </head>
            <body>
                <div class="container">
                    <h1>❌ Authentication Failed</h1>
                    <p>No token received. Please try again.</p>
                </div>
            </body>
            </html>
            """
            self.wfile.write(html.encode())


class truscannerAPI:
    def __init__(self, base_url: str = None):
        self.base_url = base_url or os.getenv("TRUSCANNER_BACKEND_URL", DEFAULT_BACKEND_URL)
        self.dashboard_url = os.getenv("TRUSCANNER_DASHBOARD_URL", DEFAULT_DASHBOARD_URL)
        self.session = requests.Session()
        self.credentials_file = Path.home() / ".truscanner" / "credentials.json"
        self.token = self.load_token()

    def load_token(self) -> Optional[str]:
        """Load auth token from credentials file."""
        if not self.credentials_file.exists():
            return None
        
        try:
            with open(self.credentials_file, 'r') as f:
                creds = json.load(f)
                # Check if token is expired
                if creds.get('expires_at', 0) > time.time():
                    return creds.get('access_token')
        except Exception as e:
            print(f"Warning: Could not load credentials: {e}")
        
        return None

    def save_token(self, token: str, expires_in: int = 300):
        """Save auth token to credentials file. Default expiration: 5 minutes."""
        self.credentials_file.parent.mkdir(parents=True, exist_ok=True)
        
        creds = {
            'access_token': token,
            'expires_at': time.time() + expires_in
        }
        
        with open(self.credentials_file, 'w') as f:
            json.dump(creds, f, indent=2)
        
        # Set restrictive permissions (600)
        os.chmod(self.credentials_file, 0o600)
        self.token = token

    def is_authenticated(self) -> bool:
        """Check if user has valid auth token."""
        # Reload token to check if it's expired
        self.token = self.load_token()
        return self.token is not None

    def authenticate(self) -> bool:
        """Start authentication flow with browser callback."""
        print(f"🔐 Starting authentication flow...")
        print(f"📱 Opening browser for Google sign-in...")
        
        # Start local HTTP server
        server = HTTPServer(('localhost', CALLBACK_PORT), CallbackHandler)
        server.received_token = None
        server.timeout = 0.5  # Check for token every 0.5s
        
        # Open browser to auth page
        callback_url = f"http://localhost:{CALLBACK_PORT}/callback"
        auth_url = f"{self.dashboard_url}/auth?callback={callback_url}"
        webbrowser.open(auth_url)
        
        print(f"⏳ Waiting for authentication (timeout: 5 minutes)...")
        
        # Wait for callback with timeout
        start_time = time.time()
        timeout = 300  # 5 minutes
        
        def run_server():
            while not server.received_token and (time.time() - start_time) < timeout:
                server.handle_request()
        
        server_thread = threading.Thread(target=run_server, daemon=True)
        server_thread.start()
        server_thread.join(timeout)
        
        if server.received_token:
            self.save_token(server.received_token)
            return True
        else:
            print("❌ Authentication timeout or cancelled")
            return False

    def upload_scan(self, project_name: str, results: Dict[str, Any], duration: float, files_scanned: int = 0, metadata: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        """Upload scan results to the backend with authentication."""
        endpoint = f"{self.base_url}/api/scans/"
        
        scan_session_id = str(uuid.uuid4())
        
        payload = {
            "project_name": project_name,
            "duration_seconds": duration,
            "total_findings": len(results) if isinstance(results, list) else 0,
            "scan_data": results,
            "files_scanned": files_scanned,
            "metadata": metadata or {},
            "scan_session_id": scan_session_id
        }
        
        headers = {}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        
        try:
            response = self.session.post(endpoint, json=payload, headers=headers)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 401:
                # Token is invalid or revoked, clear it
                print(f"\n❌ Authentication failed: {e}")
                print("🔄 Your session has expired or been revoked. Please re-authenticate.")
                self.token = None
                if self.credentials_file.exists():
                    self.credentials_file.unlink()
                return {"error": "unauthorized"}
            else:
                print(f"\n❌ Error uploading scan: {e}")
                return None
        except requests.exceptions.RequestException as e:
            print(f"\n❌ Error uploading scan: {e}")
            return None

    def open_dashboard(self, scan_id: str):
        """Open web browser to the analytics dashboard."""
        url = f"{self.dashboard_url}/scan/{scan_id}"
        print(f"\n🔗 Opening analytics dashboard: {url}")
        webbrowser.open(url)
