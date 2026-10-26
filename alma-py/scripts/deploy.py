"""Deploy the contract once to a real network, then set CONTRACT_ADDRESS and PLATFORM_KEY for every API copy.
  CHAIN_RPC=... FUNDER_KEY=... python scripts/deploy.py"""
import os, pathlib, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from eth_account import Account
from app.chain import Chain
key = Account.create(); ch = Chain(os.environ["CHAIN_RPC"], "", os.environ["FUNDER_KEY"], key.key.hex())
print("CONTRACT_ADDRESS=" + ch.address); print("PLATFORM_KEY=" + key.key.hex()); print("Keep PLATFORM_KEY secret. It is the platform owner's chain key.")
