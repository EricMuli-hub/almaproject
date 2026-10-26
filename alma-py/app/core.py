"""Settings, cryptography, Merkle trees and the content store (IPFS or local)."""
import base64, hashlib, hmac, json, os, pathlib, secrets, time
from dataclasses import dataclass, field
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

ROOT = pathlib.Path(__file__).resolve().parent.parent


@dataclass
class Settings:
    data_dir: str = os.getenv("ALMA_DATA", str(ROOT / "data"))
    database_url: str = os.getenv("DATABASE_URL", "")
    rpc_url: str = os.getenv("CHAIN_RPC", "")              # empty = in-process test chain
    contract_address: str = os.getenv("CONTRACT_ADDRESS", "")
    funder_key: str = os.getenv("FUNDER_KEY", "")           # pays gas on a real network
    ipfs_api: str = os.getenv("IPFS_API", "")               # e.g. http://127.0.0.1:5001
    master_key_b64: str = os.getenv("ALMA_MASTER_KEY", "")
    jwt_secret: str = os.getenv("JWT_SECRET", "")
    max_batch: int = int(os.getenv("MAX_BATCH", "5000"))
    batch_window_s: int = int(os.getenv("BATCH_WINDOW_S", "0"))  # 0 = no background batcher
    data_region: str = os.getenv("DATA_REGION", "local")
    auto_hold: bool = os.getenv("AUTO_HOLD", "1") == "1"
    watcher: bool = os.getenv("WATCHER", "0") == "1"
    read_cache_ttl: float = float(os.getenv("READ_CACHE_TTL", "0"))   # seconds; 0 = always read the chain

    def __post_init__(self):
        pathlib.Path(self.data_dir).mkdir(parents=True, exist_ok=True)
        if not self.database_url:
            self.database_url = f"sqlite:///{self.data_dir}/alma.db"
        self.master_key = self._secret("master.key", self.master_key_b64, 32)
        self.jwt = self._secret("jwt.key", self.jwt_secret, 32)

    def _secret(self, fname, given, n):
        if given: return hashlib.sha256(given.encode()).digest()
        p = pathlib.Path(self.data_dir) / fname
        if not p.exists():
            p.write_bytes(secrets.token_bytes(n)); os.chmod(p, 0o600)
        return p.read_bytes()


# ---------- hashing ----------
def sha(b: bytes) -> bytes: return hashlib.sha256(b).digest()
def canonical(obj) -> bytes: return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
def leaf_hash(record: dict, salt: bytes) -> bytes: return sha(b"alma:leaf:" + canonical(record) + salt)
def hx(b: bytes) -> str: return "0x" + b.hex()
def unhx(s: str) -> bytes: return bytes.fromhex(s[2:] if s.startswith("0x") else s)


# ---------- Merkle tree (domain separated, odd node promoted) ----------
def _node(l: bytes, r: bytes) -> bytes: return sha(b"\x01" + l + r)


def merkle_levels(leaves: list[bytes]) -> list[list[bytes]]:
    if not leaves: raise ValueError("no leaves")
    levels = [list(leaves)]
    while len(levels[-1]) > 1:
        cur, nxt = levels[-1], []
        for i in range(0, len(cur), 2):
            nxt.append(_node(cur[i], cur[i + 1]) if i + 1 < len(cur) else cur[i])
        levels.append(nxt)
    return levels


def merkle_root(leaves): return merkle_levels(leaves)[-1][0]


def merkle_proof(levels, index: int):
    proof = []
    for lvl in levels[:-1]:
        sib = index ^ 1
        if sib < len(lvl): proof.append(("R" if sib > index else "L", lvl[sib].hex()))
        index //= 2
    return proof


def verify_proof(leaf: bytes, proof, root: bytes) -> bool:
    h = leaf
    for side, sib in proof:
        s = bytes.fromhex(sib)
        h = _node(h, s) if side == "R" else _node(s, h)
    return hmac.compare_digest(h, root)


# ---------- encryption (per record keys, wrapped by the master key) ----------
def aes_encrypt(key: bytes, data: bytes) -> bytes:
    n = secrets.token_bytes(12); return n + AESGCM(key).encrypt(n, data, None)
def aes_decrypt(key: bytes, blob: bytes) -> bytes: return AESGCM(key).decrypt(blob[:12], blob[12:], None)


# ---------- passwords ----------
def hash_password(pw: str) -> str:
    salt = secrets.token_bytes(16)
    return salt.hex() + "$" + hashlib.scrypt(pw.encode(), salt=salt, n=2 ** 14, r=8, p=1).hex()


def check_password(pw: str, stored: str) -> bool:
    salt, h = stored.split("$")
    return hmac.compare_digest(hashlib.scrypt(pw.encode(), salt=bytes.fromhex(salt), n=2 ** 14, r=8, p=1).hex(), h)


# ---------- content store ----------
_B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
def b58(b: bytes) -> str:
    n = int.from_bytes(b, "big"); out = ""
    while n: n, r = divmod(n, 58); out = _B58[r] + out
    return "1" * (len(b) - len(b.lstrip(b"\0"))) + out


class LocalStore:
    """Content addressed store. The id is Qm + base58(sha256 multihash), like an IPFS v0 id,
    but it is computed over the raw bytes, so it is not identical to what a real IPFS node returns."""
    kind = "local-content-addressed"

    def __init__(self, path):
        self.dir = pathlib.Path(path); self.dir.mkdir(parents=True, exist_ok=True)
    def put(self, data: bytes) -> str:
        cid = b58(b"\x12\x20" + sha(data))
        p = self.dir / cid
        if not p.exists(): p.write_bytes(data)
        return cid
    def get(self, cid: str) -> bytes:
        data = (self.dir / cid).read_bytes()
        if b58(b"\x12\x20" + sha(data)) != cid: raise ValueError("content does not match its id (tampered)")
        return data
    def has(self, cid): return (self.dir / cid).exists()


class IpfsStore:
    kind = "ipfs"
    def __init__(self, api):
        import httpx; self.api = api.rstrip("/"); self.c = httpx.Client(timeout=30)
    def put(self, data: bytes) -> str:
        r = self.c.post(f"{self.api}/api/v0/add?pin=true", files={"file": ("blob", data)}); r.raise_for_status()
        return r.json()["Hash"]
    def get(self, cid: str) -> bytes:
        r = self.c.post(f"{self.api}/api/v0/cat?arg={cid}"); r.raise_for_status(); return r.content
    def has(self, cid):
        try: self.get(cid); return True
        except Exception: return False


def make_store(s: Settings):
    return IpfsStore(s.ipfs_api) if s.ipfs_api else LocalStore(pathlib.Path(s.data_dir) / "store")


def now() -> int: return int(time.time())
