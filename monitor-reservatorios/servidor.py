"""Abre o Açude Vivo no navegador e mantém os dados atualizados.

Uso:  python servidor.py            (porta 8765)
      python servidor.py 9000       (outra porta)

- Serve o app em http://localhost:8765
- Ao iniciar, atualiza os dados se tiverem mais de 12 horas
- Enquanto estiver aberto, atualiza de novo a cada 12 horas
"""
import functools
import http.server
import subprocess
import sys
import threading
import time
import webbrowser
from pathlib import Path

PASTA = Path(__file__).resolve().parent
DADOS = PASTA / "dados.json"
PORTA = int(sys.argv[1]) if len(sys.argv) > 1 else 8765
INTERVALO_H = 12


def idade_horas():
    return (time.time() - DADOS.stat().st_mtime) / 3600 if DADOS.exists() else 1e9


def atualizar():
    print(f"[{time.strftime('%d/%m %H:%M')}] Atualizando dados…", flush=True)
    r = subprocess.run([sys.executable, str(PASTA / "atualizar_dados.py")], cwd=PASTA)
    print(f"[{time.strftime('%d/%m %H:%M')}] Atualização {'concluída' if r.returncode == 0 else 'falhou'}", flush=True)


def ciclo():
    while True:
        if idade_horas() >= INTERVALO_H:
            atualizar()
        time.sleep(1800)


class Handler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def end_headers(self):
        if self.path.split("?")[0].endswith(".json"):
            self.send_header("Cache-Control", "no-store")
        super().end_headers()


if __name__ == "__main__":
    if not DADOS.exists():
        atualizar()
    threading.Thread(target=ciclo, daemon=True).start()
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", PORTA),
                                          functools.partial(Handler, directory=str(PASTA)))
    url = f"http://localhost:{PORTA}"
    print(f"Açude Vivo rodando em {url}  (Ctrl+C para sair)", flush=True)
    if "--sem-navegador" not in sys.argv:
        webbrowser.open(url)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
