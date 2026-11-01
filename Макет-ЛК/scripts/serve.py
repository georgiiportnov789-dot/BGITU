#!/usr/bin/env python3
"""Локальный сервер для макета БГИТУ.

Зачем: `python3 -m http.server` отдаёт HTTP/1.0 и при параллельной загрузке
файлов (шрифты + CSS + JS) может сбрасывать соединения — страница остаётся
без скриптов. Этот сервер использует HTTP/1.1, потоки и корректные MIME.

Запуск:  python3 scripts/serve.py [порт]
Открыть: http://127.0.0.1:8787/cabinet.html
"""

import os
import sys
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer


class Handler(SimpleHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'
    extensions_map = {
        **SimpleHTTPRequestHandler.extensions_map,
        '.js': 'text/javascript; charset=utf-8',
        '.mjs': 'text/javascript; charset=utf-8',
        '.css': 'text/css; charset=utf-8',
        '.woff2': 'font/woff2',
        '.svg': 'image/svg+xml',
        '.md': 'text/markdown; charset=utf-8',
        '.json': 'application/json; charset=utf-8',
    }

    def end_headers(self):
        self.send_header('Cache-Control', 'no-store')
        super().end_headers()

    def log_message(self, fmt, *args):  # тише: только ошибки
        status = args[1] if len(args) > 1 else ''
        if str(status).startswith(('4', '5')):
            super().log_message(fmt, *args)


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8787
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    os.chdir(root)
    httpd = ThreadingHTTPServer(('127.0.0.1', port), Handler)
    print(f'БГИТУ: http://127.0.0.1:{port}/cabinet.html  (Ctrl+C — стоп)')
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == '__main__':
    main()
