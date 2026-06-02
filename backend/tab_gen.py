"""Convert basic-pitch note events into ASCII guitar tab."""

from typing import List, Tuple, Dict, Optional

# Standard tuning: string index 0 = high e, 5 = low E
OPEN_MIDI = [64, 59, 55, 50, 45, 40]  # e B G D A E
STRING_NAMES = ["e", "B", "G", "D", "A", "E"]
MAX_FRET = 22


def _fret_options(pitch: int) -> List[Tuple[int, int]]:
    """Return all (string_idx, fret) pairs that can produce this MIDI pitch."""
    options = []
    for s, open_note in enumerate(OPEN_MIDI):
        fret = pitch - open_note
        if 0 <= fret <= MAX_FRET:
            options.append((s, fret))
    return options


def _assign_column(pitches: List[int], hand_pos: float) -> Dict[int, int]:
    """
    Greedily assign pitches to strings for one time column.
    Prefers string/fret combos close to the current hand position.
    Returns {string_idx: fret}.
    """
    used_strings: set = set()
    assignments: Dict[int, int] = {}

    for pitch in sorted(pitches, reverse=True):
        options = _fret_options(pitch)
        if not options:
            continue
        # Sort by distance from hand position, then by fret number
        options.sort(key=lambda sf: (abs(sf[1] - hand_pos), sf[1]))
        for s, fret in options:
            if s not in used_strings:
                assignments[s] = fret
                used_strings.add(s)
                break

    return assignments


def notes_to_tab(
    note_events: List[Tuple[float, float, int, float]],
    quantize_ms: int = 80,
    cols_per_line: int = 32,
) -> str:
    """
    Convert basic-pitch note events to ASCII guitar tab.

    note_events: list of (start_s, end_s, midi_pitch, amplitude)
    """
    if not note_events:
        return "No notes detected."

    q = quantize_ms / 1000.0

    # Group pitches by quantized time bin
    bins: Dict[int, List[int]] = {}
    for start, _end, pitch, amp in note_events:
        if amp < 0.25:  # skip very quiet detections
            continue
        b = int(start / q)
        bins.setdefault(b, []).append(pitch)

    if not bins:
        return "No notes detected above confidence threshold."

    max_bin = max(bins.keys())

    # Build a list of column assignments
    columns: List[Dict[int, int]] = []
    hand_pos = 0.0
    for i in range(max_bin + 1):
        if i in bins:
            col = _assign_column(bins[i], hand_pos)
            if col:
                frets = list(col.values())
                hand_pos = hand_pos * 0.7 + (sum(frets) / len(frets)) * 0.3
            columns.append(col)
        else:
            columns.append({})

    # Remove trailing empty columns
    while columns and not columns[-1]:
        columns.pop()

    if not columns:
        return "No playable notes detected."

    # Determine column render width (widest fret number + 2 dashes)
    max_fret_digits = max(
        (len(str(fret)) for col in columns for fret in col.values()),
        default=1,
    )
    col_w = max_fret_digits + 2  # dashes on both sides

    # Render in chunks
    sections: List[str] = []
    for chunk_start in range(0, len(columns), cols_per_line):
        chunk = columns[chunk_start : chunk_start + cols_per_line]
        rows = {s: STRING_NAMES[s] + "|" for s in range(6)}

        for col in chunk:
            for s in range(6):
                if s in col:
                    fret_str = str(col[s])
                    pad = col_w - len(fret_str)
                    left = "-" * (pad // 2)
                    right = "-" * (pad - pad // 2)
                    rows[s] += left + fret_str + right + "-"
                else:
                    rows[s] += "-" * col_w + "-"

        for s in range(6):
            rows[s] += "|"

        sections.append("\n".join(rows[s] for s in range(6)))

    return "\n\n".join(sections)
