import base64
import json

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from gpu_queue_probe.publisher import _encrypted_payload


def test_encrypted_payload_round_trip(tmp_path):
    source = tmp_path / "latest.json"
    source.write_text('{"cluster":"private"}\n', encoding="utf-8")
    password = "a-long-random-test-password"
    envelope = json.loads(_encrypted_payload(source, password))

    salt = base64.b64decode(envelope["salt"])
    key = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=envelope["iterations"],
    ).derive(password.encode("utf-8"))
    clear = AESGCM(key).decrypt(
        base64.b64decode(envelope["nonce"]),
        base64.b64decode(envelope["ciphertext"]),
        None,
    )
    assert json.loads(clear) == {"cluster": "private"}
