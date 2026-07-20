"""ローカル確認用の簡易サーバー（開発時のみ・公開には不要）"""
import functools
import http.server
import socketserver

DIRECTORY = "/Users/saki/Desktop/アプリ/kurashi-app"
PORT = 4173

Handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=DIRECTORY)
with socketserver.TCPServer(("127.0.0.1", PORT), Handler) as httpd:
    print(f"serving {DIRECTORY} at http://127.0.0.1:{PORT}")
    httpd.serve_forever()
