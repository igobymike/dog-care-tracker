#!/usr/bin/env python3
# =============================================================================
# deploy_webhook.py — OTA deploy server for iOS CI/CD pipeline
# =============================================================================
#
# PURPOSE:
#   1. Receives build notifications from GitHub Actions
#   2. Downloads the signed .ipa from GitHub Artifacts
#   3. Hosts the .ipa + manifest.plist for OTA (Over-The-Air) installation
#   4. Notifies the user via APNs push, webhook POST, or email
#
# CONFIG:
#   All app-specific values are read from config.json (next to scripts/).
#   See config.example.json for the schema.
#
# USAGE:
#   python3 scripts/deploy_webhook.py --port 9879
#   pm2 start scripts/deploy_webhook.py --name deploy-webhook -- --port 9879
#
# ROUTES:
#   POST /api/deploy/ios             — Trigger a deploy (from GitHub Actions)
#   POST /api/deploy/complete        — Mark deploy complete
#   POST /api/deploy/device-token    — Register APNs device token from iOS app
#   GET  /api/deploy/status          — Check deploy status
#   GET  /api/deploy/manifest.plist  — OTA manifest (iOS fetches this)
#   GET  /api/deploy/<AppName>.ipa   — Signed .ipa download
#   GET  /api/deploy/install         — Install page + optional "Open & Connect" button
#   GET  /api/deploy/pair-config     — One-tap pairing config (Tailscale-only)
#   GET  /health                     — Health check
#
# NOTIFIERS:
#   Path A (APNs device token registered): push notification → tap → native install
#   Path B (no device token): webhook POST and/or email, configured in config.json notify block
#   Always: logs install URL to stdout
#
# =============================================================================

import argparse
import base64
import json
import logging
import os
import smtplib
import subprocess
import sys
import time
import urllib.error
import urllib.request
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from threading import Thread

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [deploy-webhook] %(levelname)s: %(message)s',
    datefmt='%H:%M:%S'
)
log = logging.getLogger('deploy-webhook')


# =============================================================================
# CONFIG — load from config.json
# =============================================================================

def load_config() -> dict:
    """Load config.json from the project root (parent of scripts/)."""
    config_path = Path(__file__).parent.parent / 'config.json'
    if not config_path.exists():
        log.error(f"config.json not found at {config_path}")
        log.error("Copy config.example.json to config.json and edit it.")
        sys.exit(1)
    with open(config_path) as f:
        return json.load(f)


CONFIG = load_config()

APP_NAME     = CONFIG['app']['name']
BUNDLE_ID    = CONFIG['app']['bundle_id']
DISPLAY_NAME = CONFIG['app'].get('display_name', APP_NAME)
APP_SCHEME   = CONFIG['app'].get('url_scheme', '')

OTA_DIR      = Path(__file__).parent.parent / CONFIG['deploy'].get('ota_dir', '.deploys/ota')
OTA_BASE_URL = os.environ.get('OTA_BASE_URL', CONFIG['deploy']['ota_base_url'])

APNS_KEY_PATH = Path(os.path.expanduser(CONFIG['apple'].get('apns_key_path', '')))
APNS_KEY_ID   = CONFIG['apple'].get('apns_key_id', '')
APNS_TEAM_ID  = CONFIG['apple']['team_id']

NOTIFY_CFG    = CONFIG.get('notify', {})
OPENCLAW_CFG  = CONFIG.get('openclaw', {})

APNS_ENABLED  = NOTIFY_CFG.get('apns', {}).get('enabled',
                    CONFIG.get('notifications', {}).get('apns_enabled', True))

IPA_FILENAME  = f'{APP_NAME}.ipa'

EXPECTED_TOKEN = os.environ.get('DEPLOY_WEBHOOK_TOKEN', '')

DEVICE_TOKEN_PATH = Path(os.path.expanduser(
    CONFIG['apple'].get('apns_key_path', '~/.ios-signing')
)).parent / 'device_token.json'

deploy_state = {
    'status': 'idle',
    'sha': None,
    'started_at': None,
    'finished_at': None,
    'message': '',
    'last_run_id': None,
    'install_url': None,
}

DEPLOY_STATE_PATH = OTA_DIR / 'deploy_state.json'


def save_deploy_state():
    """Persist deploy_state to deploy_state.json in OTA dir."""
    try:
        DEPLOY_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        DEPLOY_STATE_PATH.write_text(json.dumps(deploy_state, indent=2))
    except Exception as e:
        log.warning(f"Failed to save deploy state: {e}")


def load_deploy_state():
    """Restore deploy_state from deploy_state.json on startup."""
    global deploy_state
    if not DEPLOY_STATE_PATH.exists():
        return
    try:
        saved = json.loads(DEPLOY_STATE_PATH.read_text())
        # Only restore terminal states (not 'running' — that was interrupted)
        if saved.get('status') == 'running':
            saved['status'] = 'failed'
            saved['message'] = 'Interrupted — server restarted during deploy'
        deploy_state.update(saved)
        log.info(f"Restored deploy state: status={deploy_state['status']} sha={deploy_state.get('sha', 'none')}")
    except Exception as e:
        log.warning(f"Failed to load deploy state: {e}")


def verify_token(auth_header: str) -> bool:
    if not EXPECTED_TOKEN:
        log.warning("DEPLOY_WEBHOOK_TOKEN not set — all requests allowed (unsafe!)")
        return True
    if not auth_header:
        return False
    parts = auth_header.split(' ', 1)
    if len(parts) != 2 or parts[0].lower() != 'bearer':
        return False
    return parts[1] == EXPECTED_TOKEN


# =============================================================================
# APNs Push Notifications
# =============================================================================

def load_device_token() -> str | None:
    if not DEVICE_TOKEN_PATH.exists():
        return None
    try:
        data = json.loads(DEVICE_TOKEN_PATH.read_text())
        return data.get('token')
    except Exception:
        return None


def save_device_token(token: str):
    DEVICE_TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)
    DEVICE_TOKEN_PATH.write_text(json.dumps({
        'token': token,
        'updated_at': int(time.time()),
    }))
    log.info(f"Saved device token: {token[:8]}...{token[-8:]}")


def send_push_notification(title: str, body: str, url: str = '') -> bool:
    """Send an APNs push notification. url should be itms-services:// for install triggers."""
    if not APNS_ENABLED:
        log.info("APNs disabled in config")
        return False

    device_token = load_device_token()
    if not device_token:
        log.warning("No device token registered — skipping APNs push")
        return False

    if not APNS_KEY_PATH.exists():
        log.error(f"APNs key not found at {APNS_KEY_PATH}")
        return False

    try:
        import jwt
        import httpx
    except ImportError:
        log.error("Missing pyjwt or httpx — install with: pip3 install pyjwt[crypto] httpx[http2]")
        return False

    try:
        private_key = APNS_KEY_PATH.read_text()
        token = jwt.encode(
            {"iss": APNS_TEAM_ID, "iat": int(time.time())},
            private_key,
            algorithm="ES256",
            headers={"kid": APNS_KEY_ID, "alg": "ES256"},
        )

        payload = {
            "aps": {
                "alert": {"title": title, "body": body},
                "sound": "default",
                "badge": 1,
            }
        }
        if url:
            payload["install_url"] = url

        apns_env = CONFIG.get('notifications', {}).get('apns_environment', 'development')
        apns_host = 'api.push.apple.com' if apns_env == 'production' else 'api.sandbox.push.apple.com'

        with httpx.Client(http2=True, timeout=15) as client:
            resp = client.post(
                f"https://{apns_host}/3/device/{device_token}",
                json=payload,
                headers={
                    "authorization": f"bearer {token}",
                    "apns-topic": BUNDLE_ID,
                    "apns-push-type": "alert",
                    "apns-priority": "10",
                },
            )

        if resp.status_code == 200:
            log.info(f"APNs push sent: {title}")
            return True
        else:
            log.error(f"APNs error {resp.status_code}: {resp.text}")
            return False

    except Exception as e:
        log.error(f"APNs push failed: {e}")
        return False


# =============================================================================
# Pluggable Notifiers — webhook POST and email fallbacks
# =============================================================================

def fire_webhook_notifier(install_url: str, sha_short: str, cfg: dict) -> bool:
    """POST to a webhook URL to notify of a new build."""
    url = cfg.get('url', '')
    if not url:
        return False
    template = cfg.get('body', '{"text": "{{app_name}} build {{sha}} ready: {{install_url}}"}')
    body = (template
            .replace('{{install_url}}', install_url)
            .replace('{{app_name}}', DISPLAY_NAME)
            .replace('{{sha}}', sha_short))
    try:
        req = urllib.request.Request(
            url,
            data=body.encode(),
            headers={'Content-Type': 'application/json'},
            method='POST',
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            log.info(f"Webhook notifier: HTTP {resp.status}")
            return True
    except Exception as e:
        log.warning(f"Webhook notifier failed: {e}")
        return False


def fire_email_notifier(install_url: str, sha_short: str, cfg: dict) -> bool:
    """Send an email notification via SMTP."""
    host = cfg.get('smtp_host', '')
    if not host:
        return False
    port       = int(cfg.get('smtp_port', 587))
    username   = cfg.get('username', '')
    password   = cfg.get('password', '')
    to_addr    = cfg.get('to', '')
    from_addr  = cfg.get('from', username)
    if not to_addr:
        return False

    subject = f"{DISPLAY_NAME} build {sha_short} ready to install"
    text = (
        f"A new build of {DISPLAY_NAME} is ready.\n\n"
        f"Build: {sha_short}\n"
        f"Install: {install_url}\n\n"
        f"Open the link in Safari on your iPhone to install."
    )
    try:
        msg = MIMEMultipart()
        msg['Subject'] = subject
        msg['From']    = from_addr
        msg['To']      = to_addr
        msg.attach(MIMEText(text, 'plain'))

        with smtplib.SMTP(host, port, timeout=15) as smtp:
            smtp.ehlo()
            smtp.starttls()
            if username and password:
                smtp.login(username, password)
            smtp.sendmail(from_addr, to_addr, msg.as_string())
        log.info(f"Email notifier: sent to {to_addr}")
        return True
    except Exception as e:
        log.warning(f"Email notifier failed: {e}")
        return False


def fire_notifiers(install_url: str, itms_url: str, sha_short: str):
    """Fire all configured notifiers after a successful deploy.

    Path A — APNs push if device token is registered (tap → native install dialog).
    Path B — webhook POST and/or email if no APNs token.
    Always  — log the install URL to stdout.
    """
    log.info(f"Install ready: {install_url}")

    # Path A: APNs (app installed, device token registered)
    if load_device_token():
        send_push_notification(
            title=f"{DISPLAY_NAME} Update Ready",
            body=f"Build {sha_short} ready. Tap to install.",
            url=itms_url,
        )
        return  # APNs sent — no need for fallbacks

    log.info("No APNs device token — firing fallback notifiers")

    # Path B: webhook
    webhook_cfg = NOTIFY_CFG.get('webhook', {})
    if webhook_cfg.get('enabled') and webhook_cfg.get('url'):
        fire_webhook_notifier(install_url, sha_short, webhook_cfg)

    # Path B: email
    email_cfg = NOTIFY_CFG.get('email', {})
    if email_cfg.get('enabled') and email_cfg.get('smtp_host'):
        fire_email_notifier(install_url, sha_short, email_cfg)


# =============================================================================
# Pair Config — one-tap setup via app URL scheme
# =============================================================================

def get_pair_config() -> dict | None:
    """Get the one-tap pairing config for the app's URL scheme.

    Reads gateway URL and bootstrap token from config.json openclaw block or
    environment variables. Returns None if not configured.
    """
    gateway_url     = os.environ.get('GATEWAY_URL',             OPENCLAW_CFG.get('gateway_url', ''))
    bootstrap_token = os.environ.get('OPENCLAW_BOOTSTRAP_TOKEN', OPENCLAW_CFG.get('bootstrap_token', ''))
    cf_client_id    = os.environ.get('CF_ACCESS_CLIENT_ID', '')
    cf_client_secret= os.environ.get('CF_ACCESS_CLIENT_SECRET', '')
    agent_name      = OPENCLAW_CFG.get('agent_name', APP_NAME)

    if not gateway_url or not bootstrap_token:
        return None

    return {
        'url':               gateway_url,
        'bootstrapToken':    bootstrap_token,
        'cfAccessClientId':  cf_client_id,
        'cfAccessClientSecret': cf_client_secret,
        'agentName':         agent_name,
    }


# =============================================================================
# Deploy Worker
# =============================================================================

def run_deploy_async(payload: dict):
    sha    = payload.get('sha', 'unknown')
    run_id = payload.get('run_id', '')

    deploy_state['status']      = 'running'
    deploy_state['sha']         = sha
    deploy_state['started_at']  = int(time.time())
    deploy_state['last_run_id'] = run_id
    deploy_state['message']     = f'Deploying {sha[:8]}...'
    save_deploy_state()

    log.info(f"Starting deploy: sha={sha[:8]} run_id={run_id}")

    script = Path(__file__).parent / 'deploy_to_phone.py'
    cmd = [sys.executable, str(script), '--sha', sha]
    if run_id:
        cmd += ['--run-id', run_id]

    env = {**os.environ, 'GITHUB_TOKEN': os.environ.get('GITHUB_TOKEN', '')}

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300, env=env)

        if result.returncode == 0:
            deploy_state['status']      = 'success'
            deploy_state['message']     = f'Deployed {sha[:8]} successfully'
            install_url = f'{OTA_BASE_URL}/install'
            itms_url    = f'itms-services://?action=download-manifest&url={OTA_BASE_URL}/manifest.plist'
            deploy_state['install_url'] = install_url
            log.info(f"Deploy success: {sha[:8]}")

            fire_notifiers(install_url, itms_url, sha[:8])
        else:
            deploy_state['status']  = 'failed'
            deploy_state['message'] = result.stderr.strip() or 'Deploy script failed'
            log.error(f"Deploy failed: {result.stderr.strip()}")

        for line in (result.stdout or '').strip().split('\n'):
            if line:
                log.info(f"  [deploy] {line}")
        for line in (result.stderr or '').strip().split('\n'):
            if line:
                log.warning(f"  [deploy-err] {line}")

    except subprocess.TimeoutExpired:
        deploy_state['status']  = 'failed'
        deploy_state['message'] = 'Deploy timed out after 5 minutes'
        log.error("Deploy timed out")
    except Exception as e:
        deploy_state['status']  = 'failed'
        deploy_state['message'] = str(e)
        log.error(f"Deploy error: {e}")
    finally:
        deploy_state['finished_at'] = int(time.time())
        save_deploy_state()


# =============================================================================
# HTTP Handler
# =============================================================================

class DeployHandler(BaseHTTPRequestHandler):

    def log_message(self, format, *args):
        log.info(f"{self.address_string()} - {format % args}")

    def send_json(self, status: int, data: dict):
        body = json.dumps(data).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', len(body))
        self.end_headers()
        self.wfile.write(body)

    def read_body(self) -> dict:
        length = int(self.headers.get('Content-Length', 0))
        if length == 0:
            return {}
        return json.loads(self.rfile.read(length))

    def send_file(self, filepath: Path, content_type: str, inline: bool = False):
        if not filepath.exists():
            self.send_json(404, {'error': f'{filepath.name} not found — no build deployed yet'})
            return
        data = filepath.read_bytes()
        self.send_response(200)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', len(data))
        if not inline:
            self.send_header('Content-Disposition', f'attachment; filename="{filepath.name}"')
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path == '/api/deploy/status':
            self.send_json(200, {
                **deploy_state,
                'app': APP_NAME,
                'has_device_token': load_device_token() is not None,
            })

        elif self.path == '/api/deploy/manifest.plist':
            self.send_file(OTA_DIR / 'manifest.plist', 'text/xml', inline=True)

        elif self.path == f'/api/deploy/{IPA_FILENAME}':
            self.send_file(OTA_DIR / IPA_FILENAME, 'application/octet-stream')

        elif self.path in ('/api/deploy/install', '/install'):
            itms_url  = f'itms-services://?action=download-manifest&url={OTA_BASE_URL}/manifest.plist'
            sha_short = (deploy_state.get("sha") or "")[:8] or "none"

            # Generate "Open & Connect" button if openclaw pairing is configured
            open_connect_html = ''
            if APP_SCHEME:
                pair_cfg = get_pair_config()
                if pair_cfg and pair_cfg.get('url') and pair_cfg.get('bootstrapToken'):
                    cfg_b64  = base64.b64encode(json.dumps(pair_cfg).encode()).decode()
                    pair_url = f'{APP_SCHEME}://pair?config={cfg_b64}'
                    open_connect_html = f'''
<div style="margin-top:20px;padding-top:20px;border-top:1px solid #e5e5ea">
<p style="color:#8e8e93;font-size:14px;margin:0 0 10px 0">First time? One tap to connect.</p>
<a href="{pair_url}" style="display:inline-block;padding:12px 24px;
background:#34C759;color:white;border-radius:12px;text-decoration:none;
font-size:16px;font-weight:600">Open &amp; Connect</a>
</div>'''

            html = f'''<!DOCTYPE html>
<html><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Install {DISPLAY_NAME}</title>
</head>
<body style="font-family:-apple-system,system-ui;text-align:center;padding:40px;background:#f5f5f7">
<div style="max-width:400px;margin:0 auto;background:white;border-radius:16px;padding:30px;box-shadow:0 2px 10px rgba(0,0,0,0.1)">
<h2 style="margin-top:0">{DISPLAY_NAME}</h2>
<p style="color:#666">Tap to install the latest build.</p>
<a id="install-btn" href="{itms_url}" style="display:inline-block;padding:14px 28px;
background:#007AFF;color:white;border-radius:12px;text-decoration:none;
font-size:18px;margin:10px 0">Install {DISPLAY_NAME}</a>
<p style="margin-top:20px;color:#888;font-size:13px">Build: {sha_short}</p>
<p id="safari-warning" style="display:none;color:#ff3b30;font-size:14px;margin-top:15px">
This page must be opened in Safari. Tap the share icon and choose "Open in Safari".</p>
{open_connect_html}
</div>
<script>
var isSafari = /^((?!CriOS|FxiOS|OPiOS|EdgiOS|GSA).)*Safari/.test(navigator.userAgent);
var isStandalone = window.navigator.standalone;
if (!isSafari && !isStandalone && /iPhone|iPad|iPod/.test(navigator.userAgent)) {{
    document.getElementById('safari-warning').style.display = 'block';
}}
if (isSafari && window.location.hash === '#auto') {{
    window.location = '{itms_url}';
}}
</script>
</body></html>'''
            body = html.encode()
            self.send_response(200)
            self.send_header('Content-Type', 'text/html')
            self.send_header('Content-Length', len(body))
            self.end_headers()
            self.wfile.write(body)

        elif self.path == '/api/deploy/pair-config':
            # Return pairing config for <app-scheme>://pair?config=<base64>
            # Allowed from: Tailscale (100.x.x.x), localhost, OR valid Bearer token
            # Bearer token allows the iOS app to call this via CF tunnel on first install.
            client_ip = self.client_address[0]
            is_tailscale = client_ip.startswith('100.') or client_ip in ('127.0.0.1', '::1')
            auth = self.headers.get('Authorization', '')
            bearer = auth[7:].strip() if auth.startswith('Bearer ') else ''
            is_authorized = bool(bearer and EXPECTED_TOKEN and bearer == EXPECTED_TOKEN)
            if not is_tailscale and not is_authorized:
                self.send_json(403, {'error': 'Access restricted — use Tailscale or Bearer token'})
                return
            cfg = get_pair_config()
            if cfg:
                self.send_json(200, cfg)
            else:
                self.send_json(503, {'error': 'Pairing config not available — set openclaw.gateway_url and openclaw.bootstrap_token in config.json'})

        elif self.path == '/health':
            self.send_json(200, {'status': 'ok', 'service': f'{APP_NAME}-deploy-webhook'})

        else:
            self.send_json(404, {'error': 'Not found'})

    def do_HEAD(self):
        if self.path == f'/api/deploy/{IPA_FILENAME}':
            filepath = OTA_DIR / IPA_FILENAME
            if filepath.exists():
                self.send_response(200)
                self.send_header('Content-Type', 'application/octet-stream')
                self.send_header('Content-Length', filepath.stat().st_size)
                self.end_headers()
            else:
                self.send_response(404)
                self.end_headers()
        elif self.path == '/api/deploy/manifest.plist':
            filepath = OTA_DIR / 'manifest.plist'
            if filepath.exists():
                self.send_response(200)
                self.send_header('Content-Type', 'text/xml')
                self.send_header('Content-Length', filepath.stat().st_size)
                self.end_headers()
            else:
                self.send_response(404)
                self.end_headers()
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        # Device token registration is unauthenticated (iOS app sends it on launch)
        if self.path == '/api/deploy/device-token':
            body = self.read_body()
            token = body.get('token', '')
            if not token or len(token) < 32:
                self.send_json(400, {'error': 'Invalid device token'})
                return
            save_device_token(token)
            self.send_json(200, {'status': 'ok', 'message': 'Device token registered'})
            return

        # All other POST routes require auth
        auth = self.headers.get('Authorization', '')
        if not verify_token(auth):
            self.send_json(401, {'error': 'Unauthorized'})
            return

        body = self.read_body()

        if self.path == '/api/deploy/ios':
            if deploy_state['status'] == 'running':
                self.send_json(409, {
                    'error': 'Deploy already in progress',
                    'sha': deploy_state['sha'],
                })
                return

            thread = Thread(
                target=run_deploy_async,
                args=(body,),
                daemon=True,
                name='deploy-worker',
            )
            thread.start()

            self.send_json(202, {
                'status': 'accepted',
                'message': f"Deploy started for {body.get('sha', 'unknown')[:8]}",
                'sha': body.get('sha'),
            })

        elif self.path == '/api/deploy/complete':
            success = body.get('success', False)
            deploy_state['status']      = 'success' if success else 'failed'
            deploy_state['message']     = body.get('message', '')
            deploy_state['finished_at'] = int(time.time())
            install_url = body.get('install_url', '')
            if install_url:
                deploy_state['install_url'] = install_url
            save_deploy_state()
            log.info(f"Deploy complete: success={success}")

            if success:
                sha_short   = (deploy_state.get('sha') or 'unknown')[:8]
                install_url = install_url or f'{OTA_BASE_URL}/install'
                itms_url    = f'itms-services://?action=download-manifest&url={OTA_BASE_URL}/manifest.plist'
                fire_notifiers(install_url, itms_url, sha_short)

            self.send_json(200, {'status': 'ok'})

        elif self.path == '/api/deploy/push-test':
            itms_url = f'itms-services://?action=download-manifest&url={OTA_BASE_URL}/manifest.plist'
            result = send_push_notification(
                title=f"{DISPLAY_NAME} Test",
                body="Push notification test from deploy webhook.",
                url=itms_url,
            )
            self.send_json(200, {'status': 'ok', 'push_sent': result})

        else:
            self.send_json(404, {'error': 'Not found'})


def main():
    parser = argparse.ArgumentParser(description='iOS OTA deploy webhook server')
    parser.add_argument('--port', type=int,
                        default=CONFIG['deploy'].get('webhook_port', 9879),
                        help='Port to listen on')
    parser.add_argument('--host', type=str, default='0.0.0.0', help='Host to bind to')
    args = parser.parse_args()

    if not EXPECTED_TOKEN:
        log.warning("DEPLOY_WEBHOOK_TOKEN not set — set it for security!")

    OTA_DIR.mkdir(parents=True, exist_ok=True)
    load_deploy_state()

    log.info(f"App: {DISPLAY_NAME} ({BUNDLE_ID})")

    if APNS_ENABLED and APNS_KEY_PATH.exists():
        log.info(f"APNs key loaded: {APNS_KEY_PATH.name}")
    elif APNS_ENABLED:
        log.warning(f"APNs key not found at {APNS_KEY_PATH} — APNs push disabled")
    else:
        log.info("APNs disabled in config")

    # Log which notifiers are active
    webhook_cfg = NOTIFY_CFG.get('webhook', {})
    email_cfg   = NOTIFY_CFG.get('email', {})
    if webhook_cfg.get('enabled') and webhook_cfg.get('url'):
        log.info(f"Webhook notifier: {webhook_cfg['url']}")
    if email_cfg.get('enabled') and email_cfg.get('smtp_host'):
        log.info(f"Email notifier: {email_cfg.get('to')} via {email_cfg['smtp_host']}")

    dt = load_device_token()
    if dt:
        log.info(f"Device token loaded: {dt[:8]}...{dt[-8:]}")
    else:
        log.info("No device token registered yet — fallback notifiers will be used")

    server = HTTPServer((args.host, args.port), DeployHandler)
    log.info(f"Deploy webhook listening on {args.host}:{args.port}")
    log.info(f"OTA dir: {OTA_DIR} | Base URL: {OTA_BASE_URL}")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        log.info("Shutting down")


if __name__ == '__main__':
    main()
