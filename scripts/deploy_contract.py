"""Deploy EvidenceRegistry.sol to Sepolia — Phase 3.

Two deploy paths are supported:

1. **RECOMMENDED for the hackathon deadline** — compile and deploy
   directly here using `py-solc-x` (which installs solc 0.8.20+ on
   first use). After deployment, copy the printed address into
   `CONTRACT_ADDRESS` in your `.env` so subsequent `anchor` and
   `verify-onchain` commands can find it.

2. **Use Remix** (the spec's "Fastest Contract Deployment Option"):
   https://remix.ethereum.org — paste `contracts/EvidenceRegistry.sol`,
   compile, deploy via MetaMask on Sepolia, then paste the address into
   `.env`. The Python pipeline never has to compile anything.

Both paths produce an identical on-chain contract; this script just
automates path (1). It will not run with empty env vars — it will
explain exactly what's missing and exit 1.

Required env vars:
    SEPOLIA_RPC_URL        e.g. https://sepolia.infura.io/v3/<KEY>
    BLOCKCHAIN_PRIVATE_KEY a Sepolia test wallet key (0x...)

Outputs:
    Prints the deployed contract address on success. Does NOT
    auto-write it to `.env` (you should confirm it first).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Allow running this script as `python scripts/deploy_contract.py`
# from the repository root.
_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT))

from facechain.blockchain.client import EVIDENCE_REGISTRY_ABI, EthereumClient  # noqa: E402
from facechain.blockchain.errors import (  # noqa: E402
    BlockchainConfigError,
    BlockchainError,
    BlockchainTransactionError,
)
from facechain.config import settings  # noqa: E402

CONTRACT_SOURCE = _REPO_ROOT / "contracts" / "EvidenceRegistry.sol"
REQUIRED_SOLC_VERSION = "0.8.20"


def _read_source() -> str:
    if not CONTRACT_SOURCE.exists():
        raise FileNotFoundError(
            f"Contract source not found at {CONTRACT_SOURCE}. "
            f"Run this script from the repository root."
        )
    return CONTRACT_SOURCE.read_text(encoding="utf-8")


def _install_solc_if_needed() -> None:
    """Install solc 0.8.20 via py-solc-x if not already present."""
    try:
        import solcx  # noqa: F401
    except ImportError as exc:
        raise RuntimeError(
            "py-solc-x is not installed. Run `pip install py-solc-x`, "
            "or use the Remix deploy path described in the README."
        ) from exc

    import solcx

    if not solcx.get_installed_solc_versions() or not any(
        str(v).startswith("0.8.20") for v in solcx.get_installed_solc_versions()
    ):
        print(f"Installing solc {REQUIRED_SOLC_VERSION} (one-time, ~10s)...")
        solcx.install_solc(REQUIRED_SOLC_VERSION)


def _compile() -> tuple[bytes, str]:
    """Compile EvidenceRegistry.sol and return (bytecode, abi-json)."""
    import solcx

    _install_solc_if_needed()
    source = _read_source()
    compiled = solcx.compile_source(
        source,
        output_values=["abi", "bin"],
        solc_version=REQUIRED_SOLC_VERSION,
    )
    # solcx returns a dict like {'<stdin>:EvidenceRegistry': {...}}
    for key, value in compiled.items():
        if key.endswith(":EvidenceRegistry"):
            return bytes.fromhex(value["bin"]), value["abi"]
    raise RuntimeError("Could not find compiled EvidenceRegistry in solc output.")


def deploy() -> str:
    """Compile + deploy the registry; return the deployed address."""
    try:
        client = EthereumClient()
        client.require_fully_configured()
    except BlockchainConfigError as exc:
        print(f"\n✗ {exc}\n", file=sys.stderr)
        sys.exit(1)

    print(f"RPC:           {settings.sepolia_rpc_url}")
    print(f"Chain ID:      {client.chain_id_int}")
    print(f"Submitter:     {client.submitter_address}")
    if not client.is_connected():
        print(
            "\n✗ Cannot reach the Sepolia RPC. Check SEPOLIA_RPC_URL "
            "and your network connection.\n",
            file=sys.stderr,
        )
        sys.exit(1)

    bytecode, _abi = _compile()
    web3 = client.web3
    account = client.account

    EvidenceRegistryContract = web3.eth.contract(abi=EVIDENCE_REGISTRY_ABI, bytecode=bytecode)
    tx = EvidenceRegistryContract.constructor().build_transaction(
        {
            "from": account.address,
            "nonce": web3.eth.get_transaction_count(account.address),
            "chainId": client.chain_id_int,
            "gas": 1_500_000,
            "gasPrice": web3.eth.gas_price,
        }
    )
    signed = account.sign_transaction(tx)
    tx_hash = web3.eth.send_raw_transaction(signed.raw_transaction)
    print(f"Deploy TX:     0x{tx_hash.hex()}")
    print("Waiting for receipt...")

    try:
        receipt = web3.eth.wait_for_transaction_receipt(tx_hash, timeout=180)
    except Exception as exc:
        raise BlockchainTransactionError(
            f"Deploy transaction did not confirm: {exc}"
        ) from exc

    if receipt.get("status") != 1:
        raise BlockchainTransactionError(
            f"Deploy transaction reverted. status={receipt.get('status')!r}"
        )

    address = web3.to_checksum_address(receipt.get("contractAddress"))
    print(f"\nDeployed EvidenceRegistry to: {address}")
    print(f"Block:                        {receipt.get('blockNumber')}")
    print()
    print("Next steps:")
    print(f"  1. Add to your .env:    CONTRACT_ADDRESS={address}")
    print("  2. Anchor evidence:     python main.py anchor artifacts/evidence/evidence.json")
    print("  3. Verify on chain:    python main.py verify-onchain artifacts/evidence/evidence.json")
    return address


def main() -> None:
    print(
        "FaceChain — EvidenceRegistry deployer\n"
        "--------------------------------------\n"
    )
    try:
        deploy()
    except BlockchainError as exc:
        print(f"\n✗ {exc}\n", file=sys.stderr)
        sys.exit(1)
    except RuntimeError as exc:
        print(f"\n✗ {exc}\n", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
