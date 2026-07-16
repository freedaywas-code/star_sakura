import http.server
import os
import urllib.request

BACKEND_BASE = 'http://127.0.0.1:8000'

class ProxyHTTPRequestHandler(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header('Cache-Control', 'no-cache, no-store, must-revalidate')
        self.send_header('Pragma', 'no-cache')
        self.send_header('Expires', '0')
        self.send_header('Access-Control-Allow-Origin', '*')
        super().end_headers()
    
    def do_GET(self):
        if self.path.startswith('/media/') or self.path.startswith('/artworks/'):
            backend_url = BACKEND_BASE + self.path
            try:
                with urllib.request.urlopen(backend_url) as response:
                    content_type = response.headers.get('Content-Type', 'application/octet-stream')
                    content_length = response.headers.get('Content-Length', '')
                    
                    self.send_response(200)
                    self.send_header('Content-Type', content_type)
                    if content_length:
                        self.send_header('Content-Length', content_length)
                    self.end_headers()
                    
                    self.wfile.write(response.read())
                    return
            except Exception as e:
                self.send_response(404)
                self.end_headers()
                return
        
        super().do_GET()

if __name__ == '__main__':
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    server_address = ('', 5173)
    httpd = http.server.HTTPServer(server_address, ProxyHTTPRequestHandler)
    print('Server running on http://localhost:5173')
    httpd.serve_forever()
