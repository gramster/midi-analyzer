#!/usr/bin/env python3
"""Generate nonstop2k_artists.py data file from artists.txt."""

import re
from pathlib import Path


def to_slug(name: str) -> str:
    """Convert artist name to nonstop2k filename slug format."""
    slug = name.lower()
    # Handle & and special chars
    slug = slug.replace(" & ", "-")
    slug = slug.replace("&", "-")
    slug = slug.replace("'", "")
    slug = slug.replace(".", "")
    slug = slug.replace("$", "s")
    # Replace spaces and non-alphanumeric with hyphens
    slug = re.sub(r"[^a-z0-9-]", "-", slug)
    slug = re.sub(r"-+", "-", slug)
    slug = slug.strip("-")
    return slug


def main():
    # Read artists.txt
    artists_file = Path(__file__).parent.parent / "artists.txt"
    with open(artists_file) as f:
        content = f.read()

    # Parse artist names
    artists = []
    for line in content.split("\n"):
        # Remove bullet point prefix
        line = re.sub(r"^[\s•\t]+", "", line).strip()
        if line:
            artists.append(line)

    print(f"Parsed {len(artists)} artists")

    # Build slug -> display name mapping
    slug_to_name = {}
    for name in artists:
        slug = to_slug(name)
        if slug:
            # Keep first occurrence (some duplicates may exist)
            if slug not in slug_to_name:
                slug_to_name[slug] = name

    print(f"Created {len(slug_to_name)} unique slugs")

    # Generate Python data file
    output_file = Path(__file__).parent.parent / "src" / "midi_analyzer" / "ingest" / "nonstop2k_artists.py"
    
    with open(output_file, "w") as f:
        f.write('"""Known nonstop2k.com artist names for metadata extraction.\n\n')
        f.write("Auto-generated from artists.txt - do not edit manually.\n")
        f.write('"""\n\n')
        f.write("# Mapping from filename slug to display name\n")
        f.write("NONSTOP2K_ARTISTS: dict[str, str] = {\n")
        
        for slug in sorted(slug_to_name.keys()):
            name = slug_to_name[slug]
            # Escape quotes in names
            escaped_name = name.replace('"', '\\"')
            f.write(f'    "{slug}": "{escaped_name}",\n')
        
        f.write("}\n")

    print(f"Wrote {output_file}")

    # Test some lookups
    test_slugs = ["above-beyond", "070-shake", "4-strings", "deadmau5", "adriatique"]
    print("\nTest lookups:")
    for slug in test_slugs:
        name = slug_to_name.get(slug, "NOT FOUND")
        print(f"  {slug} -> {name}")


if __name__ == "__main__":
    main()
