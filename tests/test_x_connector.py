from pathlib import Path
import json

from xfetch.backends.fxtwitter import parse_fxtwitter_payload
from xfetch.connectors.x import XConnector


def test_parse_fxtwitter_payload_extracts_minimum_fields():
    payload = json.loads(Path("tests/fixtures/fxtwitter_single_tweet.json").read_text())
    raw = parse_fxtwitter_payload(payload)
    assert raw["tweet_id"]
    assert raw["screen_name"]
    assert raw["text"]



def test_x_connector_normalizes_fixture_payload():
    payload = json.loads(Path("tests/fixtures/fxtwitter_single_tweet.json").read_text())
    connector = XConnector()
    doc = connector.normalize_payload(
        source_url="https://x.com/alice/status/123",
        payload=payload,
    )
    assert doc.source_type == "x"
    assert doc.external_id == "123"
    assert doc.author_handle == "alice"
    assert doc.metadata["platform"] == "x"
    assert doc.lineage["backend"] == "fxtwitter"
