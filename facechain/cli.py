"""FaceChain CLI — Phase 1: `python main.py analyze IMAGE`."""

from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from facechain.pipeline import PipelineError, run_phase1_pipeline

app = typer.Typer(help="FaceChain — Vision -> Search -> Proof -> Chain (Phase 1)")
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
        "\n[dim]Blockchain anchoring (Sepolia) is not implemented in Phase 1.[/dim]"
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
        "\n[dim]Blockchain anchoring (Sepolia) is not implemented yet.[/dim]"
    )


if __name__ == "__main__":
    app()
