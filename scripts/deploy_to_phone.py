#!/usr/bin/env python3
# =============================================================================
# deploy_to_phone.py — OTA iOS app deployment via HTTPS
# =============================================================================
#
# PURPOSE:
#   Downloads the latest signed .ipa artifact from GitHub Actions, hosts it
#   for OTA (Over-The-Air) installation, and notifies the webhook (APNs push).
#
# CONFIG:
#   All app-specific values are read from config.json (next to scripts/).
#
# USAGE:
#   python3 scripts/deploy_to_phone.py                # Deploy latest build
#   python3 scripts/deploy_to_phone.py --run-id 123   # Deploy specific run
#   python3 scripts/deploy_to_phone.py --ipa /path     # Deploy local .ipa
#   python3 scripts/deploy_to_phone.py --sha abc123    # Set SHA for logging
#
# REQUIREMENTS:
#   - GITHUB_TOKEN env var with repo:read scope (for artifact download)
#   - deploy_webhook.py running (serves OTA files)
#   - HTTPS route to the webhook (e.g., Cloudflare tunnel)
#
# =============================================================================

import argparse
import json
import os
import pathlib
import plistlib
import shutil
import subprocess
import sys
import time
import zipfile
import urllib.request
import urllib.error


# =============================================================================
# CONFIG
# =============================================================================

def load_config() -> dict:
    """Load config.json from the project root (parent of scripts/)."""
    config_path = pathlib.Path(__file__).parent.parent / 'config.json'
    if not config_path.exists():
        print(f"  config.json not found at {config_path}")
        print("  Copy config.example.json to config.json and edit it.")
        sys.exit(1)
    with open(config_path) as f:
        return json.load(f)


CONFIG = load_config()

APP_NAME = CONFIG['app']['name']
BUNDLE_ID = CONFIG['app']['bundle_id']
DISPLAY_NAME = CONFIG['app'].get('display_name', APP_NAME)
GITHUB_REPO = CONFIG['github']['repo']
ARTIFACT_PATTERN = CONFIG['github'].get('artifact_pattern', APP_NAME)
BRANCH = CONFIG['github'].get('branch', 'main')

OTA_DIR = pathlib.Path(__file__).parent.parent / CONFIG['deploy'].get('ota_dir', '.deploys/ota')
OTA_BASE_URL = os.environ.get('OTA_BASE_URL', CONFIG['deploy']['ota_base_url'])
WEBHOOK_PORT = CONFIG['deploy'].get('webhook_port', 9879)

IPA_FILENAME = f'{APP_NAME}.ipa'
TEMP_DIR = pathlib.Path(f"/tmp/{APP_NAME.lower()}-deploy")


# =============================================================================
# GITHUB API — artifact download
# =============================================================================

def github_api(path: str, token: str) -> dict:
    url = f"https://api.github.com{path}"
    req = urllib.request.Request(url, headers={
        'Authorization': f'token {token}',
        'Accept': 'application/vnd.github.v3+json',
        'User-Agent': f'{APP_NAME}-deploy/1.0',
    })
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"GitHub API error {e.code}: {e.read().decode()}")


def find_latest_run(token: str, run_id: int = None) -> dict:
    if run_id:
        print(f"  Fetching run {run_id}...")
        run = github_api(f"/repos/{GITHUB_REPO}/actions/runs/{run_id}", token)
        conclusion = run.get('conclusion')
        status = run.get('status')
        if conclusion and conclusion != 'success':
            raise RuntimeError(f"Run {run_id} status: {conclusion} (not success)")
        if not conclusion and status != 'in_progress':
            raise RuntimeError(f"Run {run_id} status: {status} (unexpected)")
        print(f"  Run status: {status}, conclusion: {conclusion}")
        return run

    print("  Finding latest successful run...")
    runs = github_api(
        f"/repos/{GITHUB_REPO}/actions/runs?status=success&branch={BRANCH}&per_page=5",
        token
    )

    if not runs.get('workflow_runs'):
        raise RuntimeError("No successful workflow runs found")

    for run in runs['workflow_runs']:
        name = run.get('name', '')
        if ARTIFACT_PATTERN in name or 'Build' in name:
            print(f"  Found run: #{run['run_number']} ({run['created_at']})")
            return run

    run = runs['workflow_runs'][0]
    print(f"  Found run: #{run['run_number']} ({run['created_at']})")
    return run


def download_artifact(run: dict, token: str, dest_dir: pathlib.Path) -> pathlib.Path:
    run_id = run['id']
    print(f"  Fetching artifacts for run {run_id}...")

    artifacts = github_api(
        f"/repos/{GITHUB_REPO}/actions/runs/{run_id}/artifacts",
        token
    )

    ipa_artifact = None
    for artifact in artifacts.get('artifacts', []):
        if ARTIFACT_PATTERN in artifact['name'] and 'app-' not in artifact['name']:
            ipa_artifact = artifact
            break

    if not ipa_artifact:
        available = [a['name'] for a in artifacts.get('artifacts', [])]
        raise RuntimeError(f"No IPA artifact found. Available: {available}")

    print(f"  Downloading: {ipa_artifact['name']} ({ipa_artifact['size_in_bytes']:,} bytes)...")

    # Clear stale temp dir to avoid gh "file exists" errors on retry
    if dest_dir.exists():
        shutil.rmtree(dest_dir, ignore_errors=True)
    dest_dir.mkdir(parents=True, exist_ok=True)

    # Use `gh run download` — handles GitHub's Azure CDN 302 redirect correctly.
    # urllib.request follows the redirect while keeping the Authorization header,
    # which Azure rejects with 403. gh CLI strips auth on the CDN hop.
    result = subprocess.run(
        ['gh', 'run', 'download', str(run_id),
         '--repo', GITHUB_REPO,
         '-n', ipa_artifact['name'],
         '--dir', str(dest_dir)],
        capture_output=True, text=True,
        env={**os.environ, 'GH_TOKEN': token},
    )
    if result.returncode != 0:
        raise RuntimeError(f"gh download failed: {result.stderr.strip() or result.stdout.strip()}")

    # gh downloads the artifact contents directly (not a zip wrapper)
    ipa_path = dest_dir / IPA_FILENAME
    ipa_candidates = list(dest_dir.rglob('*.ipa'))
    if not ipa_candidates:
        # Artifact may be a zip-of-zip — extract if needed
        zip_candidates = list(dest_dir.rglob('*.zip'))
        if not zip_candidates:
            raise RuntimeError(f"No .ipa found after download. Dir: {list(dest_dir.iterdir())}")
        with zipfile.ZipFile(zip_candidates[0]) as zf:
            ipa_names = [n for n in zf.namelist() if n.endswith('.ipa')]
            if not ipa_names:
                raise RuntimeError(f"No .ipa in downloaded zip. Contents: {zf.namelist()}")
            zf.extract(ipa_names[0], dest_dir)
            ipa_candidates = [dest_dir / ipa_names[0]]
        zip_candidates[0].unlink()

    if ipa_candidates[0] != ipa_path:
        shutil.move(str(ipa_candidates[0]), str(ipa_path))

    print(f"  IPA ready: {ipa_path} ({ipa_path.stat().st_size:,} bytes)")
    return ipa_path


# =============================================================================
# OTA DISTRIBUTION — host .ipa + manifest for itms-services://
# =============================================================================

def get_ipa_version(ipa_path: pathlib.Path) -> str:
    """Extract CFBundleShortVersionString from the .ipa's Info.plist."""
    try:
        with zipfile.ZipFile(ipa_path) as zf:
            for name in zf.namelist():
                if name.endswith('Info.plist') and 'Payload/' in name:
                    with zf.open(name) as f:
                        info = plistlib.load(f)
                        return info.get('CFBundleShortVersionString', '1.0')
    except Exception:
        pass
    return '1.0'


def generate_manifest(ipa_url: str, version: str) -> str:
    """Generate the OTA install manifest.plist."""
    manifest = {
        'items': [{
            'assets': [{
                'kind': 'software-package',
                'url': ipa_url,
            }],
            'metadata': {
                'bundle-identifier': BUNDLE_ID,
                'bundle-version': version,
                'kind': 'software',
                'title': DISPLAY_NAME,
            },
        }],
    }
    return plistlib.dumps(manifest, fmt=plistlib.FMT_XML).decode()


def stage_ota(ipa_path: pathlib.Path, sha: str) -> str:
    """Copy .ipa to OTA hosting dir and generate manifest.plist."""
    OTA_DIR.mkdir(parents=True, exist_ok=True)

    dest_ipa = OTA_DIR / IPA_FILENAME
    shutil.copy2(str(ipa_path), str(dest_ipa))
    print(f"  Staged .ipa: {dest_ipa} ({dest_ipa.stat().st_size:,} bytes)")

    version = get_ipa_version(ipa_path)
    print(f"  App version: {version}")

    ipa_url = f"{OTA_BASE_URL}/{IPA_FILENAME}"
    manifest_xml = generate_manifest(ipa_url, version)
    manifest_path = OTA_DIR / 'manifest.plist'
    manifest_path.write_text(manifest_xml)
    print(f"  Manifest: {manifest_path}")

    meta = {
        'app': APP_NAME,
        'sha': sha,
        'version': version,
        'staged_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
        'ipa_size': dest_ipa.stat().st_size,
        'ipa_url': ipa_url,
    }
    (OTA_DIR / 'deploy-meta.json').write_text(json.dumps(meta, indent=2))

    install_url = f"itms-services://?action=download-manifest&url={OTA_BASE_URL}/manifest.plist"
    print(f"  Install URL: {install_url}")
    return install_url


def notify_webhook(sha: str, success: bool, message: str = "", install_url: str = ""):
    """Notify the deploy webhook that staging is complete."""
    try:
        payload = json.dumps({
            'sha': sha,
            'success': success,
            'message': message,
            'install_url': install_url,
            'web_install_url': f"{OTA_BASE_URL}/install",
            'timestamp': int(time.time()),
        }).encode()

        req = urllib.request.Request(
            f'http://127.0.0.1:{WEBHOOK_PORT}/api/deploy/complete',
            data=payload,
            headers={
                'Content-Type': 'application/json',
                'Authorization': f"Bearer {os.environ.get('DEPLOY_WEBHOOK_TOKEN', '')}",
            },
            method='POST'
        )
        urllib.request.urlopen(req, timeout=5)
        print("  Webhook notified (APNs push will be sent)")
    except Exception as e:
        print(f"  Webhook notify failed: {e}")


# =============================================================================
# MAIN
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description=f'Deploy {DISPLAY_NAME} iOS app via OTA (Over-The-Air) install'
    )
    parser.add_argument('--run-id', type=int, help='Specific GitHub Actions run ID')
    parser.add_argument('--ipa', type=str, help='Local .ipa file (skip GitHub download)')
    parser.add_argument('--sha', type=str, default='unknown', help='Git SHA for logging')
    args = parser.parse_args()

    print(f"\n  {DISPLAY_NAME} OTA Deploy")
    print("=" * 50)

    sha = args.sha

    # ---- Get the IPA ----
    if args.ipa:
        ipa_path = pathlib.Path(args.ipa)
        if not ipa_path.exists():
            print(f"  IPA file not found: {ipa_path}")
            return 1
        print(f"\n[1/2] Using local IPA: {ipa_path}")
    else:
        token = os.environ.get('GITHUB_TOKEN')
        if not token:
            print("  GITHUB_TOKEN env var required for artifact download")
            return 1

        print("\n[1/2] Downloading artifact from GitHub Actions...")
        try:
            run = find_latest_run(token, args.run_id)
            sha = run.get('head_sha', sha)
            ipa_path = download_artifact(run, token, TEMP_DIR)
        except Exception as e:
            print(f"  Download failed: {e}")
            return 1

    # ---- Stage for OTA ----
    print("\n[2/2] Staging for OTA distribution...")
    try:
        install_url = stage_ota(ipa_path, sha)
    except Exception as e:
        print(f"  Staging failed: {e}")
        notify_webhook(sha, False, str(e))
        return 1

    # ---- Notify webhook (sends APNs push) ----
    notify_webhook(sha, True, f"OTA update ready: {sha[:8]}", install_url)

    print(f"\n  OTA deploy staged!")
    print(f"   SHA: {sha[:8]}")
    print(f"   Install page: {OTA_BASE_URL}/install")
    print(f"   Direct URL: {install_url}")

    # Clean up temp files
    if not args.ipa and TEMP_DIR.exists():
        try:
            shutil.rmtree(TEMP_DIR)
        except Exception:
            pass

    return 0


if __name__ == '__main__':
    sys.exit(main())
