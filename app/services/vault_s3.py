# app/services/vault_s3.py — tiny S3 client (AWS Signature V4, stdlib only) for Vultr Object Storage: put, list, signed download link.
import datetime as dt
import hashlib
import hmac
import os
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET


class VaultError(RuntimeError):
    pass


def conf() -> dict | None:
    """None when Object Storage is not configured (local runs, tests): the vault then says so instead of failing."""
    c = {k: os.environ.get(f"CG_S3_{k.upper()}", "").strip() for k in ("endpoint", "access_key", "secret_key", "bucket")}
    return {**c, "region": os.environ.get("CG_S3_REGION") or "us-east-1"} if all(c.values()) else None


def _sign(key: bytes, msg: str) -> bytes:
    return hmac.new(key, msg.encode(), hashlib.sha256).digest()


def _signature(c: dict, stamp: str, string_to_sign: str) -> str:
    k = _sign(("AWS4" + c["secret_key"]).encode(), stamp[:8])
    for part in (c["region"], "s3", "aws4_request"):
        k = _sign(k, part)
    return hmac.new(k, string_to_sign.encode(), hashlib.sha256).hexdigest()


def _path(c: dict, key: str = "") -> str:
    return "/" + c["bucket"] + ("/" + urllib.parse.quote(key, safe="/-_.~") if key else "")


def _query(q: dict) -> str:
    return "&".join(f"{urllib.parse.quote(k, safe='-_.~')}={urllib.parse.quote(str(v), safe='-_.~')}" for k, v in sorted(q.items()))


def _request(c: dict, method: str, key: str = "", query: dict | None = None, body: bytes = b"", ctype: str = "", timeout: int = 30) -> bytes:
    host = urllib.parse.urlparse(c["endpoint"]).netloc
    now = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    payload = hashlib.sha256(body).hexdigest()
    headers = {"host": host, "x-amz-content-sha256": payload, "x-amz-date": now} | ({"content-type": ctype} if ctype else {})
    signed = ";".join(sorted(headers))
    canon = "\n".join([method, _path(c, key), _query(query or {}), "".join(f"{k}:{headers[k]}\n" for k in sorted(headers)), signed, payload])
    scope = f"{now[:8]}/{c['region']}/s3/aws4_request"
    sts = "\n".join(["AWS4-HMAC-SHA256", now, scope, hashlib.sha256(canon.encode()).hexdigest()])
    auth = f"AWS4-HMAC-SHA256 Credential={c['access_key']}/{scope}, SignedHeaders={signed}, Signature={_signature(c, now, sts)}"
    url = c["endpoint"].rstrip("/") + _path(c, key) + ("?" + _query(query) if query else "")
    req = urllib.request.Request(url, data=body if method in ("PUT", "POST") else None, method=method,
                                 headers={**{k: v for k, v in headers.items() if k != "host"}, "Authorization": auth})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read()
    except urllib.error.HTTPError as e:
        raise VaultError(f"Object Storage said {e.code} on {method} {key or c['bucket']}: {e.read()[:200]!r}") from e
    except OSError as e:
        raise VaultError(f"Object Storage unreachable: {e}") from e


def ensure_bucket(c: dict) -> None:
    try:
        _request(c, "HEAD")
    except VaultError:
        _request(c, "PUT")


def exists(c: dict, key: str) -> bool:
    try:
        _request(c, "HEAD", key, timeout=5)
        return True
    except VaultError as e:
        if " 404 " in str(e):
            return False
        raise


def put(c: dict, key: str, body: bytes, ctype: str) -> None:
    _request(c, "PUT", key, body=body, ctype=ctype)


def list_keys(c: dict, prefix: str) -> list:
    """[(key, size, last_modified)] newest first."""
    xml = _request(c, "GET", query={"list-type": "2", "prefix": prefix}, timeout=5)
    ns = {"s": "http://s3.amazonaws.com/doc/2006-03-01/"}
    rows = [(o.findtext("s:Key", "", ns), int(o.findtext("s:Size", "0", ns)), o.findtext("s:LastModified", "", ns))
            for o in ET.fromstring(xml).findall("s:Contents", ns)]
    return sorted(rows, key=lambda r: r[2], reverse=True)


def signed_url(c: dict, key: str, seconds: int = 900) -> str:
    """A download link that works for `seconds` without the keys (presigned GET)."""
    host = urllib.parse.urlparse(c["endpoint"]).netloc
    now = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    scope = f"{now[:8]}/{c['region']}/s3/aws4_request"
    q = {"X-Amz-Algorithm": "AWS4-HMAC-SHA256", "X-Amz-Credential": f"{c['access_key']}/{scope}", "X-Amz-Date": now,
         "X-Amz-Expires": str(seconds), "X-Amz-SignedHeaders": "host"}
    canon = "\n".join(["GET", _path(c, key), _query(q), f"host:{host}\n", "host", "UNSIGNED-PAYLOAD"])
    sts = "\n".join(["AWS4-HMAC-SHA256", now, scope, hashlib.sha256(canon.encode()).hexdigest()])
    return c["endpoint"].rstrip("/") + _path(c, key) + "?" + _query(q | {"X-Amz-Signature": _signature(c, now, sts)})
