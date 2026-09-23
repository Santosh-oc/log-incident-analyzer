"""Unit tests for message fingerprinting."""
from app.parsing.fingerprint import fingerprint


def test_numbers_normalized():
    assert fingerprint("Timeout calling bank-gateway after 30000ms (order_id=A1923)") == (
        "timeout calling bank-gateway after <n>ms (order_id=a<n>)"
    )


def test_uuid_normalized():
    msg = "Failed request 550e8400-e29b-41d4-a716-446655440000 took 120ms"
    assert fingerprint(msg) == "failed request <uuid> took <n>ms"


def test_ip_normalized():
    assert fingerprint("Connection from 192.168.1.10 refused") == "connection from <ip> refused"
    assert fingerprint("connect 10.0.0.1:5432 failed") == "connect <ip>:<n> failed"


def test_hex_normalized():
    assert fingerprint("trace abcdef1234567890 done") == "trace <hex> done"
    # Short hex (fewer than 8 chars) is not treated as hex; its digits still normalize.
    assert fingerprint("code ab12 ok") == "code ab<n> ok"


def test_quoted_strings_normalized():
    assert fingerprint('User "jane doe" logged in') == "user <str> logged in"
    assert fingerprint("Value 'x9' rejected") == "value <str> rejected"


def test_whitespace_collapsed():
    assert fingerprint("a   b\n\tc") == "a b c"


def test_case_insensitive():
    assert fingerprint("DB Connection Refused") == fingerprint("db connection refused")


def test_combined():
    msg = 'Order 12345 failed for user "bob" at 10.1.2.3 trace deadbeef01'
    assert fingerprint(msg) == "order <n> failed for user <str> at <ip> trace <hex>"


def test_stable():
    a = "Timeout after 30000ms (order_id=A1923)"
    b = "Timeout after 45000ms (order_id=A7788)"
    assert fingerprint(a) == fingerprint(b)
