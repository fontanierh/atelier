import socket

from atelier import live


def test_free_port_is_a_loopback_port_a_game_can_bind():
    port = live.free_port()
    assert 1024 < port < 65536
    with socket.socket() as s:
        s.bind(('127.0.0.1', port))
