from Crypto.Cipher import AES
from Crypto.Util.Padding import pad, unpad
from Crypto.PublicKey import RSA
from Crypto.Cipher import PKCS1_OAEP
import os
import hashlib

BLOCK_SIZE = 16

RSA_KEY_SIZE = 2048
RSA_PRIVATE_FILE = "rsa_private.pem"
RSA_PUBLIC_FILE = "rsa_public.pem"

# well-known 2048-bit DH prime (RFC 3526 group 14)
DH_PRIME = int(
    "FFFFFFFFFFFFFFFFC90FDAA22168C234C4C6628B80DC1CD1"
    "29024E088A67CC74020BBEA63B139B22514A08798E3404DD"
    "EF9519B3CD3A431B302B0A6DF25F14374FE1356D6D51C245"
    "E485B576625E7EC6F44C42E9A637ED6B0BFF5CB6F406B7ED"
    "EE386BFB5A899FA5AE9F24117C4B1FE649286651ECE45B3D"
    "C2007CB8A163BF0598DA48361C55D39A69163FA8FD24CF5F"
    "83655D23DCA3AD961C62F356208552BB9ED529077096966D"
    "670C354E4ABC9804F1746C08CA18217C32905E462E36CE3B"
    "E39E772C180E86039B2783A2EC07A28FB5C55DF06F4C52C9"
    "DE2BCBF6955817183995497CEA956AE515D2261898FA0510"
    "15728E5A8AACAA68FFFFFFFFFFFFFFFF", 16
)
DH_GENERATOR = 2


# ======================== AES ========================

def generate_aes_key():
    return os.urandom(16)


def aes_encrypt(data, key):
    iv = os.urandom(BLOCK_SIZE)
    cipher = AES.new(key, AES.MODE_CBC, iv)
    encrypted = cipher.encrypt(pad(data, BLOCK_SIZE))
    return iv + encrypted


def aes_decrypt(data, key):
    iv = data[:BLOCK_SIZE]
    cipher = AES.new(key, AES.MODE_CBC, iv)
    return unpad(cipher.decrypt(data[BLOCK_SIZE:]), BLOCK_SIZE)


# ======================== RSA ========================

def generate_rsa_keys():
    key = RSA.generate(RSA_KEY_SIZE)
    private_pem = key.export_key()
    public_pem = key.publickey().export_key()
    return private_pem, public_pem


def save_rsa_keys(private_pem, public_pem):
    with open(RSA_PRIVATE_FILE, "wb") as f:
        f.write(private_pem)
    with open(RSA_PUBLIC_FILE, "wb") as f:
        f.write(public_pem)


def load_rsa_keys():
    if os.path.exists(RSA_PRIVATE_FILE) and os.path.exists(RSA_PUBLIC_FILE):
        with open(RSA_PRIVATE_FILE, "rb") as f:
            private_pem = f.read()
        with open(RSA_PUBLIC_FILE, "rb") as f:
            public_pem = f.read()
        return private_pem, public_pem
    return None


def rsa_encrypt(data, public_pem):
    key = RSA.import_key(public_pem)
    cipher = PKCS1_OAEP.new(key)
    return cipher.encrypt(data)


def rsa_decrypt(data, private_pem):
    key = RSA.import_key(private_pem)
    cipher = PKCS1_OAEP.new(key)
    return cipher.decrypt(data)


# ======================== Diffie-Hellman ========================

def dh_generate_private():
    return int.from_bytes(os.urandom(256), "big") % (DH_PRIME - 2) + 1


def dh_compute_public(private):
    return pow(DH_GENERATOR, private, DH_PRIME)


def dh_compute_shared(other_public, my_private):
    return pow(other_public, my_private, DH_PRIME)


def dh_derive_aes_key(shared_secret):
    shared_bytes = shared_secret.to_bytes((shared_secret.bit_length() + 7) // 8, "big")
    return hashlib.sha256(shared_bytes).digest()[:16]