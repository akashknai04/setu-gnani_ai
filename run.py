"""One-command run.

    python run.py                 # this computer only: http://127.0.0.1:8000
    python run.py --lan           # also reachable from phones on the same Wi-Fi
    python run.py --lan --https   # phones need https for the microphone (self-signed certificate)
    python run.py --public        # real phone call: opens a public https tunnel for Gnani Inya (cloudflared)

Then open /call (rider's phone) and /customer (Asha's phone).
"""
import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def make_cert(ip: str | None) -> tuple[str, str]:
    """Self-signed certificate for local demos, made with openssl. Reused if already present."""
    d = ROOT / "data" / "certs"
    d.mkdir(parents=True, exist_ok=True)
    key, crt = d / "key.pem", d / "cert.pem"
    if key.exists() and crt.exists():
        return str(key), str(crt)
    if not shutil.which("openssl"):
        sys.exit("--https needs openssl (macOS/Linux have it; on Windows install Git for Windows, which includes it).")
    san = "DNS:localhost,IP:127.0.0.1" + (f",IP:{ip}" if ip else "")
    subprocess.run(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "30",
                    "-keyout", str(key), "-out", str(crt), "-subj", "/CN=SETU AI local demo",
                    "-addext", f"subjectAltName={san}"], check=True, capture_output=True)
    return str(key), str(crt)


def start_tunnel(port: int) -> None:
    """Free Cloudflare quick tunnel -> prints the public https URL for  call_me.py setup --public-url."""
    import re
    import threading
    exe = shutil.which("cloudflared")
    if not exe:
        print("  --public needs cloudflared: https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/")
        print("  (Windows: winget install --id Cloudflare.cloudflared   macOS: brew install cloudflared)")
        return
    from backend.config import settings
    if not settings.inya_bridge_token:
        print("  WARNING: INYA_BRIDGE_TOKEN is empty in .env, so /inya/turn will refuse every call.")
    proc = subprocess.Popen([exe, "tunnel", "--no-autoupdate", "--url", f"http://127.0.0.1:{port}"],
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)

    def watch():
        for line in proc.stdout:
            m = re.search(r"https://[a-z0-9-]+\.trycloudflare\.com", line)
            if m:
                url = m.group(0)
                print(f"\n  PUBLIC URL (for Gnani): {url}")
                print(f"  next, in a second terminal:  python call_me.py setup --public-url {url}")
                print("  then:                        python call_me.py call\n")
                return
    threading.Thread(target=watch, daemon=True).start()


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--lan", action="store_true", help="listen on the local network so phones can connect")
    ap.add_argument("--https", action="store_true", help="serve over https (phones need it for the microphone)")
    ap.add_argument("--public", action="store_true",
                    help="open a public https tunnel (cloudflared) so Gnani Inya can reach /inya/turn")
    ap.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8000")))
    a = ap.parse_args()

    import uvicorn

    from backend.config import FFmpegMissing, check_ffmpeg
    from backend.main import _lan_ip, app

    try:
        print(check_ffmpeg())
    except FFmpegMissing as e:
        sys.exit(str(e))
    host = "0.0.0.0" if a.lan else os.environ.get("HOST", "127.0.0.1")
    scheme = "https" if a.https else "http"
    ip = _lan_ip() if a.lan else None
    app.state.port, app.state.scheme = a.port, scheme
    ssl = {}
    if a.https:
        key, crt = make_cert(ip)
        ssl = {"ssl_keyfile": key, "ssl_certfile": crt}
    print("\nSETU AI")
    print(f"  this computer : {scheme}://127.0.0.1:{a.port}/        (rider: /call   Asha: /customer)")
    if ip:
        print(f"  phones on Wi-Fi: {scheme}://{ip}:{a.port}/call   and   {scheme}://{ip}:{a.port}/customer")
        if not a.https:
            print("  note: phones block the microphone on plain http. Add --https for the rider's phone.")
        else:
            print("  first visit on each phone: accept the certificate warning (it is your own local certificate).")
    if a.public:
        start_tunnel(a.port)
    print()
    uvicorn.run(app, host=host, port=a.port, **ssl)
