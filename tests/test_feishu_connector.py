import json

import pytest
from urllib.error import HTTPError

from xfetch.connectors.feishu import FeishuConnector


class FakeResponse:
    def __init__(self, body: str, url: str, content_type: str = "application/json"):
        self._body = body.encode("utf-8")
        self._url = url
        self.headers = {"Content-Type": content_type}

    def read(self):
        return self._body

    def geturl(self):
        return self._url

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


def _text_block(block_id: str, kind: str, text: str, **extra) -> dict:
    data = {
        "type": kind,
        "children": [],
        "text": {"initialAttributedTexts": {"text": {"0": text}}},
    }
    data.update(extra)
    return {"id": block_id, "data": data}


def _client_payload() -> dict:
    return {
        "code": 0,
        "msg": "success",
        "data": {
            "has_more": False,
            "meta_map": {"OBJ": {"title": "Example Doc", "create_time": "2026-04-07T21:38:31.079+08:00"}},
            "block_map": {
                "PAGE": {"id": "PAGE", "data": {"type": "page", "children": ["H", "T", "O1", "O2", "B", "TBL", "IMG"]}},
                "H": _text_block("H", "heading2", "Section"),
                "T": _text_block("T", "text", "Hello wiki"),
                "O1": _text_block("O1", "ordered", "First", seq="1"),
                "O2": _text_block("O2", "ordered", "Second", seq="auto"),
                "B": _text_block("B", "bullet", "Dot"),
                "TBL": {"id": "TBL", "data": {
                    "type": "table",
                    "children": [],
                    "rows_id": ["row1", "row2"],
                    "columns_id": ["col1"],
                    "cell_set": {
                        "row1col1": {"block_id": "C1"},
                        "row2col1": {"block_id": "C2"},
                    },
                }},
                "C1": _text_block("C1", "table_cell", "Head"),
                "C2": _text_block("C2", "table_cell", "Cell"),
                "IMG": {"id": "IMG", "data": {"type": "image", "children": [], "image": {"token": "abc"}}},
            },
        },
    }


def _route(monkeypatch, node=None, client=None, wiki_status=None):
    calls = []
    node = node if node is not None else {
        "code": 0,
        "data": {"obj_token": "OBJ", "obj_type": 22, "title": "Example Doc"},
    }
    client = client if client is not None else _client_payload()

    def fake(request, timeout=15, cookie_jar=None):
        calls.append(request.full_url)
        assert cookie_jar is not None
        if wiki_status is not None and "get_node" not in request.full_url and "client_vars" not in request.full_url:
            raise HTTPError(request.full_url, wiki_status, "redirect", {}, None)
        if "client_vars" in request.full_url:
            return FakeResponse(json.dumps(client), request.full_url)
        if "get_node" in request.full_url:
            return FakeResponse(json.dumps(node), request.full_url)
        return FakeResponse("<html>ok</html>", request.full_url, "text/html")

    monkeypatch.setattr("xfetch.connectors.feishu.urlopen", fake)
    return calls


def test_feishu_connector_renders_public_wiki_document(monkeypatch):
    calls = _route(monkeypatch)
    doc = FeishuConnector().fetch("https://example.feishu.cn/wiki/WIKITOKEN?from=copy")
    assert doc.source_type == "feishu"
    assert doc.external_id == "WIKITOKEN"
    assert doc.canonical_url == "https://example.feishu.cn/wiki/WIKITOKEN"
    assert doc.title == "Example Doc"
    assert doc.author == "example.feishu.cn"
    assert doc.created_at == "2026-04-07T21:38:31.079+08:00"
    assert "## Section" in doc.markdown
    assert "Hello wiki" in doc.text
    assert "1. First\n2. Second" in doc.markdown
    assert "- Dot" in doc.markdown
    assert "| Head |" in doc.markdown
    assert "| Cell |" in doc.markdown
    assert doc.capture_status == "partial"
    assert doc.metadata["capture_limitation"] == "Feishu images were not preserved."
    assert doc.metadata["obj_token"] == "OBJ"
    assert any("wiki_token=WIKITOKEN" in call for call in calls)
    assert any("id=OBJ" in call for call in calls)


def test_feishu_connector_text_only_document_is_complete(monkeypatch):
    client = _client_payload()
    page = client["data"]["block_map"]["PAGE"]["data"]
    page["children"] = ["H", "T"]
    _route(monkeypatch, client=client)
    doc = FeishuConnector().fetch("https://example.feishu.cn/wiki/WIKITOKEN")
    assert doc.capture_status == "complete"
    assert "capture_limitation" not in doc.metadata
    assert "Hello wiki" in doc.text


def test_feishu_connector_reads_docx_without_wiki_lookup(monkeypatch):
    calls = _route(monkeypatch)
    doc = FeishuConnector().fetch("https://tenant.larkoffice.com/docx/OBJ")
    assert doc.external_id == "OBJ"
    assert doc.title == "Example Doc"
    assert not any("get_node" in call for call in calls)
    assert any("client_vars" in call and "id=OBJ" in call for call in calls)


def test_feishu_connector_rejects_private_wiki(monkeypatch):
    calls = _route(monkeypatch, node={"code": 920004004, "msg": "PermFail", "data": None})
    with pytest.raises(ValueError, match="not publicly readable"):
        FeishuConnector().fetch("https://example.feishu.cn/wiki/WIKITOKEN")
    assert not any("client_vars" in call for call in calls)


def test_feishu_connector_rejects_non_document_wiki_node(monkeypatch):
    _route(monkeypatch, node={"code": 0, "data": {"obj_token": "OBJ", "obj_type": 8, "title": "Sheet"}})
    with pytest.raises(ValueError, match="not a document"):
        FeishuConnector().fetch("https://example.feishu.cn/wiki/WIKITOKEN")


def test_feishu_connector_rejects_login_redirect(monkeypatch):
    _route(monkeypatch, wiki_status=302)
    with pytest.raises(ValueError, match="not publicly readable"):
        FeishuConnector().fetch("https://example.feishu.cn/wiki/WIKITOKEN")


def test_feishu_connector_matches_wiki_and_docx_urls_only():
    connector = FeishuConnector()
    assert connector.can_handle("https://example.feishu.cn/wiki/WIKITOKEN") is True
    assert connector.can_handle("https://tenant.larksuite.com/docx/OBJ") is True
    assert connector.can_handle("https://example.feishu.cn/drive/home") is False
    assert connector.can_handle("https://zhuanlan.zhihu.com/p/692256732") is False
