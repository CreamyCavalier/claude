"""Convert basic-pitch note events into ASCII guitar tab."""

from typing import Dict, List, Tuple

OPEN_MIDI = [64, 59, 55, 50, 45, 40]  # e B G D A E (high to low)
STRING_NAMES = ["e", "B", "G", "D", "A", "E"]
MAX_FRET = 22


def _fret_options(pitch: int) -> List[Tuple[int, int]]:
    options = []
    for s, open_note in enumerate(OPEN_MIDI):
        fret = pitch - open_note
        if 0 <= fret <= MAX_FRET:
            options.append((s, fret))
    return options


def _assign_column(pitches: List[int], hand_pos: float) -> Dict[int, int]:
    used: set = set()
    assignments: Dict[int, int] = {}
    for pitch in sorted(pitches, reverse=True):
        options = _fret_options(pitch)
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
    note_events: List[Tuple[float, float, int, float]],
    quantize_ms: int = 80,
    cols_per_line: int = 32,
) -> str:
    if not note_events:
        return "No notes detected."

    q = quantize_ms / 1000.0
    bins: Dict[int, List[int]] = {}
    for start, _end, pitch, amp in note_events:
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
        col = _assign_column(bins.get(i, []), hand_pos) if i in bins else {}
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
        rows = {s: STRING_NAMES[s] + "|" for s in range(6)}
        for col in chunk:
            for s in range(6):
                if s in col:
                    fs = str(col[s])
                    pad = col_w - len(fs)
                    rows[s] += "-" * (pad // 2) + fs + "-" * (pad - pad // 2) + "-"
                else:
                    rows[s] += "-" * col_w + "-"
        for s in range(6):
            rows[s] += "|"
        sections.append("\n".join(rows[s] for s in range(6)))

    return "\n\n".join(sections)
