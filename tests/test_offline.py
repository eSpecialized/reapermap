"""Network-block test: prove zero network calls during map generation.

Monkeypatches ``socket`` so any attempt to open a network connection raises.
If the engine touches the network, these tests fail.
"""

import socket

import pytest

from privrepomap.filescan import find_src_files, read_text
from privrepomap.repomap import RepoMap
from privrepomap.tokenizer import count_tokens


class _BlockedSocket(socket.socket):
    def __init__(self, *args, **kwargs):
        raise OSError("Network access is blocked in offline tests")


@pytest.fixture()
def no_network(monkeypatch):
    def _blocked_connect(*args, **kwargs):
        raise OSError("Network access is blocked in offline tests")

    monkeypatch.setattr(socket, "socket", _BlockedSocket)
    monkeypatch.setattr(socket, "create_connection", _blocked_connect)
    monkeypatch.setattr(socket.socket, "connect", _blocked_connect, raising=False)
    yield


def test_tokenizer_offline(no_network):
    assert count_tokens("def f(): return 1", strategy="heuristic") > 0
    assert count_tokens("def f(): return 1", strategy="pygments") > 0


def test_map_generation_offline(no_network, fixture_repo):
    mapper = RepoMap(map_tokens=2048, root=str(fixture_repo), file_reader_func=read_text,
                     output_handler_funcs={"info": lambda *a: None,
                                           "warning": lambda *a: None,
                                           "error": lambda *a: None})
    others = find_src_files(str(fixture_repo))
    map_content, report = mapper.get_repo_map(other_files=others)
    assert map_content is not None
    assert report.definition_matches > 0
