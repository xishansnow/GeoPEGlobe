import json
import socket
import threading
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen
import pytest
from geope_globe.server import BoundedHTTPServer, Handler


@pytest.fixture
def server():
    value=BoundedHTTPServer(('127.0.0.1',0),Handler,max_connections=2,read_timeout=.4)
    thread=threading.Thread(target=value.serve_forever,daemon=True);thread.start()
    yield value
    value.shutdown();value.server_close();thread.join(timeout=2)


def test_null_static_path_returns_error_not_disconnect(server):
    with pytest.raises(HTTPError) as caught:urlopen(f'http://127.0.0.1:{server.server_port}/%00',timeout=2)
    assert caught.value.code==400


def test_slow_body_has_read_timeout(server):
    with socket.create_connection(server.server_address,timeout=2) as connection:
        connection.sendall(b'POST /api/evaluate HTTP/1.0\r\nContent-Type: application/json\r\nContent-Length: 10\r\n\r\n{')
        assert b'408' in connection.recv(4096)


def test_connections_are_bounded_before_body_read(server):
    sockets=[]
    try:
        for _ in range(2):
            s=socket.create_connection(server.server_address,timeout=2)
            s.sendall(b'POST /api/evaluate HTTP/1.0\r\nContent-Type: application/json\r\nContent-Length: 100\r\n\r\n{')
            sockets.append(s)
        deadline=time.monotonic()+.25
        while server.active_connections<2 and time.monotonic()<deadline:time.sleep(.002)
        assert server.active_connections==2
        with pytest.raises(HTTPError) as caught:urlopen(f'http://127.0.0.1:{server.server_port}/api/health',timeout=.25)
        assert caught.value.code==503
    finally:
        for s in sockets:s.close()


def test_evaluation_and_path_traversal(server):
    base=f'http://127.0.0.1:{server.server_port}'
    with urlopen(base+'/api/health',timeout=2) as r:assert json.load(r)['ok']
    request=Request(base+'/api/evaluate',data=json.dumps({'config':{'encoder':'xyz'},'grid':{'nlat':16,'nlon':32}}).encode(),headers={'Content-Type':'application/json'})
    with urlopen(request,timeout=2) as r:assert json.load(r)['info']['rank']==3
    with pytest.raises(HTTPError) as caught:urlopen(base+'/%2e%2e/server.py',timeout=2)
    assert caught.value.code==404


def test_paper_figure_endpoint_returns_png(server):
    base=f'http://127.0.0.1:{server.server_port}'
    sample={'config':{'encoder':'xyz'},'grid':{'nlat':16,'nlon':32},'anchor':{'lon':110,'lat':35},'band':{'min':0,'max':3}}
    body={'theme':'paper','layer':'raw_similarity','colors_locked':True,'show_region':False,
          'show_centers':False,'requests':[sample,sample]}
    request=Request(base+'/api/export/figure',data=json.dumps(body).encode(),headers={'Content-Type':'application/json'})
    with urlopen(request,timeout=15) as response:
        assert response.headers['Content-Type']=='image/png'
        assert response.read(8)==b'\x89PNG\r\n\x1a\n'
