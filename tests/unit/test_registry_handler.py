"""Unit tests for the pattern registry Vercel handler."""

import json
import time
import sys
import os
from pathlib import Path
from unittest.mock import patch, MagicMock
from io import BytesIO

import pytest

# Add website/ to path so we can import the handler module
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "website"))

from api.patterns import (
    _validate_pattern,
    _validate_attestations,
    _check_rate_limit,
    _check_text_safe,
    _merge_pattern,
    _rate_limits,
)


# ─── Fixtures ───

def _valid_pattern(**overrides):
    """Build a valid pattern dict with optional overrides."""
    p = {
        "fingerprint": "3aab010d317b22df",
        "pattern_type": "co_occurrence",
        "discovery_method": "statistical",
        "sources": ["ci", "git"],
        "metrics": ["ci_presence", "dispersion"],
        "description_statistical": "When ci events occur, dispersion increases.",
        "correlation_strength": 0.38,
        "occurrence_count": 465,
        "confidence_tier": "confirmed",
        "scope": "community",
    }
    p.update(overrides)
    return p


def _valid_attestation(**overrides):
    """Build a valid attestation dict."""
    a = {
        "instance_id": "abcdef0123456789",
        "signature": "a" * 64,
        "timestamp": int(time.time()),
        "ee_version": "0.1.0",
    }
    a.update(overrides)
    return a


@pytest.fixture(autouse=True)
def _clear_rate_limits():
    """Clear rate limits between tests."""
    _rate_limits.clear()
    yield
    _rate_limits.clear()


# ─── Validation: valid patterns ───

class TestValidatePattern:

    def test_valid_pattern_passes(self):
        v, err = _validate_pattern(_valid_pattern())
        assert err is None
        assert v["fingerprint"] == "3aab010d317b22df"
        assert v["pattern_type"] == "co_occurrence"
        assert v["sources"] == ["ci", "git"]
        assert v["metrics"] == ["ci_presence", "dispersion"]

    def test_minimal_pattern(self):
        """Pattern with only required fields passes."""
        p = {
            "fingerprint": "abcdef01",
            "pattern_type": "co_occurrence",
            "discovery_method": "statistical",
            "sources": ["git"],
            "metrics": ["files_touched"],
        }
        v, err = _validate_pattern(p)
        assert err is None
        assert v["fingerprint"] == "abcdef01"

    def test_all_pattern_types(self):
        for pt in ("co_occurrence", "temporal_sequence", "threshold_breach"):
            v, err = _validate_pattern(_valid_pattern(pattern_type=pt))
            assert err is None, f"Failed for pattern_type={pt}"

    def test_all_discovery_methods(self):
        for dm in ("statistical", "semantic", "hybrid"):
            v, err = _validate_pattern(_valid_pattern(discovery_method=dm))
            assert err is None, f"Failed for discovery_method={dm}"


# ─── Validation: fingerprint ───

class TestValidateFingerprint:

    def test_missing_fingerprint(self):
        p = _valid_pattern()
        del p["fingerprint"]
        _, err = _validate_pattern(p)
        assert "fingerprint" in err

    def test_short_fingerprint(self):
        _, err = _validate_pattern(_valid_pattern(fingerprint="abc"))
        assert "fingerprint" in err

    def test_non_hex_fingerprint(self):
        _, err = _validate_pattern(_valid_pattern(fingerprint="ghijklmn"))
        assert "fingerprint" in err

    def test_uppercase_hex_rejected(self):
        _, err = _validate_pattern(_valid_pattern(fingerprint="3AAB010D317B22DF"))
        assert "fingerprint" in err

    def test_too_long_fingerprint(self):
        _, err = _validate_pattern(_valid_pattern(fingerprint="a" * 65))
        assert "fingerprint" in err

    def test_8_char_fingerprint_ok(self):
        v, err = _validate_pattern(_valid_pattern(fingerprint="a" * 8))
        assert err is None

    def test_64_char_fingerprint_ok(self):
        v, err = _validate_pattern(_valid_pattern(fingerprint="a" * 64))
        assert err is None


# ─── Validation: sources and metrics ───

class TestValidateSourcesMetrics:

    def test_empty_sources_rejected(self):
        _, err = _validate_pattern(_valid_pattern(sources=[]))
        assert "sources" in err

    def test_empty_metrics_rejected(self):
        _, err = _validate_pattern(_valid_pattern(metrics=[]))
        assert "metrics" in err

    def test_too_many_sources(self):
        _, err = _validate_pattern(_valid_pattern(sources=[f"s{i}" for i in range(21)]))
        assert "sources" in err

    def test_too_many_metrics(self):
        _, err = _validate_pattern(_valid_pattern(metrics=[f"m{i}" for i in range(21)]))
        assert "metrics" in err

    def test_unsafe_source_name(self):
        _, err = _validate_pattern(_valid_pattern(sources=["git; rm -rf /"]))
        assert "sources" in err

    def test_unsafe_metric_name(self):
        _, err = _validate_pattern(_valid_pattern(metrics=["<script>alert(1)</script>"]))
        assert "metrics" in err

    def test_sources_not_list(self):
        _, err = _validate_pattern(_valid_pattern(sources="git"))
        assert "sources" in err


# ─── Validation: text fields ───

class TestValidateTextFields:

    def test_injection_in_description_rejected(self):
        _, err = _validate_pattern(_valid_pattern(
            description_statistical='<script>alert("xss")</script>'
        ))
        assert "dangerous" in err

    def test_template_injection_rejected(self):
        _, err = _validate_pattern(_valid_pattern(
            description_statistical="Hello {{user.password}}"
        ))
        assert "dangerous" in err

    def test_js_template_injection_rejected(self):
        _, err = _validate_pattern(_valid_pattern(
            description_statistical="Value is ${process.env.SECRET}"
        ))
        assert "dangerous" in err

    def test_shell_injection_rejected(self):
        _, err = _validate_pattern(_valid_pattern(
            description_statistical="test; rm -rf /"
        ))
        assert "dangerous" in err

    def test_path_traversal_rejected(self):
        _, err = _validate_pattern(_valid_pattern(
            description_statistical="file at ../../etc/passwd"
        ))
        assert "dangerous" in err

    def test_javascript_protocol_rejected(self):
        _, err = _validate_pattern(_valid_pattern(
            description_statistical="see javascript:void(0)"
        ))
        assert "dangerous" in err

    def test_long_description_rejected(self):
        _, err = _validate_pattern(_valid_pattern(
            description_statistical="x" * 1001
        ))
        assert "max length" in err

    def test_valid_description_passes(self):
        v, err = _validate_pattern(_valid_pattern(
            description_statistical="When CI events occur, dispersion increases (d=0.32)."
        ))
        assert err is None


# ─── Validation: numeric fields ───

class TestValidateNumericFields:

    def test_correlation_strength_out_of_range(self):
        _, err = _validate_pattern(_valid_pattern(correlation_strength=10.0))
        assert "correlation_strength" in err

    def test_correlation_strength_negative_limit(self):
        _, err = _validate_pattern(_valid_pattern(correlation_strength=-6.0))
        assert "correlation_strength" in err

    def test_correlation_strength_string_rejected(self):
        _, err = _validate_pattern(_valid_pattern(correlation_strength="high"))
        assert "correlation_strength" in err

    def test_negative_occurrence_count(self):
        _, err = _validate_pattern(_valid_pattern(occurrence_count=-1))
        assert "occurrence_count" in err

    def test_float_occurrence_count(self):
        _, err = _validate_pattern(_valid_pattern(occurrence_count=3.5))
        assert "occurrence_count" in err

    def test_valid_boundary_correlation(self):
        v, err = _validate_pattern(_valid_pattern(correlation_strength=5.0))
        assert err is None
        v, err = _validate_pattern(_valid_pattern(correlation_strength=-5.0))
        assert err is None


# ─── Validation: enums ───

class TestValidateEnums:

    def test_invalid_pattern_type(self):
        _, err = _validate_pattern(_valid_pattern(pattern_type="invalid"))
        assert "pattern_type" in err

    def test_invalid_discovery_method(self):
        _, err = _validate_pattern(_valid_pattern(discovery_method="magic"))
        assert "discovery_method" in err

    def test_invalid_confidence_tier(self):
        _, err = _validate_pattern(_valid_pattern(confidence_tier="certain"))
        assert "confidence_tier" in err


# ─── Attestations ───

class TestValidateAttestations:

    def test_valid_attestation(self):
        result = _validate_attestations([_valid_attestation()])
        assert len(result) == 1
        assert result[0]["instance_id"] == "abcdef0123456789"

    def test_invalid_instance_id_skipped(self):
        result = _validate_attestations([_valid_attestation(instance_id="short")])
        assert len(result) == 0

    def test_invalid_signature_skipped(self):
        result = _validate_attestations([_valid_attestation(signature="tooshort")])
        assert len(result) == 0

    def test_future_timestamp_skipped(self):
        result = _validate_attestations([
            _valid_attestation(timestamp=int(time.time()) + 7200)
        ])
        assert len(result) == 0

    def test_duplicate_instance_id_deduped(self):
        att = _valid_attestation()
        result = _validate_attestations([att, att])
        assert len(result) == 1

    def test_max_attestations_enforced(self):
        atts = [
            _valid_attestation(instance_id=f"{i:016x}")
            for i in range(60)
        ]
        result = _validate_attestations(atts)
        assert len(result) == 50  # _MAX_ATTESTATIONS

    def test_non_dict_skipped(self):
        result = _validate_attestations(["not a dict", 42])
        assert len(result) == 0

    def test_not_a_list(self):
        result = _validate_attestations("invalid")
        assert len(result) == 0


# ─── Merge Logic ───

class TestMergePattern:

    def test_new_pattern_added(self):
        store = {"patterns": {}, "submitters": {}}
        p = _valid_pattern()
        v, _ = _validate_pattern(p)
        _merge_pattern(store, v, "abcdef0123456789")

        assert "3aab010d317b22df" in store["patterns"]
        assert store["patterns"]["3aab010d317b22df"]["independent_count"] == 1
        assert store["submitters"]["3aab010d317b22df"] == ["abcdef0123456789"]

    def test_duplicate_fingerprint_merges(self):
        store = {"patterns": {}, "submitters": {}}
        p = _valid_pattern()
        v1, _ = _validate_pattern(p)
        v2, _ = _validate_pattern(p)

        _merge_pattern(store, v1, "aaaa000000000001")
        _merge_pattern(store, v2, "bbbb000000000002")

        fp = "3aab010d317b22df"
        assert store["patterns"][fp]["independent_count"] == 2
        assert len(store["submitters"][fp]) == 2

    def test_same_instance_no_double_count(self):
        store = {"patterns": {}, "submitters": {}}
        p = _valid_pattern()
        v1, _ = _validate_pattern(p)
        v2, _ = _validate_pattern(p)

        instance = "abcdef0123456789"
        _merge_pattern(store, v1, instance)
        _merge_pattern(store, v2, instance)

        fp = "3aab010d317b22df"
        assert store["patterns"][fp]["independent_count"] == 1
        assert store["submitters"][fp] == [instance]

    def test_merge_updates_occurrence_count(self):
        store = {"patterns": {}, "submitters": {}}
        v1, _ = _validate_pattern(_valid_pattern(occurrence_count=100))
        v2, _ = _validate_pattern(_valid_pattern(occurrence_count=200))

        _merge_pattern(store, v1, "aaaa000000000001")
        _merge_pattern(store, v2, "bbbb000000000002")

        assert store["patterns"]["3aab010d317b22df"]["occurrence_count"] == 200

    def test_merge_attestations_dedup(self):
        store = {"patterns": {}, "submitters": {}}
        att1 = _valid_attestation(instance_id="aaaa000000000001")
        att2 = _valid_attestation(instance_id="bbbb000000000002")

        v1, _ = _validate_pattern(_valid_pattern(attestations=[att1]))
        v2, _ = _validate_pattern(_valid_pattern(attestations=[att1, att2]))

        _merge_pattern(store, v1, "aaaa000000000001")
        _merge_pattern(store, v2, "bbbb000000000002")

        atts = store["patterns"]["3aab010d317b22df"]["attestations"]
        ids = {a["instance_id"] for a in atts}
        assert ids == {"aaaa000000000001", "bbbb000000000002"}

    def test_confirmed_tier_on_two_submitters(self):
        store = {"patterns": {}, "submitters": {}}
        v1, _ = _validate_pattern(_valid_pattern(confidence_tier="statistical"))
        v2, _ = _validate_pattern(_valid_pattern(confidence_tier="statistical"))

        _merge_pattern(store, v1, "aaaa000000000001")
        _merge_pattern(store, v2, "bbbb000000000002")

        assert store["patterns"]["3aab010d317b22df"]["confidence_tier"] == "confirmed"

    def test_last_updated_set(self):
        store = {"patterns": {}, "submitters": {}}
        v, _ = _validate_pattern(_valid_pattern())
        _merge_pattern(store, v, "abcdef0123456789")
        assert "last_updated" in store["patterns"]["3aab010d317b22df"]


# ─── Rate Limiting ───

class TestRateLimit:

    def test_first_request_allowed(self):
        assert _check_rate_limit("test_instance_001") is True

    def test_under_limit_allowed(self):
        for _ in range(9):
            _check_rate_limit("test_instance_002")
        assert _check_rate_limit("test_instance_002") is True

    def test_over_limit_blocked(self):
        for _ in range(10):
            _check_rate_limit("test_instance_003")
        assert _check_rate_limit("test_instance_003") is False

    def test_old_entries_expire(self):
        iid = "test_instance_004"
        # Simulate 10 requests from >1 hour ago
        _rate_limits[iid] = [time.time() - 3700] * 10
        assert _check_rate_limit(iid) is True


# ─── Text Safety ───

class TestTextSafety:

    def test_safe_text(self):
        val, err = _check_text_safe("Normal description text.", "field")
        assert err is None
        assert val == "Normal description text."

    def test_strips_whitespace(self):
        val, err = _check_text_safe("  padded  ", "field")
        assert val == "padded"

    def test_non_string_rejected(self):
        val, err = _check_text_safe(42, "field")
        assert err is not None

    def test_too_long_rejected(self):
        val, err = _check_text_safe("x" * 100, "field", max_len=50)
        assert "max length" in err


# ─── Handler Integration (mocked Redis) ───

class TestHandlerIntegration:
    """Test the handler end-to-end with mocked Redis."""

    def _make_handler(self, method, path, body=None):
        """Create a mock handler and invoke it."""
        from api.patterns import handler as HandlerClass

        # Build a mock request
        mock_wfile = BytesIO()
        mock_rfile = BytesIO()
        if body:
            raw = json.dumps(body).encode("utf-8")
            mock_rfile.write(raw)
            mock_rfile.seek(0)

        # We need to mock BaseHTTPRequestHandler.__init__ to avoid socket issues
        h = HandlerClass.__new__(HandlerClass)
        h.wfile = mock_wfile
        h.rfile = mock_rfile
        h.path = path
        h.headers = {}
        if body:
            h.headers = {"Content-Length": str(len(json.dumps(body).encode("utf-8")))}

        # Capture response
        h._response_code = None
        h._response_headers = {}

        def send_response(code):
            h._response_code = code
        def send_header(key, val):
            h._response_headers[key] = val
        def end_headers():
            pass

        h.send_response = send_response
        h.send_header = send_header
        h.end_headers = end_headers

        if method == "GET":
            h.do_GET()
        elif method == "POST":
            h.do_POST()

        # Parse response body
        h.wfile.seek(0)
        resp_body = h.wfile.read().decode("utf-8")
        return h._response_code, json.loads(resp_body) if resp_body else {}

    @patch("api.patterns._redis_get", return_value={"patterns": {}, "submitters": {}})
    @patch("api.patterns._redis_set", return_value=True)
    @patch("api.patterns._axiom_send")
    def test_post_valid_patterns(self, mock_axiom, mock_set, mock_get):
        payload = {
            "level": 2,
            "instance_id": "abcdef0123456789",
            "patterns": [_valid_pattern()],
        }
        code, resp = self._make_handler("POST", "/api/patterns", payload)
        assert code == 200
        assert resp["accepted"] == 1
        mock_set.assert_called_once()

    @patch("api.patterns._redis_get", return_value={"patterns": {}, "submitters": {}})
    @patch("api.patterns._redis_set", return_value=True)
    @patch("api.patterns._axiom_send")
    def test_post_level1_metadata(self, mock_axiom, mock_set, mock_get):
        payload = {"level": 1, "metadata": {"families": ["git"]}}
        code, resp = self._make_handler("POST", "/api/patterns", payload)
        assert code == 200
        assert resp["accepted"] == 0
        mock_set.assert_not_called()

    @patch("api.patterns._redis_get", return_value={"patterns": {}, "submitters": {}})
    @patch("api.patterns._axiom_send")
    def test_post_invalid_instance_id(self, mock_axiom, mock_get):
        payload = {
            "level": 2,
            "instance_id": "bad",
            "patterns": [_valid_pattern()],
        }
        code, resp = self._make_handler("POST", "/api/patterns", payload)
        assert code == 400
        assert "instance_id" in resp["error"]

    @patch("api.patterns._redis_get", return_value={"patterns": {}, "submitters": {}})
    @patch("api.patterns._redis_set", return_value=True)
    @patch("api.patterns._axiom_send")
    def test_post_rejects_bad_pattern(self, mock_axiom, mock_set, mock_get):
        payload = {
            "level": 2,
            "instance_id": "abcdef0123456789",
            "patterns": [{"fingerprint": "BAD"}],
        }
        code, resp = self._make_handler("POST", "/api/patterns", payload)
        assert code == 400
        assert "rejected" in resp["error"].lower()

    @patch("api.patterns._redis_get")
    @patch("api.patterns._axiom_send")
    def test_get_returns_patterns(self, mock_axiom, mock_get):
        mock_get.return_value = {
            "patterns": {
                "3aab010d317b22df": {
                    **_valid_pattern(),
                    "independent_count": 2,
                    "last_updated": "2026-02-14T00:00:00Z",
                }
            },
            "submitters": {},
        }
        code, resp = self._make_handler("GET", "/api/patterns")
        assert code == 200
        assert len(resp["patterns"]) == 1

    @patch("api.patterns._redis_get")
    @patch("api.patterns._axiom_send")
    def test_get_since_filters(self, mock_axiom, mock_get):
        mock_get.return_value = {
            "patterns": {
                "aaa": {**_valid_pattern(fingerprint="aa" * 4), "last_updated": "2026-01-01T00:00:00Z"},
                "bbb": {**_valid_pattern(fingerprint="bb" * 4), "last_updated": "2026-02-14T00:00:00Z"},
            },
            "submitters": {},
        }
        code, resp = self._make_handler("GET", "/api/patterns?since=2026-02-01T00:00:00Z")
        assert code == 200
        assert len(resp["patterns"]) == 1

    @patch("api.patterns._redis_get", return_value={"patterns": {}, "submitters": {}})
    @patch("api.patterns._axiom_send")
    def test_post_rate_limited(self, mock_axiom, mock_get):
        instance = "abcdef0123456789"
        # Exhaust rate limit
        _rate_limits[instance] = [time.time()] * 10

        payload = {
            "level": 2,
            "instance_id": instance,
            "patterns": [_valid_pattern()],
        }
        code, resp = self._make_handler("POST", "/api/patterns", payload)
        assert code == 429

    @patch("api.patterns._redis_get", return_value={"patterns": {}, "submitters": {}})
    @patch("api.patterns._axiom_send")
    def test_post_invalid_level(self, mock_axiom, mock_get):
        payload = {"level": 5}
        code, resp = self._make_handler("POST", "/api/patterns", payload)
        assert code == 400
        assert "level" in resp["error"].lower()

    @patch("api.patterns._redis_get", return_value={"patterns": {}, "submitters": {}})
    @patch("api.patterns._redis_set", return_value=True)
    @patch("api.patterns._axiom_send")
    def test_post_mixed_valid_invalid(self, mock_axiom, mock_set, mock_get):
        """Some valid, some invalid patterns — valid ones accepted."""
        payload = {
            "level": 2,
            "instance_id": "abcdef0123456789",
            "patterns": [
                _valid_pattern(),
                {"fingerprint": "BAD"},
            ],
        }
        code, resp = self._make_handler("POST", "/api/patterns", payload)
        assert code == 200
        assert resp["accepted"] == 1
        assert resp["rejected"] == 1

    @patch("api.patterns._redis_get", return_value={"patterns": {}, "submitters": {}})
    @patch("api.patterns._redis_set", return_value=False)
    @patch("api.patterns._axiom_send")
    def test_post_redis_write_failure(self, mock_axiom, mock_set, mock_get):
        payload = {
            "level": 2,
            "instance_id": "abcdef0123456789",
            "patterns": [_valid_pattern()],
        }
        code, resp = self._make_handler("POST", "/api/patterns", payload)
        assert code == 500
        assert "storage" in resp["error"].lower()
