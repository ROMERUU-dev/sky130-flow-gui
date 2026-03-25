"""Top-level EM probe insertion for ngspice netlists."""

from __future__ import annotations

import json
from pathlib import Path
import re

from app.core.spice_tools import DEVICE_NODE_COUNTS

SUPPLY_NETS = {"vpwr", "vpb", "vgnd", "vnb", "vdpwr", "gnd"}
TT_DIGITAL_PREFIXES = ("clk", "ena", "rst_n", "ui_in[", "uio_in[", "uio_oe[")
TT_ANALOG_PREFIXES = ("ua[",)
OUTPUT_NET_PREFIXES = ("uo_out[", "uio_out[", "ua[")
LOAD_PREFIXES = {"r", "c", "l"}
SOURCE_PREFIXES = {"v", "i"}


def instrument_netlist_for_em(input_netlist_path: str, output_netlist_path: str, config: dict) -> dict:
    """Create an instrumented netlist copy and return probe metadata."""
    input_path = Path(input_netlist_path).resolve()
    output_path = Path(output_netlist_path).resolve()
    source_text = input_path.read_text(encoding="utf-8", errors="replace")
    instrumented_text, metadata = instrument_netlist_text_for_em(source_text, config)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(instrumented_text, encoding="utf-8")
    return metadata


def inspect_internal_net_candidates(source_text: str, project_mode: str = "tiny_tapeout") -> list[dict]:
    """Return top-level internal nets and their connected elements."""
    statements = _split_statements(source_text)
    top_level_infos = _collect_top_level_infos(statements)
    connected_by_net: dict[str, dict] = {}
    for info in top_level_infos:
        for net_name in info["nodes"]:
            if _is_supply_net(net_name) or _is_output_net(net_name) or _should_instrument_net(net_name, project_mode):
                continue
            normalized = _normalized_net_name(net_name)
            if not normalized:
                continue
            entry = connected_by_net.setdefault(
                normalized,
                {
                    "display_name": net_name,
                    "infos": [],
                },
            )
            entry["infos"].append(info)

    candidates: list[dict] = []
    for _, entry in sorted(connected_by_net.items(), key=lambda item: item[1]["display_name"].lower()):
        net_name = entry["display_name"]
        infos = entry["infos"]
        if len(infos) < 2:
            continue
        elements = []
        for info in infos:
            elements.append(
                {
                    "instance_name": info["statement_name"],
                    "statement_type": info["prefix"].upper(),
                    "classification": _classify_internal_element(info["prefix"]),
                    "line_text": info["line_text"],
                    "line_preview": info["line_text"][:140],
                    "pin_position": info["net_pin_positions"].get(net_name),
                    "move_default": _classify_internal_element(info["prefix"]) == "driver",
                }
            )
        candidates.append({"net_name": net_name, "connected_elements": elements})
    return candidates


def preview_manual_instrumentation(source_text: str, net_name: str, moved_statements: list[str], wrdata_output: str | Path) -> dict:
    """Preview a manual internal-net instrumentation change without writing files."""
    probe_def = _manual_probe_def(net_name, moved_statements)
    instrumented_text = _instrument_text_with_probe_defs(source_text, [probe_def], Path(wrdata_output).resolve())
    preview_lines = [f"- {statement}" for statement in moved_statements]
    return {
        "instrumented_text": instrumented_text,
        "preview_text": "\n".join(
            [
                f"Manual instrumentation preview for {net_name}",
                "Moved statements:",
                *preview_lines,
                "",
                instrumented_text,
            ]
        ),
        "metadata": {"probes": [_probe_metadata_entry(probe_def)], "warnings": []},
    }


def write_manual_instrumented_netlist(
    source_text: str,
    output_netlist_path: str | Path,
    probe_map_path: str | Path,
    net_name: str,
    moved_statements: list[str],
    wrdata_output: str | Path,
) -> dict:
    """Write a manually instrumented netlist and its metadata."""
    preview = preview_manual_instrumentation(source_text, net_name, moved_statements, wrdata_output)
    output_path = Path(output_netlist_path).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(preview["instrumented_text"], encoding="utf-8")
    write_em_probe_map(probe_map_path, preview["metadata"])
    return preview["metadata"]


def instrument_netlist_text_for_em(source_text: str, config: dict) -> tuple[str, dict]:
    """Instrument a netlist string without touching subcircuit bodies."""
    project_mode = str(config.get("project_mode", "tiny_tapeout"))
    wrdata_output = Path(str(config["wrdata_output"])).resolve()
    statements = _split_statements(source_text)
    top_level_infos = _collect_top_level_infos(statements)
    probe_defs, global_warnings = _build_probe_defs(top_level_infos, project_mode)

    instrumented_text = _instrument_text_with_probe_defs(source_text, probe_defs, wrdata_output)

    metadata = {
        "probes": [_probe_metadata_entry(probe) for probe in probe_defs],
        "warnings": global_warnings,
    }
    return instrumented_text, metadata


def ensure_em_workspace(repo_root: str | Path) -> dict[str, Path]:
    """Create and return the fixed EM workspace directories."""
    base = Path(repo_root).resolve() / "workspace" / "em"
    paths = {
        "base": base,
        "netlists": base / "netlists",
        "inputs": base / "inputs",
        "reports": base / "reports",
    }
    for path in paths.values():
        path.mkdir(parents=True, exist_ok=True)
    return paths


def write_em_probe_map(path: str | Path, metadata: dict) -> Path:
    """Write probe metadata to JSON."""
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    return output


def normalize_em_current_file(raw_path: str | Path, normalized_path: str | Path, probe_map_path: str | Path) -> dict:
    """Convert ngspice wrdata output into a deterministic 1-time + N-current file."""
    raw_file = Path(raw_path).resolve()
    normalized_file = Path(normalized_path).resolve()
    probe_map_file = Path(probe_map_path).resolve()

    probe_map = json.loads(probe_map_file.read_text(encoding="utf-8"))
    probes = probe_map.get("probes", [])
    expected_currents = len(probes)
    if expected_currents <= 0:
        raise ValueError("Probe map contains no probes to normalize.")

    rows = _read_numeric_rows(raw_file)
    if not rows:
        raise ValueError(f"No numeric EM current rows found in {raw_file}.")

    normalized_rows, warnings = _normalize_wrdata_rows(rows, expected_currents)
    normalized_file.parent.mkdir(parents=True, exist_ok=True)
    header = ["time"] + [probe.get("original_net") or probe.get("probe_name", f"probe_{index + 1}") for index, probe in enumerate(probes)]
    with normalized_file.open("w", encoding="utf-8") as handle:
        handle.write(",".join(header) + "\n")
        for row in normalized_rows:
            handle.write(",".join(f"{value:.12g}" for value in row) + "\n")

    return {
        "normalized_path": str(normalized_file),
        "warnings": warnings,
        "probe_count": expected_currents,
        "row_count": len(normalized_rows),
    }


def _split_statements(source_text: str) -> list[list[str]]:
    statements: list[list[str]] = []
    current: list[str] = []
    for line in source_text.splitlines():
        if current and line.lstrip().startswith("+"):
            current.append(line)
            continue
        if current:
            statements.append(current)
        current = [line]
    if current:
        statements.append(current)
    return statements


def _instrument_text_with_probe_defs(source_text: str, probe_defs: list[dict], wrdata_output: Path) -> str:
    statements = _split_statements(source_text)
    instrumented_lines: list[str] = []
    inserted_block = False
    in_subckt = False

    for statement in statements:
        first_line = statement[0]
        stripped = first_line.strip()
        lowered = stripped.lower()

        if lowered.startswith(".subckt"):
            in_subckt = True
            instrumented_lines.extend(statement)
            continue
        if in_subckt:
            instrumented_lines.extend(statement)
            if lowered.startswith(".ends"):
                in_subckt = False
            continue
        if _is_comment_or_blank(stripped):
            instrumented_lines.extend(statement)
            continue
        if lowered == ".end" and not inserted_block:
            instrumented_lines.extend(_probe_source_lines(probe_defs))
            instrumented_lines.extend(_control_block_lines(wrdata_output, probe_defs))
            inserted_block = True
            instrumented_lines.extend(statement)
            continue
        instrumented_lines.extend(_rewrite_top_level_statement(statement, probe_defs))

    if not inserted_block:
        instrumented_lines.extend(_probe_source_lines(probe_defs))
        instrumented_lines.extend(_control_block_lines(wrdata_output, probe_defs))
        instrumented_lines.append(".end")
    return "\n".join(instrumented_lines).rstrip() + "\n"


def _read_numeric_rows(path: Path) -> list[list[float]]:
    rows: list[list[float]] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith(("*", ";", "#")):
            continue
        tokens = re.split(r"[,\s]+", stripped)
        try:
            rows.append([float(token) for token in tokens if token])
        except ValueError:
            continue
    return rows


def _normalize_wrdata_rows(rows: list[list[float]], expected_currents: int) -> tuple[list[list[float]], list[str]]:
    warnings: list[str] = []
    normalized_rows: list[list[float]] = []
    expected_clean = expected_currents + 1
    expected_pair_with_time = 2 * (expected_currents + 1)
    expected_pair_without_time = 2 * expected_currents

    for row in rows:
        if len(row) == expected_clean:
            normalized_rows.append(row[:expected_clean])
            continue
        if len(row) == expected_pair_with_time:
            warnings.append("Duplicated time columns were found in raw wrdata output and normalized.")
            normalized_rows.append([row[1]] + [row[2 * index + 1] for index in range(1, expected_currents + 1)])
            continue
        if len(row) == expected_pair_without_time:
            warnings.append("Duplicated time columns were found in raw wrdata output and normalized.")
            normalized_rows.append([row[0]] + [row[2 * index + 1] for index in range(expected_currents)])
            continue

        time_values = [candidate[0] for candidate in rows]
        duplicate_indexes = [0]
        for column_index in range(1, len(row)):
            if _column_matches_reference(rows, column_index, time_values):
                duplicate_indexes.append(column_index)
        duplicate_indexes = sorted(set(duplicate_indexes))
        current_indexes = [index for index in range(len(row)) if index not in duplicate_indexes]
        if duplicate_indexes and len(current_indexes) == expected_currents:
            warnings.append("Time-like duplicate columns were removed during EM normalization.")
            normalized_rows.append([row[duplicate_indexes[0]]] + [row[index] for index in current_indexes])
            continue
        raise ValueError(
            f"Raw EM current file has {len(row)} columns; expected {expected_clean}, {expected_pair_with_time}, or {expected_pair_without_time} for {expected_currents} probes."
        )

    return normalized_rows, sorted(set(warnings))


def _column_matches_reference(rows: list[list[float]], column_index: int, reference: list[float], tolerance: float = 1e-18) -> bool:
    for row_index, row in enumerate(rows):
        if column_index >= len(row):
            return False
        if abs(row[column_index] - reference[row_index]) > tolerance:
            return False
    return True


def _collect_top_level_infos(statements: list[list[str]]) -> list[dict]:
    infos: list[dict] = []
    in_subckt = False
    for statement_index, statement in enumerate(statements):
        first_line = statement[0]
        stripped = first_line.strip()
        lowered = stripped.lower()
        if lowered.startswith(".subckt"):
            in_subckt = True
            continue
        if in_subckt:
            if lowered.startswith(".ends"):
                in_subckt = False
            continue
        if _is_comment_or_blank(stripped):
            continue
        parsed = _parse_statement_tokens(statement)
        if not parsed:
            continue
        infos.append(
            {
                "statement_index": statement_index,
                "statement_name": parsed["tokens"][0],
                "statement": statement,
                "prefix": parsed["prefix"],
                "nodes": parsed["nodes"],
                "line_text": _flatten_statement(statement),
                "net_pin_positions": {net: position for position, net in enumerate(parsed["nodes"], start=1)},
            }
        )
    return infos


def _build_probe_defs(top_level_infos: list[dict], project_mode: str) -> tuple[list[dict], list[str]]:
    probes: list[dict] = []
    global_warnings: list[str] = []
    used_probe_names: set[str] = set()
    candidate_nets: list[str] = []
    seen: set[str] = set()
    for info in top_level_infos:
        for net_name in info["nodes"]:
            if net_name not in seen and _should_instrument_net(net_name, project_mode):
                seen.add(net_name)
                candidate_nets.append(net_name)

    for index, net_name in enumerate(candidate_nets, start=1):
        sanitized = re.sub(r"[^A-Za-z0-9_]", "_", net_name).strip("_") or f"net_{index}"
        probe_name = f"VPROBE_{sanitized}"
        if probe_name in used_probe_names:
            probe_name = f"{probe_name}_{index}"
        used_probe_names.add(probe_name)

        if _is_supply_net(net_name):
            probes.append(
                {
                    "probe_name": probe_name,
                    "original_net": net_name,
                    "node_inserted": f"{net_name}__em",
                    "current_expr": f"i({probe_name})",
                    "mode": "rail_series",
                    "warnings": [],
                }
            )
            continue

        if _is_output_net(net_name):
            output_probe = _build_output_probe_def(net_name, probe_name, top_level_infos)
            if output_probe is not None:
                probes.append(output_probe)
            else:
                global_warnings.append(f"Output net {net_name} could not be safely instrumented; current may be unavailable.")
            continue

        probes.append(
            {
                "probe_name": probe_name,
                "original_net": net_name,
                "node_inserted": f"{net_name}__em",
                "current_expr": f"i({probe_name})",
                "mode": "net_series",
                "warnings": [],
            }
        )
    return probes, global_warnings


def _build_output_probe_def(net_name: str, probe_name: str, top_level_infos: list[dict]) -> dict | None:
    connected = [info for info in top_level_infos if net_name in info["nodes"]]
    load_infos = [info for info in connected if info["prefix"] in LOAD_PREFIXES]
    driver_infos = [info for info in connected if info["prefix"] not in LOAD_PREFIXES | SOURCE_PREFIXES]
    if not load_infos or not driver_infos:
        return None

    moved_statements = [info["statement_name"] for info in driver_infos]
    return {
        "probe_name": probe_name,
        "original_net": net_name,
        "node_inserted": f"{net_name}__drv",
        "current_expr": f"i({probe_name})",
        "mode": "output_driver_load",
        "moved_statements": moved_statements,
        "warnings": ["Output net instrumented using driver/load split."],
    }


def _manual_probe_def(net_name: str, moved_statements: list[str]) -> dict:
    sanitized = re.sub(r"[^A-Za-z0-9_]", "_", net_name).strip("_") or "manual_net"
    return {
        "probe_name": f"VPROBE_{sanitized}_manual",
        "original_net": net_name,
        "node_inserted": f"{net_name}__manual_drv",
        "current_expr": f"i(VPROBE_{sanitized}_manual)",
        "mode": "internal_manual",
        "moved_statements": moved_statements,
        "warnings": ["User-defined instrumentation", "Manual instrumentation; interpretation depends on selected branch."],
    }


def _probe_source_lines(probe_defs: list[dict]) -> list[str]:
    if not probe_defs:
        return []
    lines = ["", "* EM probe sources inserted by SKY130 Flow GUI"]
    for probe in probe_defs:
        lines.append(f"{probe['probe_name']} {probe['original_net']} {probe['node_inserted']} 0")
    return lines


def _probe_metadata_entry(probe: dict) -> dict:
    return {
        "probe_name": probe["probe_name"],
        "original_net": probe["original_net"],
        "node_inserted": probe["node_inserted"],
        "current_expr": probe["current_expr"],
        "mode": probe["mode"],
        "moved_statements": probe.get("moved_statements", []),
        "warnings": probe.get("warnings", []),
    }


def _control_block_lines(wrdata_output: Path, probe_defs: list[dict]) -> list[str]:
    expressions = " ".join(["time"] + [probe["current_expr"] for probe in probe_defs]) if probe_defs else "time"
    return [
        "",
        ".control",
        "run",
        f"wrdata {wrdata_output} {expressions}",
        ".endc",
    ]


def _rewrite_top_level_statement(statement: list[str], probe_defs: list[dict]) -> list[str]:
    parsed = _parse_statement_tokens(statement)
    if not parsed:
        return statement
    if parsed["prefix"] in SOURCE_PREFIXES:
        return statement

    if not any(_probe_applies_to_statement(probe, parsed) for probe in probe_defs):
        return statement

    updated_lines = list(statement)
    replacements_by_line: dict[int, list[tuple[int, int, str]]] = {}
    for item in parsed["items"]:
        if item["token_index"] not in parsed["node_token_indexes"]:
            continue
        replacement = None
        for probe in probe_defs:
            if item["text"] == probe["original_net"] and _probe_applies_to_statement(probe, parsed):
                replacement = probe["node_inserted"]
                break
        if not replacement:
            continue
        replacements_by_line.setdefault(item["line_index"], []).append((item["start"], item["end"], replacement))
    for line_index, replacements in replacements_by_line.items():
        line_text = updated_lines[line_index]
        for start, end, replacement in sorted(replacements, reverse=True):
            line_text = line_text[:start] + replacement + line_text[end:]
        updated_lines[line_index] = line_text
    return updated_lines


def _parse_statement_tokens(statement: list[str]) -> dict | None:
    first_line = statement[0].lstrip()
    if not first_line:
        return None
    name = first_line.split(None, 1)[0]
    if not name or name[0] in ".*+":
        return None

    items: list[dict] = []
    for line_index, line in enumerate(statement):
        for match in re.finditer(r"\S+", line):
            items.append(
                {
                    "text": match.group(0),
                    "line_index": line_index,
                    "start": match.start(),
                    "end": match.end(),
                    "token_index": len(items),
                }
            )
    if len(items) < 2:
        return None

    tokens = [item["text"] for item in items]
    prefix = tokens[0][0].lower()
    node_token_indexes: list[int]
    if prefix == "x":
        stop = len(tokens)
        for idx in range(1, len(tokens)):
            if "=" in tokens[idx]:
                stop = idx
                break
        if stop < 3:
            return None
        node_token_indexes = list(range(1, stop - 1))
    else:
        node_count = DEVICE_NODE_COUNTS.get(prefix)
        if not node_count or len(tokens) < node_count + 1:
            return None
        node_token_indexes = list(range(1, 1 + node_count))

    nodes = [tokens[index] for index in node_token_indexes]
    return {
        "items": items,
        "tokens": tokens,
        "nodes": nodes,
        "node_token_indexes": set(node_token_indexes),
        "prefix": prefix,
    }


def _should_instrument_net(net_name: str, project_mode: str) -> bool:
    if _is_supply_net(net_name) or _is_output_net(net_name):
        return True
    lowered = net_name.lower()
    if project_mode != "tiny_tapeout":
        return False
    return lowered.startswith(TT_DIGITAL_PREFIXES)


def _is_supply_net(net_name: str) -> bool:
    return net_name.lower() in SUPPLY_NETS


def _is_output_net(net_name: str) -> bool:
    return net_name.lower().startswith(OUTPUT_NET_PREFIXES)


def _classify_internal_element(prefix: str) -> str:
    lowered = prefix.lower()
    if lowered in LOAD_PREFIXES:
        return "passive"
    if lowered == "x":
        return "driver"
    return "unknown"


def _normalized_net_name(value: str | None) -> str:
    return (value or "").strip().lower()


def _probe_applies_to_statement(probe: dict, parsed: dict) -> bool:
    if probe["original_net"] not in parsed["nodes"]:
        return False
    if probe["mode"] == "output_driver_load":
        return parsed["tokens"][0] in set(probe.get("moved_statements", []))
    if probe["mode"] == "internal_manual":
        return parsed["tokens"][0] in set(probe.get("moved_statements", []))
    return True


def _flatten_statement(statement: list[str]) -> str:
    pieces: list[str] = []
    for index, line in enumerate(statement):
        text = line.strip()
        if index > 0 and text.startswith("+"):
            text = text[1:].strip()
        pieces.append(text)
    return " ".join(piece for piece in pieces if piece)


def _is_comment_or_blank(stripped: str) -> bool:
    return not stripped or stripped.startswith(("*", ";", "#"))
