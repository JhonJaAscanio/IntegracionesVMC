"""Punto de entrada: inicia el servidor local en http://127.0.0.1:5000."""
import sys
import webbrowser
from pathlib import Path
from threading import Timer

from wposs_vim import create_app
from wposs_vim.excel_store import StoreError


def main():
    base = Path(__file__).resolve().parent
    try:
        app = create_app(base)
    except StoreError as exc:
        print(f"\n[ERROR] {exc}\n")
        return 1
    server = app.extensions["wposs"]["config"]["servidor"]
    host = server.get("host", "127.0.0.1")
    if host not in ("127.0.0.1", "localhost", "::1"):
        print("[ERROR] Por seguridad la aplicación solo escucha en 127.0.0.1.")
        return 1
    port = int(server.get("puerto", 5000))
    url = f"http://127.0.0.1:{port}"
    print(f"\n  WPOSS Vending Integration Manager\n  Abra {url} en Chrome o Edge.\n  Cierre esta ventana para detener la aplicación.\n")
    if "--no-browser" not in sys.argv:
        Timer(1.2, lambda: webbrowser.open(url)).start()
    try:
        from waitress import serve
        serve(app, host="127.0.0.1", port=port, threads=4)
    except ImportError:
        app.run(host="127.0.0.1", port=port, debug=False, use_reloader=False, threaded=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
