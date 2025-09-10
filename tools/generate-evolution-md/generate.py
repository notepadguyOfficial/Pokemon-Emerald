import re
import requests
from pathlib import Path

POKEAPI = "https://pokeapi.co/api/v2/pokemon/"
species_cache = {}


def fetch_species(species):
    """Fetch Dex ID and name from PokéAPI for a SPECIES_XXX identifier"""
    if not species:
        return ("?", None)
    if species in species_cache:
        return species_cache[species]

    # Convert SPECIES_FOO_BAR -> foo-bar
    name = species.replace("SPECIES_", "").lower().replace("_", "-")

    url = f"{POKEAPI}{name}"
    try:
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        data = r.json()
        dex_id = data["id"]
        poke_name = data["name"]
        result = (poke_name.capitalize() if "-" not in poke_name else poke_name, dex_id)
    except Exception as e:
        print(f"⚠️ Could not fetch {name} ({e})")
        result = (name, None)

    species_cache[species] = result
    return result


def get_serebii_icon(dex_id):
    if not dex_id:
        return ""
    return f'<img src="https://www.serebii.net/pokedex-sv/icon/new/{dex_id:03}.png">'


def extract_species_lines(filepath: Path):
    inside = None
    results = []
    with open(filepath, "r", encoding="utf-8") as f:
        for line in f:
            stripped = line.strip()
            if stripped.startswith("const struct Evolution gEvolutionTable"):
                inside = "gEvolutionTable"
            elif stripped.startswith("const struct LevelEvolution gLevelEvolution"):
                inside = "gLevelEvolution"
            elif stripped.startswith("const struct LevelItemEvolution gLevelItemEvolutionItems"):
                inside = "gLevelItemEvolutionItems"

            if inside and stripped.startswith("};"):
                inside = None
                continue

            if inside and stripped.startswith("[SPECIES_"):
                results.append((inside, stripped))
    return results


def parse_species_from_line(context, line):
    species_match = re.match(r"\[([A-Z0-9_]+)\]", line)
    if not species_match:
        return None, None, None, None
    species = species_match.group(1)

    if context == "gEvolutionTable":
        m = re.search(r"=\s*\{\{([^,]+),\s*([^,]+),\s*([^}]+)", line)
        if m:
            method, value, target = m.groups()
            return species, method.strip(), value.strip(), target.strip()

    elif context == "gLevelEvolution":
        m = re.search(r"=\s*\{\{([^}]+)\}\}", line)
        if m:
            level = m.group(1).strip()
            return species, "EVO_LEVEL", level, None

    elif context == "gLevelItemEvolutionItems":
        items = re.findall(r"\{([^,]+),\s*([^}]+)\}", line)
        for item, level in items:
            return species, "EVO_ITEM", f"{item.strip()}@{level.strip()}", None

    return species, None, None, None


def extract_all_evolutions(filepath: Path):
    lines = extract_species_lines(filepath)
    evolutions = {}
    for context, line in lines:
        species, method, value, target = parse_species_from_line(context, line)
        if not species:
            continue
        if species not in evolutions:
            evolutions[species] = []
        evolutions[species].append((method, value, target))
    return evolutions


def resolve_target(species, evolutions):
    for m, v, t in evolutions.get(species, []):
        if t:
            return t
    return None

def clean_value(value: str) -> str:
    """Remove braces and format ITEM@LEVEL nicely"""
    if not value:
        return ""
    value = value.strip("{} ")
    if "@" in value:
        item, level = value.split("@", 1)
        return f"{item} (Lv.{level})"
    return value

def generate_html_table(evolutions):
    rows = []
    seen = set()  # prevent duplicates

    for species, evo_list in evolutions.items():
        sname, sid = fetch_species(species)

        for method, value, target in evo_list:
            if not method:
                continue

            if not target:
                target = resolve_target(species, evolutions)

            target_html = "?"
            if target:
                tname, tid = fetch_species(target)
                target_html = f'{get_serebii_icon(tid)}{tname}'

            # clean value
            clean_val = clean_value(value)

            key = (species, method, clean_val, target_html)
            if key in seen:
                continue
            seen.add(key)

            rows.append(
                f'\t\t<tr>\n'
                f'\t\t\t<td>{get_serebii_icon(sid)}{sname}</td>\n'
                f'\t\t\t<td>{method}</td>\n'
                f'\t\t\t<td>{clean_val}</td>\n'
                f'\t\t\t<td>{target_html}</td>\n'
                f'\t\t</tr>'
            )

    return (
        "# Evolution Table\n\n"
        "<table>\n"
        "\t<thead>\n"
        "\t\t<tr>\n"
        "\t\t\t<th>Species</th>\n"
        "\t\t\t<th>Method</th>\n"
        "\t\t\t<th>Level/Stone</th>\n"
        "\t\t\t<th>Target Species</th>\n"
        "\t\t</tr>\n"
        "\t</thead>\n"
        "\t<tbody>\n"
        + "\n".join(rows)
        + "\n\t</tbody>\n</table>\n"
    )


def diff_evolutions(original, modified):
    diff = {}
    for species, mods in modified.items():
        orig = original.get(species, [])
        if mods != orig:  # only keep if changed
            diff[species] = mods
    return diff


if __name__ == "__main__":
    root_dir = Path(__file__).parent.resolve()
    original_file = root_dir / "evolution.h"
    modified_file = (root_dir / "../../src/data/pokemon/evolution.h").resolve()

    evolutions_original = extract_all_evolutions(original_file)
    evolutions_modified = extract_all_evolutions(modified_file)

    differences = diff_evolutions(evolutions_original, evolutions_modified)

    html = generate_html_table(differences)

    output_path = (root_dir / "../../.github/Evolution.md").resolve()
    if not output_path.parent.exists():
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.touch()

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)

    print("✅ README.md generated with evolution changes (Serebii icons)")