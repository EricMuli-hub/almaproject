"""web3 wrapper around the AlmaRegistry contract. Works on an in-process test chain by default
and on any EVM node (Hardhat, Ganache, a testnet, a private chain) when CHAIN_RPC is set."""
import json, threading, time
from dataclasses import dataclass
from eth_account import Account
from web3 import Web3, EthereumTesterProvider, HTTPProvider
from web3.exceptions import ContractLogicError
from .core import ROOT

ROLES = {0: "None", 1: "PlatformAdmin", 2: "UniversityAdmin", 3: "Student", 4: "Employer", 5: "Regulator"}


@dataclass
class TxResult:
    ok: bool
    error: str = ""
    gas: int = 0
    tx_hash: str = ""
    block: int = 0
    latency_ms: float = 0.0


class Chain:
    def __init__(self, rpc="", address="", funder_key="", platform_key="", artifact="AlmaRegistry.json"):
        art = json.loads((ROOT / "build" / artifact).read_text())
        self.abi = art["abi"]; self.lock = threading.RLock()
        self.tester = not rpc
        self.w3 = Web3(HTTPProvider(rpc)) if rpc else Web3(EthereumTesterProvider())
        if self.tester:
            self.funder = Account.from_key(self.w3.eth.account.create().key) if False else None
            self._fund_src = self.w3.eth.accounts[0]
        else:
            self.funder = Account.from_key(funder_key)
        self.platform = Account.from_key(platform_key) if platform_key else Account.create()
        self.fund(self.platform.address, 50)
        self.errors = {}
        for i in self.abi:
            if i["type"] == "error":
                sig = f'{i["name"]}({",".join(x["type"] for x in i["inputs"])})'
                self.errors["0x" + Web3.keccak(text=sig)[:4].hex().removeprefix("0x")] = i["name"]
        if address:
            self.address = Web3.to_checksum_address(address)
        else:
            if rpc and __import__('os').getenv('ALLOW_DEPLOY', '1') != '1': raise RuntimeError('set CONTRACT_ADDRESS (run scripts/deploy.py once)')
            C = self.w3.eth.contract(abi=self.abi, bytecode=art["bytecode"])
            r = self._send(C.constructor(), self.platform.key, wait=True)
            self.address = r[1].contractAddress; self.deploy_gas = r[1].gasUsed
        self.c = self.w3.eth.contract(address=self.address, abi=self.abi)

    # ---- plumbing ----
    def fund(self, addr, eth=5):
        with self.lock:
            wei = Web3.to_wei(eth, "ether")
            if self.tester:
                self.w3.eth.send_transaction({"from": self._fund_src, "to": addr, "value": wei})
            elif self.w3.eth.get_balance(addr) < wei // 10:
                tx = {"to": addr, "value": wei, "nonce": self.w3.eth.get_transaction_count(self.funder.address),
                      "gas": 21000, "gasPrice": self.w3.eth.gas_price, "chainId": self.w3.eth.chain_id}
                self.w3.eth.wait_for_transaction_receipt(self.w3.eth.send_raw_transaction(self.funder.sign_transaction(tx).raw_transaction))

    def _decode(self, e) -> str:
        """Turn a revert into the contract's own error name. Test chain and real nodes report reverts differently."""
        import ast, re
        data = getattr(e, "data", None); raw = None
        if isinstance(data, dict): data = data.get("data")
        if isinstance(data, str) and data.startswith("0x") and len(data) >= 10: raw = bytes.fromhex(data[2:])
        if raw is None:
            m = re.search(r"(b'.*'|b\".*\")\s*$", str(e))
            if m:
                try: raw = ast.literal_eval(m.group(1))
                except Exception: raw = None
        if raw is None:
            m = re.search(r"0x(e[0-9a-f]{7}|[0-9a-f]{8})[0-9a-f]*", str(e))
            if m:
                h = m.group(0)[2:]
                if len(h) % 2: h = h[:-1]
                try: raw = bytes.fromhex(h)
                except Exception: raw = None
        if raw and len(raw) >= 4:
            name = self.errors.get("0x" + raw[:4].hex())
            if name == "NotAllowed" and len(raw) >= 68:
                return f"NotAllowed(needed={ROLES.get(int.from_bytes(raw[4:36],'big'))},actual={ROLES.get(int.from_bytes(raw[36:68],'big'))})"
            if name: return name
        return str(e)[:160]

    def _send(self, fn, key, wait=True):
        acct = Account.from_key(key); t0 = time.perf_counter()
        with self.lock:
            try:
                gas = fn.estimate_gas({"from": acct.address})
            except Exception as e:
                return TxResult(False, self._decode(e), latency_ms=(time.perf_counter() - t0) * 1000), None
            tx = fn.build_transaction({"from": acct.address, "nonce": self.w3.eth.get_transaction_count(acct.address),
                                       "gas": int(gas * 1.25) + 5000})
            raw = acct.sign_transaction(tx).raw_transaction
            h = self.w3.eth.send_raw_transaction(raw)
            rc = self.w3.eth.wait_for_transaction_receipt(h)
        ok = rc.status == 1
        return TxResult(ok, "" if ok else "reverted", rc.gasUsed, h.hex(), rc.blockNumber, (time.perf_counter() - t0) * 1000), rc

    def tx(self, name, key, *args) -> TxResult:
        res, _ = self._send(getattr(self.c.functions, name)(*args), key)
        return res

    # ---- reads ----
    def role_of(self, addr) -> str: return ROLES[self.c.functions.roleOf(addr).call()]
    def batch_status(self, root_hex):
        e, rev, inst, act = self.c.functions.batchStatus(bytes.fromhex(root_hex.removeprefix("0x"))).call()
        return dict(exists=e, revoked=rev, inst_id=inst, issuer_active=act)
    def credential_status(self, h_hex):
        e, rev, inst, holder, act = self.c.functions.credentialStatus(bytes.fromhex(h_hex.removeprefix("0x"))).call()
        return dict(exists=e, revoked=rev, inst_id=inst, holder=holder, issuer_active=act)
    def leaf_revoked(self, leaf_hex): return self.c.functions.revokedLeaf(bytes.fromhex(leaf_hex.removeprefix("0x"))).call()
    def has_access(self, h_hex, verifier): return self.c.functions.hasAccess(bytes.fromhex(h_hex.removeprefix("0x")), verifier).call()
    def institution(self, i):
        n, adm, act, fl, ts = self.c.functions.institutions(i).call(); return dict(name=n, admin=adm, active=act, flagged=fl)
    def now(self) -> int: return self.w3.eth.get_block("latest").timestamp

    def events(self, name, from_block=0):
        return getattr(self.c.events, name)().get_logs(from_block=from_block)

    def all_logs_text(self) -> str:
        """Every byte the contract has ever logged, as text. Used to prove no personal data is on chain."""
        logs = self.w3.eth.get_logs({"address": self.address, "fromBlock": 0})
        return " ".join(l["data"].hex() if hasattr(l["data"], "hex") else str(l["data"]) for l in logs)

    # ---- ledger watching and raw sending ----
    def latest(self) -> int: return self.w3.eth.block_number

    def contract_txs(self, number):
        """Transactions in a block that were sent to the registry, decoded."""
        blk = self.w3.eth.get_block(number, full_transactions=True); out = []
        for t in blk["transactions"]:
            if t.get("to") and t["to"].lower() == self.address.lower():
                inp = t.get("input", t.get("data"))
                try: fn, args = self.c.decode_function_input(inp); name = fn.fn_name
                except Exception: name, args = "unknown", {}
                rc = self.w3.eth.get_transaction_receipt(t["hash"])
                out.append(dict(hash=t["hash"].hex(), sender=t["from"], name=name, args=args, ok=rc.status == 1, gas=rc.gasUsed,
                                ts=blk["timestamp"], block=number, input=bytes(inp)))
        return out

    def replay_error(self, number, hash_hex):
        t = self.w3.eth.get_transaction(hash_hex)
        try:
            self.w3.eth.call({"from": t["from"], "to": t["to"], "data": t.get("input", t.get("data")), "value": t["value"]}, block_identifier=max(0, number - 1))
            return "reverted"
        except Exception as e: return self._decode(e)

    def send_unchecked(self, name, key, *args, gas=300000):
        """Sends without the pre-flight gas estimate, so a forbidden call is mined and reverts on chain.
        Used to model an attacker who talks to the node directly instead of our API."""
        acct = Account.from_key(key); fn = getattr(self.c.functions, name)(*args)
        with self.lock:
            tx = fn.build_transaction({"from": acct.address, "nonce": self.w3.eth.get_transaction_count(acct.address), "gas": gas})
            h = self.w3.eth.send_raw_transaction(acct.sign_transaction(tx).raw_transaction)
            rc = self.w3.eth.wait_for_transaction_receipt(h)
        return TxResult(rc.status == 1, "" if rc.status == 1 else "reverted", rc.gasUsed, h.hex(), rc.blockNumber)
