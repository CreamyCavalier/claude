"""Export tab column data to Guitar Pro 5 (.gp5) format via PyGuitarPro."""

import io
import math

import guitarpro

QUARTER_TIME = 960  # GP internal ticks per quarter note
MEASURE_TICKS = QUARTER_TIME * 4  # 4/4 time
SIXTEENTH_TICKS = QUARTER_TIME // 4  # 240 ticks per 16th note

_TUNING_STRINGS = {
    "guitar": [(1, 64), (2, 59), (3, 55), (4, 50), (5, 45), (6, 40)],
    "bass":   [(1, 43), (2, 38), (3, 33), (4, 28)],
}


def notes_to_gp5_bytes(
    columns: list,
    tuning: str = "guitar",
    tempo_bpm: int = 120,
    track_name: str = "Guitar",
) -> bytes:
    if not columns:
        return b""

    beat_sec = 60.0 / tempo_bpm
    measure_sec = beat_sec * 4

    max_time = max(c["time"] for c in columns)
    num_measures = max(1, math.ceil(max_time / measure_sec))

    # Map: measure_idx -> {slot_16th -> notes_dict}
    beat_map: dict = {}
    for col in columns:
        t = col["time"]
        m = min(int(t / measure_sec), num_measures - 1)
        offset_sec = t - m * measure_sec
        slot = round(offset_sec / (beat_sec / 4))  # 16th-note grid
        slot = max(0, min(15, slot))
        beat_map.setdefault(m, {})[slot] = col["notes"]

    song = guitarpro.Song()
    song.tempo = tempo_bpm

    track = song.tracks[0]
    track.name = track_name
    track.strings = [guitarpro.GuitarString(n, v) for n, v in _TUNING_STRINGS[tuning]]
    track.fretCount = 24
    if tuning == "bass":
        track.channel.instrument = 33

    song.measureHeaders.clear()
    track.measures.clear()

    for m_idx in range(num_measures):
        m_start = QUARTER_TIME + m_idx * MEASURE_TICKS

        header = guitarpro.MeasureHeader()
        header.number = m_idx + 1
        header.start = m_start
        header.timeSignature.numerator = 4
        header.timeSignature.denominator.value = 4
        header.tempo.value = tempo_bpm
        song.measureHeaders.append(header)

        measure = guitarpro.Measure(track, header)
        voice = measure.voices[0]
        voice.beats.clear()

        m_notes = beat_map.get(m_idx, {})
        for slot in range(16):
            tick = m_start + slot * SIXTEENTH_TICKS
            beat = guitarpro.Beat(voice)
            beat.start = tick
            beat.duration = guitarpro.Duration(value=16)

            if slot in m_notes:
                beat.status = guitarpro.BeatStatus.normal
                for s_str, fret in m_notes[slot].items():
                    s = int(s_str) + 1  # GP strings are 1-indexed
                    note = guitarpro.Note(s)
                    note.value = int(fret)
                    beat.notes.append(note)
            else:
                beat.status = guitarpro.BeatStatus.rest

            voice.beats.append(beat)

        track.measures.append(measure)

    buf = io.BytesIO()
    guitarpro.write(song, buf)
    return buf.getvalue()
