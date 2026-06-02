"""Convert basic-pitch note events into ASCII guitar tab or structured column data."""

from typing import Dict, List, Tuple

TUNINGS = {
    "guitar": {"open_midi": [64, 59, 55, 50, 45, 40], "names": ["e", "B", "G", "D", "A", "E"]},
    "bass":   {"open_midi": [43, 38, 33, 28],          "names": ["G", "D", "A", "E"]},
}
MAX_FRET = 22


def _fret_options(pitch: int, open_midi: List[int]) -> List[Tuple[int, int]]:
    options = []
    for s, open_note in enumerate(open_midi):
        fret = pitch - open_note
        if 0 <= fret <= MAX_FRET:
            options.append((s, fret))
    return options


def _assign_column(pitches: List[int], hand_pos: float, open_midi: List[int]) -> Dict[int, int]:
    used: set = set()
    assignments: Dict[int, int] = {}
    for pitch in sorted(pitches, reverse=True):
        options = _fret_options(pitch, open_midi)
        if not options:
            continue
        options.sort(key=lambda sf: (abs(sf[1] - hand_pos), sf[1]))
        for s, fret in options:
            if s not in used:
                assignments[s] = fret
                used.add(s)
                break
    return assignments


def notes_to_tab(
    note_events,
    tuning: str = "guitar",
    quantize_ms: int = 80,
    cols_per_line: int = 32,
) -> str:
    if not note_events:
        return "No notes detected."

    tuning_cfg = TUNINGS[tuning]
    open_midi = tuning_cfg["open_midi"]
    string_names = tuning_cfg["names"]
    num_strings = len(open_midi)

    q = quantize_ms / 1000.0
    bins: Dict[int, List[int]] = {}
    for start, _end, pitch, amp, *_ in note_events:
        if amp < 0.2:
            continue
        b = int(start / q)
        bins.setdefault(b, []).append(pitch)

    if not bins:
        return "No notes detected above confidence threshold."

    max_bin = max(bins.keys())
    columns: List[Dict[int, int]] = []
    hand_pos = 0.0
    for i in range(max_bin + 1):
        col = _assign_column(bins.get(i, []), hand_pos, open_midi) if i in bins else {}
        if col:
            frets = list(col.values())
            hand_pos = hand_pos * 0.7 + (sum(frets) / len(frets)) * 0.3
        columns.append(col)

    while columns and not columns[-1]:
        columns.pop()

    if not columns:
        return "No playable notes detected."

    max_digits = max((len(str(f)) for col in columns for f in col.values()), default=1)
    col_w = max_digits + 2

    sections = []
    for chunk_start in range(0, len(columns), cols_per_line):
        chunk = columns[chunk_start : chunk_start + cols_per_line]
        rows = {s: string_names[s] + "|" for s in range(num_strings)}
        for col in chunk:
            for s in range(num_strings):
                if s in col:
                    fs = str(col[s])
                    pad = col_w - len(fs)
                    rows[s] += "-" * (pad // 2) + fs + "-" * (pad - pad // 2) + "-"
                else:
                    rows[s] += "-" * col_w + "-"
        for s in range(num_strings):
            rows[s] += "|"
        sections.append("\n".join(rows[s] for s in range(num_strings)))

    return "\n\n".join(sections)


def notes_to_columns(
    note_events,
    tuning: str = "guitar",
    quantize_ms: int = 80,
) -> List[dict]:
    """Returns list of {"time": float, "notes": {str(string_idx): fret}} for playhead use."""
    if not note_events:
        return []

    tuning_cfg = TUNINGS[tuning]
    open_midi = tuning_cfg["open_midi"]

    q = quantize_ms / 1000.0
    bins: Dict[int, List[int]] = {}
    bin_time: Dict[int, float] = {}
    for start, _end, pitch, amp, *_ in note_events:
        if amp < 0.2:
            continue
        b = int(start / q)
        bins.setdefault(b, []).append(pitch)
        # Use the earliest start time for this bin
        if b not in bin_time or start < bin_time[b]:
            bin_time[b] = start

    if not bins:
        return []

    max_bin = max(bins.keys())
    result = []
    hand_pos = 0.0

    for i in range(max_bin + 1):
        if i not in bins:
            continue
        col = _assign_column(bins[i], hand_pos, open_midi)
        if col:
            frets = list(col.values())
            hand_pos = hand_pos * 0.7 + (sum(frets) / len(frets)) * 0.3
            result.append({
                "time": float(bin_time[i]),
                "notes": {str(s): int(fret) for s, fret in col.items()},
            })

    return result
