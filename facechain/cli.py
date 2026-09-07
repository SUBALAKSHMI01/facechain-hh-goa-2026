"""FaceChain CLI — Phase 1: `python main.py analyze IMAGE`."""

from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from facechain.pipeline import PipelineError, run_phase1_pipeline

app = typer.Typer(help="FaceChain — Vision -> Search -> Proof -> Chain (Phases 1+2+3+4)")
console = Console()


@app.command()
def version() -> None:
    """Print the FaceChain version."""
    from facechain import __version__

    console.print(f"FaceChain {__version__}")


def _banner() -> None:
    console.print(
        Panel.fit(
            "[bold]FACECHAIN[/bold]\nVision -> Search -> Proof -> Chain",
            border_style="cyan",
        )
    )


@app.command()
def analyze(
    image: Path = typer.Argument(..., exists=True, help="Path to the input image."),
) -> None:
    """Run the Phase 1 pipeline on IMAGE and produce artifacts/evidence/evidence.json."""
    _banner()

    try:
        result = run_phase1_pipeline(image)
    except PipelineError as exc:
        console.print(f"[bold red]✗ Pipeline failed:[/bold red] {exc}")
        raise typer.Exit(code=1)

    li = result.loaded_image
    face = result.faces[0]

    console.print("\n[bold]\\[1/5] Image analysis[/bold]")
    console.print("      [green]✓[/green] Image loaded "
                   f"({li.width}x{li.height})")
    console.print(f"      [green]✓[/green] SHA-256 generated: {li.sha256[:16]}...")
    console.print(f"      [green]✓[/green] pHash generated: {li.phash}")

    console.print("\n[bold]\\[2/5] Face analysis[/bold]")
    console.print(f"      [green]✓[/green] {len(result.faces)} face detected")
    console.print(f"      [green]✓[/green] SCRFD confidence: {face.detection_confidence * 100:.1f}%")
    console.print("      [green]✓[/green] 512-D ArcFace embedding generated")

    console.print("\n[bold]\\[3/5] Reverse search[/bold]")
    if result.search_error:
        console.print(f"      [yellow]![/yellow] Google Web Detection failed: {result.search_error}")
        console.print("      [yellow]![/yellow] No social candidates found (search did not run)")
    else:
        console.print("      [green]✓[/green] Google Web Detection completed")
        if result.social_candidates:
            table = Table(show_header=True, header_style="bold")
            table.add_column("Platform")
            table.add_column("URL")
            table.add_column("Match type")
            for c in result.social_candidates:
                table.add_row(c.platform, c.url, c.match_type)
            console.print(f"      [green]✓[/green] {len(result.social_candidates)} social candidate(s) found")
            console.print(table)
        else:
            console.print("      [yellow]![/yellow] No social-media candidates found — reporting honestly, not fabricating a match")

    console.print("\n[bold]\\[4/5] Evidence[/bold]")
    console.print(f"      [green]✓[/green] evidence.json created at {result.built_evidence.output_path}")

    console.print("\n[bold]\\[5/5] Cryptographic proof[/bold]")
    console.print(f"      [green]✓[/green] Evidence SHA-256: {result.built_evidence.evidence_hash}")

    console.print(
        "\n[dim]Run `python main.py anchor <evidence.json>` to anchor this on Sepolia (Phase 3).[/dim]"
    )


@app.command()
def verify(
    reference: Path = typer.Argument(
        ..., exists=True, help="Path to the reference image (e.g. a photo of yourself)."
    ),
    candidate: str = typer.Argument(
        ..., help="URL or local path of the ONE candidate you have already chosen to compare."
    ),
    platform: str = typer.Option(
        None, help="Optional: platform the candidate came from (e.g. 'instagram.com'), for the record."
    ),
    match_type: str = typer.Option(
        None, "--match-type", help="Optional: how the candidate was found (e.g. 'full_matching_image')."
    ),
) -> None:
    """Compare ONE explicitly-approved candidate against a reference image.

    This does not search for or select the candidate for you — pick the
    URL yourself (e.g. from `analyze`'s social candidate list) and pass
    it in. Produces a consistent/not-consistent result, never an
    identity claim.
    """
    from facechain.verification import VerificationError, run_consent_verification

    _banner()

    try:
        result = run_consent_verification(
            reference_path=reference,
            candidate_source=candidate,
            platform=platform,
            match_type=match_type,
        )
    except VerificationError as exc:
        console.print(f"[bold red]✗ Verification failed:[/bold red] {exc}")
        raise typer.Exit(code=1)

    console.print("\n[bold]\\[1/3] Reference & candidate[/bold]")
    console.print(f"      [green]✓[/green] Reference SHA-256: {result.reference_image.sha256[:16]}...")
    console.print(f"      [green]✓[/green] Candidate SHA-256: {result.candidate_image.sha256[:16]}...")
    console.print(f"      [green]✓[/green] Candidate source: {candidate}")

    console.print("\n[bold]\\[2/3] Comparison[/bold]")
    console.print(f"      [green]✓[/green] Face similarity: {result.evidence.face_similarity:.4f}")
    if result.evidence.image_similarity is not None:
        console.print(f"      [green]✓[/green] Image (pHash) similarity: {result.evidence.image_similarity:.4f}")

    status = result.evidence.verification_status
    status_style = "green" if status == "consistent_with_reference" else "yellow"
    console.print(f"      [{status_style}]●[/{status_style}] Status: {status}")
    console.print(f"      [dim]{result.evidence.verification_label}[/dim]")

    console.print("\n[bold]\\[3/3] Evidence[/bold]")
    console.print(f"      [green]✓[/green] verification.json created at {result.output_path}")
    console.print(f"      [green]✓[/green] Evidence SHA-256: {result.evidence_hash}")

    console.print(
        "\n[dim]Run `python main.py verify-onchain <verification.json>` to verify on Sepolia (Phase 3).[/dim]"
    )


# ---------------------------------------------------------------------------
# Phase 3 — blockchain anchoring (`anchor`) and on-chain verification
# (`verify-onchain`). These commands are purely additive: they neither
# read nor modify any of the Phase 1/Phase 2 evidence files' contents.
# ---------------------------------------------------------------------------


@app.command()
def anchor(
    evidence: Path = typer.Argument(
        ...,
        exists=True,
        help="Path to a FaceChain evidence.json (Phase 1 or Phase 2).",
    ),
) -> None:
    """Anchor an evidence file's SHA-256 on Ethereum Sepolia.

    Reads `evidence`, extracts the `evidenceHash` and the first social
    candidate URL, derives a `sourceHash = SHA-256(normalized URL)`,
    and submits a signed transaction to the deployed
    `EvidenceRegistry` contract. Prints the transaction hash and the
    block number on success.
    """
    from facechain.blockchain import (
        BlockchainConfigError,
        BlockchainError,
        BlockchainTransactionError,
        EthereumClient,
        EvidenceRegistryContract,
        InvalidEvidenceFileError,
    )

    _banner()

    try:
        client = EthereumClient()
        client.require_fully_configured()
    except BlockchainConfigError as exc:
        console.print(f"[bold red]✗ {exc}[/bold red]")
        raise typer.Exit(code=1)

    contract = EvidenceRegistryContract(client)

    console.print("\n[bold]\\[1/3] Evidence file[/bold]")
    console.print(f"      [green]✓[/green] {evidence}")

    console.print("\n[bold]\\[2/3] Connection[/bold]")
    info = client.connection_info()
    console.print(f"      [green]✓[/green] RPC: {info.rpc_url}")
    console.print(f"      [green]✓[/green] Chain ID: {info.chain_id}")
    console.print(f"      [green]✓[/green] Submitter: {info.submitter_address}")
    console.print(f"      [green]✓[/green] Contract: {info.contract_address}")

    try:
        result = contract.register_evidence_from_file(evidence)
    except InvalidEvidenceFileError as exc:
        console.print(f"[bold red]✗ Bad evidence file:[/bold red] {exc}")
        raise typer.Exit(code=1)
    except BlockchainTransactionError as exc:
        console.print(f"[bold red]✗ Transaction failed:[/bold red] {exc}")
        raise typer.Exit(code=1)
    except BlockchainError as exc:
        console.print(f"[bold red]✗ Blockchain error:[/bold red] {exc}")
        raise typer.Exit(code=1)

    console.print("\n[bold]\\[3/3] Anchored[/bold]")
    console.print(f"      [green]✓[/green] Evidence hash: {result.evidence_hash}")
    console.print(f"      [green]✓[/green] Source hash:   {result.source_hash}")
    console.print(f"      [green]✓[/green] TX hash:       {result.transaction_hash}")
    console.print(f"      [green]✓[/green] Block:         {result.block_number}")
    console.print(
        f"\n[green]TAMPER-EVIDENT PROOF ANCHORED ON SEPOLIA[/green]"
    )


@app.command()
def verify_onchain(
    evidence: Path = typer.Argument(
        ...,
        exists=True,
        help="Path to a FaceChain evidence.json to verify against Sepolia.",
    ),
) -> None:
    """Re-derive an evidence file's hash and check it against Sepolia.

    Recomputes the canonical SHA-256 of the file, reads the
    matching on-chain `getEvidence(evidenceHash)` record, and prints
    one of three outcomes: VERIFIED / TAMPERED / NOT_ANCHORED.
    """
    from facechain.blockchain import (
        BlockchainConfigError,
        InvalidEvidenceFileError,
        VerificationStatus,
        verify_evidence_file,
    )

    _banner()

    try:
        report = verify_evidence_file(evidence)
    except InvalidEvidenceFileError as exc:
        console.print(f"[bold red]✗ Bad evidence file:[/bold red] {exc}")
        raise typer.Exit(code=1)
    except BlockchainConfigError as exc:
        console.print(f"[bold red]✗ {exc}[/bold red]")
        raise typer.Exit(code=1)

    console.print("\n[bold]\\[1/3] Evidence file[/bold]")
    console.print(f"      [green]✓[/green] {report.evidence_path}")
    console.print(f"      [green]✓[/green] Recomputed SHA-256: {report.recomputed_evidence_hash}")
    if report.claimed_evidence_hash:
        match = report.claimed_evidence_hash.lower() == report.recomputed_evidence_hash.lower()
        marker = "[green]✓[/green]" if match else "[red]✗[/red]"
        console.print(f"      {marker} Claimed 'evidenceHash': {report.claimed_evidence_hash}")

    console.print("\n[bold]\\[2/3] On-chain record[/bold]")
    if report.on_chain_record is None:
        console.print("      [yellow]![/yellow] No Sepolia record found for this evidence hash.")
    else:
        rec = report.on_chain_record
        console.print(f"      [green]✓[/green] evidenceHash: {rec.evidence_hash}")
        console.print(f"      [green]✓[/green] sourceHash:   {rec.source_hash}")
        console.print(f"      [green]✓[/green] timestamp:    {rec.timestamp}")
        console.print(f"      [green]✓[/green] submitter:    {rec.submitter}")

    console.print("\n[bold]\\[3/3] Result[/bold]")
    for note in report.notes:
        console.print(f"      [dim]• {note}[/dim]")

    if report.status == VerificationStatus.VERIFIED:
        console.print(f"\n[bold green]RESULT  VERIFIED[/bold green]")
    elif report.status == VerificationStatus.TAMPERED:
        console.print(f"\n[bold red]RESULT  TAMPERED[/bold red]")
    else:
        console.print(f"\n[bold yellow]RESULT  NOT_ANCHORED[/bold yellow]")
        raise typer.Exit(code=2)


# ---------------------------------------------------------------------------
# Phase 4 — shortlist-demo commands (`tamper-demo`, `benchmark`).
# Additive; none of analyze / verify / anchor / verify-onchain change.
# ---------------------------------------------------------------------------


@app.command()
def tamper_demo(
    evidence: Path = typer.Argument(
        ...,
        exists=True,
        help="Path to a FaceChain evidence.json to demonstrate the tamper flow on.",
    ),
    field: str = typer.Option(
        "confidence",
        help="Field in the evidence JSON to mutate (default: 'confidence' — the spec's example).",
    ),
    value: str = typer.Option(
        "0.999",
        help="New value for the field (parsed as JSON if possible, else used as a string).",
    ),
) -> None:
    """Run the live tamper demo: verify → mutate → re-verify.

    Copies the file, modifies the chosen field on the COPY, and
    re-runs the Phase 3 verifier. The original is never modified.
    With no blockchain env, the local-file check still demonstrates
    VERIFIED → TAMPERED.
    """
    from facechain.tamper_demo import run_tamper_demo

    import json as _json

    _banner()

    # Try to parse the new value as JSON (so `--value 0.999` is a
    # number, not the string "0.999"); fall back to the raw string.
    try:
        parsed_value: object = _json.loads(value)
    except _json.JSONDecodeError:
        parsed_value = value

    try:
        result = run_tamper_demo(evidence, field=field, new_value=parsed_value)
    except FileNotFoundError as exc:
        console.print(f"[bold red]✗ {exc}[/bold red]")
        raise typer.Exit(code=1)

    console.print("\n[bold]\\[1/3] Original evidence[/bold]")
    console.print(f"      [green]✓[/green] {result.source_path}")
    console.print(
        f"      [{'green' if result.before_status == 'VERIFIED' else 'red'}]"
        f"●[/] Verify: {result.before_status}"
    )

    console.print("\n[bold]\\[2/3] Tamper the COPY[/bold]")
    console.print(f"      [yellow]![/yellow] {result.tampered_path}")
    console.print(
        f"      [yellow]![/yellow] Mutated '{result.field}': "
        f"{result.original_value!r} → {result.new_value!r}"
    )

    console.print("\n[bold]\\[3/3] Verify the TAMPERED copy[/bold]")
    console.print(
        f"      [{'green' if result.after_status == 'VERIFIED' else 'red'}]"
        f"●[/] Verify: {result.after_status}"
    )

    if result.transitioned_to_tampered():
        console.print(
            f"\n[bold green]✓ Tamper detected. The transition "
            f"VERIFIED → TAMPERED was observed.[/bold green]"
        )
    elif result.before_status == "TAMPERED":
        console.print(
            f"\n[bold yellow]! The original file was already TAMPERED. "
            f"The demo can't show a clean VERIFIED → TAMPERED transition. "
            f"Run on an un-modified evidence file.[/bold yellow]"
        )
        raise typer.Exit(code=2)
    else:
        console.print(
            f"\n[bold red]✗ The tamper was not detected. Something is wrong. "
            f"Status went {result.before_status} → {result.after_status}.[/bold red]"
        )
        raise typer.Exit(code=1)

    for note in result.notes:
        console.print(f"      [dim]• {note}[/dim]")


@app.command()
def benchmark(
    n: int = typer.Option(3, help="Number of runs to aggregate (default: 3)."),
    size: int = typer.Option(320, help="Synthetic image size in px (square)."),
) -> None:
    """Run the latency benchmark and print a per-stage table.

    Times the spec's seven stages (preprocess, detection, embedding,
    reverse search, candidate validation, evidence generation,
    blockchain submit) across N runs. Network-dependent stages are
    reported as N/A when credentials are missing — never fabricated.
    """
    from facechain.benchmark import run_benchmark

    _banner()

    if n < 1:
        console.print(f"[bold red]✗ n must be >= 1 (got {n})[/bold red]")
        raise typer.Exit(code=1)
    if size < 32:
        console.print(f"[bold red]✗ size must be >= 32 (got {size})[/bold red]")
        raise typer.Exit(code=1)

    console.print(f"\n[bold]Running {n} benchmark pass(es) on a {size}x{size} synthetic image...[/bold]")
    report = run_benchmark(n=n, image_size=(size, size))

    table = Table(show_header=True, header_style="bold", title=f"Latency (n={report.runs})")
    table.add_column("Stage")
    table.add_column("min ms")
    table.add_column("avg ms")
    table.add_column("max ms")
    table.add_column("n")

    for stage_name, stats in report.stages.items():
        n_measured = stats["n"]
        if n_measured == 0:
            table.add_row(stage_name, "[dim]N/A[/dim]", "[dim]N/A[/dim]", "[dim]N/A[/dim]", "0")
        else:
            table.add_row(
                stage_name,
                f"{stats['min']:.2f}",
                f"{stats['avg']:.2f}",
                f"{stats['max']:.2f}",
                str(n_measured),
            )

    console.print("\n[bold]Per-stage timings[/bold]")
    console.print(table)

    for note in report.notes:
        console.print(f"      [dim]• {note}[/dim]")

    console.print(
        "\n[dim]Network-bound stages (reverse_search_ms, blockchain_submit_ms) "
        "are reported as N/A when credentials are not configured. "
        "The local stages are measured every run.[/dim]"
    )


if __name__ == "__main__":
    app()


if __name__ == "__main__":
    app()
