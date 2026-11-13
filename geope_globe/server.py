#!/usr/bin/env python3
"""Serve the local encoder globe and its numerical API. Run with --help."""
import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import mimetypes
import os
from pathlib import Path
import sys
import threading
from urllib.parse import unquote, urlparse

# Set thread budgets before importing the numerical libraries.
for name in ['OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'MKL_NUM_THREADS']:
    os.environ.setdefault(name, '1')
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from geope_globe.src.service import catalog, compute

WEB = Path(__file__).resolve().parent/'web'
SLOTS = threading.BoundedSemaphore(2)


class BoundedHTTPServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address, handler, max_connections=12, read_timeout=10):
        self._connections = threading.BoundedSemaphore(max_connections)
        self._count_lock = threading.Lock()
        self._connection_count = 0
        self.read_timeout = read_timeout
        super().__init__(address, handler)

    @property
    def active_connections(self):
        with self._count_lock:
            return self._connection_count

    def process_request(self, request, address):
        request.settimeout(self.read_timeout)
        if not self._connections.acquire(blocking=False):
            data = json.dumps({'error': '连接数已达上限，请稍后重试'}, ensure_ascii=False).encode()
            try:
                request.sendall(b'HTTP/1.0 503 Service Unavailable\r\nContent-Type: application/json; charset=utf-8\r\nContent-Length: '+str(len(data)).encode()+b'\r\nConnection: close\r\n\r\n'+data)
            except OSError:
                pass
            self.shutdown_request(request)
            return
        with self._count_lock:
            self._connection_count += 1
        try:
            super().process_request(request, address)
        except BaseException:
            self._release_connection()
            raise

    def _release_connection(self):
        with self._count_lock:
            self._connection_count -= 1
        self._connections.release()

    def process_request_thread(self, request, address):
        try:
            super().process_request_thread(request, address)
        finally:
            self._release_connection()


class Handler(BaseHTTPRequestHandler):
    def send(self, status, value, content_type='application/json; charset=utf-8'):
        data = value if isinstance(value, bytes) else json.dumps(value, ensure_ascii=False, allow_nan=False).encode()
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(data)))
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Cache-Control', 'no-cache')
        self.end_headers()
        try:
            self.wfile.write(data)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def do_GET(self):
        path = urlparse(self.path).path
        if path == '/api/health':
            return self.send(200, {'ok': True})
        if path == '/api/catalog':
            return self.send(200, catalog())
        try:
            relative = unquote(path).lstrip('/') or 'index.html'
            if '\x00' in relative:
                raise ValueError('NUL in path')
            target = (WEB/relative).resolve()
        except (ValueError, OSError):
            return self.send(400, {'error': '无效文件路径'})
        if not target.is_relative_to(WEB.resolve()) or not target.is_file():
            return self.send(404, {'error': '文件不存在'})
        self.send(200, target.read_bytes(), mimetypes.guess_type(str(target))[0] or 'application/octet-stream')

    def do_POST(self):
        path = urlparse(self.path).path
        if path not in {'/api/evaluate', '/api/export/figure'}:
            return self.send(404, {'error': '未知接口'})
        origin = self.headers.get('Origin')
        if origin and urlparse(origin).netloc != self.headers.get('Host'):
            return self.send(403, {'error': '只接受同源请求'})
        if self.headers.get_content_type() != 'application/json':
            return self.send(415, {'error': '请使用 application/json'})
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if not 1 <= length <= 65536:
                return self.send(413, {'error': '请求大小须为 1…65536 字节'})
            body = json.loads(self.rfile.read(length))
        except TimeoutError:
            self.close_connection = True
            return self.send(408, {'error': '读取请求超时'})
        except (ValueError, UnicodeDecodeError):
            return self.send(400, {'error': '请求不是有效 JSON'})
        if not SLOTS.acquire(blocking=False):
            return self.send(503, {'error': '数值服务正在处理两个请求，请稍候重试'})
        try:
            if path == '/api/export/figure':
                if not isinstance(body, dict) or body.get('theme') != 'paper' or body.get('layer') not in {
                        'raw_similarity', 'similarity', 'kernel', 'energy', 'channel', 'region', 'centers'} or \
                        not isinstance(body.get('requests'), list) or len(body['requests']) != 2 or \
                        not isinstance(body.get('colors_locked'), bool) or \
                        not isinstance(body.get('show_region'), bool) or not isinstance(body.get('show_centers'), bool):
                    raise ValueError('论文图需要两个请求、受支持的图层及明确的共同色标设置')
                from geope_globe.src.figure_export import render_publication_png
                result = render_publication_png([compute(request) for request in body['requests']],
                                                body['layer'], body['colors_locked'],
                                                body['show_region'], body['show_centers'], body['requests'])
            else:
                result = compute(body)
        except (ValueError, TypeError, IndexError) as exc:
            return self.send(400, {'error': str(exc)})
        except Exception as exc:
            self.log_error('numerical computation failed: %s', exc)
            return self.send(500, {'error': '数值计算失败，请检查配置或服务日志'})
        finally:
            SLOTS.release()
        self.send(200, result, 'image/png' if path == '/api/export/figure' else 'application/json; charset=utf-8')


def main():
    parser = argparse.ArgumentParser(description='地理位置编码器交互地球，固定前端数值可视化')
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=8876)
    args = parser.parse_args()
    try:
        server = BoundedHTTPServer((args.host, args.port), Handler)
    except OSError as exc:
        parser.exit(2, f'无法监听 {args.host}:{args.port}：{exc}。请换用 --port，或 --port 0 自动分配。\n')
    print(f'Encoder Globe: http://{args.host}:{server.server_port}', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
