from pathlib import Path


def test_inno_setup_uses_release_bundle_and_fidelichem_artwork() -> None:
    setup_path = Path(__file__).parents[2] / "installer" / "fidelichem.iss"
    setup = setup_path.read_text(encoding="utf-8")

    assert "AppName=FideliChem" in setup
    assert "OutputBaseFilename=FideliChem-{#AppVersion}-Windows-x64-Setup" in setup
    assert (
        "SetupIconFile=..\\src\\fidelichem\\gui\\assets\\fidelichem-mark.ico"
        in setup
    )
    assert 'Source: "..\\release-assets\\pyinstaller-dist\\FideliChem\\*"' in setup
    assert 'Source: "..\\LICENSE"' in setup
    assert 'Source: "..\\THIRD_PARTY_NOTICES.md"' in setup
    assert 'Name: "{autoprograms}\\FideliChem"' in setup
