"""CAS 密码加密所用 AES-CBC 实现的向量测试（离线）。

纯 Python 实现必须自证正确：这里用 NIST SP 800-38A 官方向量校验 AES 分组加密，
再用 S-box 定义值 + PKCS7 边界校验周边逻辑。若环境里有 pycryptodome，
额外做一次随机对拍（没有则跳过，不影响结论）。

直接运行: python test/test_aes_cbc.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from utils import aes_cbc  # noqa: E402

# NIST SP 800-38A F.2.x：CBC 第一块密文
NIST = [
    ("AES-128 F.2.1",
     "2b7e151628aed2a6abf7158809cf4f3c",
     "000102030405060708090a0b0c0d0e0f",
     "6bc1bee22e409f96e93d7e117393172a",
     "7649abac8119b246cee98e9b12e9197d"),
    ("AES-192 F.2.3",
     "8e73b0f7da0e6452c810f32b809079e562f8ead2522c6b7b",
     "000102030405060708090a0b0c0d0e0f",
     "6bc1bee22e409f96e93d7e117393172a",
     "4f021db243bc633d7178183a9fa071e8"),
    ("AES-256 F.2.5",
     "603deb1015ca71be2b73aef0857d77811f352c073b6108d72d9810a30914dff4",
     "000102030405060708090a0b0c0d0e0f",
     "6bc1bee22e409f96e93d7e117393172a",
     "f58c4c04d6e5f1ba779eabfb5f7bfbd6"),
]


def test_nist_cbc_vectors():
    for name, k, iv, pt, ct in NIST:
        out = aes_cbc.aes_cbc_encrypt(bytes.fromhex(k), bytes.fromhex(iv), bytes.fromhex(pt))
        assert out[:16].hex() == ct, f"{name}: {out[:16].hex()} != {ct}"
    print("ok NIST SP 800-38A CBC vectors (128/192/256)")


def test_sbox_definition_values():
    assert aes_cbc.SBOX[0x00] == 0x63
    assert aes_cbc.SBOX[0x01] == 0x7C
    assert aes_cbc.SBOX[0x53] == 0xED
    for i, v in enumerate(aes_cbc.SBOX):
        assert aes_cbc.INV_SBOX[v] == i, f"S-box 不是双射: {i}->{v}"
    print("ok S-box definition + bijection")


def test_pkcs7_padding_boundaries():
    key, iv = b"0123456789abcdef", b"abcdef0123456789"
    for n in (0, 1, 15, 16, 17, 31, 32):
        out = aes_cbc.aes_cbc_encrypt(key, iv, b"A" * n)
        assert len(out) % 16 == 0
        expect = ((n // 16) + 1) * 16  # 整块时也要补一整块
        assert len(out) == expect, f"n={n} 长度 {len(out)} != {expect}"
    print("ok PKCS7 padding boundaries (incl. full block)")


def test_cas_password_scheme():
    salt = "jI6OiZwMHtJNp7BW"
    pwd = "P@ssw0rd-中文"
    blob = aes_cbc.encrypt_cas_password(pwd, salt)
    raw = aes_cbc.base64.b64decode(blob)
    assert len(raw) % 16 == 0
    # 明文长度 = 64 个随机字符 + 密码（UTF-8 字节），再补齐到块边界
    pt_len = 64 + len(pwd.encode("utf-8"))
    assert len(raw) == ((pt_len // 16) + 1) * 16
    # 两次加密不应相同（随机前缀/IV）
    assert blob != aes_cbc.encrypt_cas_password(pwd, salt)
    print("ok CAS password scheme (prefix 64 chars, random, block-aligned)")


def test_empty_salt_refuses():
    try:
        aes_cbc.encrypt_cas_password("secret", "")
    except ValueError:
        print("ok empty salt refused (never send plaintext)")
        return
    raise AssertionError("salt 为空必须拒绝，否则会把明文密码当密文发出去")


def test_pycryptodome_cross_check():
    try:
        from Crypto.Cipher import AES
        from Crypto.Util.Padding import pad
        import secrets
    except ImportError:
        print("skip pycryptodome cross-check (not installed)")
        return
    for _ in range(20):
        key = secrets.token_bytes(secrets.choice([16, 24, 32]))
        iv = secrets.token_bytes(16)
        pt = secrets.token_bytes(secrets.randbelow(200))
        assert aes_cbc.aes_cbc_encrypt(key, iv, pt) == AES.new(key, AES.MODE_CBC, iv).encrypt(pad(pt, 16))
    print("ok pycryptodome cross-check (20 random cases)")


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for t in tests:
        t()
    print(f"\nALL {len(tests)} TESTS PASSED")
