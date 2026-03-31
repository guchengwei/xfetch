from pathlib import Path
import json

from xfetch.backends.fxtwitter import parse_fxtwitter_payload


def test_parse_fxtwitter_payload_extracts_minimum_fields():
    payload = json.loads(Path("tests/fixtures/fxtwitter_single_tweet.json").read_text())
    raw = parse_fxtwitter_payload(payload)
    assert raw["tweet_id"]
    assert raw["screen_name"]
    assert raw["text"]
