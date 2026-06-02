"""Convert note events to MIDI file bytes using mido."""

import io

import mido


def notes_to_midi_bytes(note_events, tempo_bpm: int = 120, instrument: int = 25) -> bytes:
    """Convert note events to MIDI file bytes using mido."""
    mid = mido.MidiFile(type=0, ticks_per_beat=480)
    track = mido.MidiTrack()
    mid.tracks.append(track)

    track.append(mido.MetaMessage("set_tempo", tempo=mido.bpm2tempo(tempo_bpm), time=0))
    track.append(mido.Message("program_change", channel=0, program=instrument, time=0))

    ticks_per_second = 480 * tempo_bpm / 60

    events = []
    for event in note_events:
        start, end, pitch, amp, *_ = event
        velocity = max(1, min(127, int(amp * 100)))
        events.append((int(start * ticks_per_second), "note_on", pitch, velocity))
        events.append((int(end * ticks_per_second), "note_off", pitch, 0))

    # Sort: same tick → note_off before note_on
    events.sort(key=lambda e: (e[0], 0 if e[1] == "note_off" else 1))

    current_tick = 0
    for tick, msg_type, pitch, vel in events:
        delta = max(0, tick - current_tick)
        track.append(mido.Message(msg_type, channel=0, note=pitch, velocity=vel, time=delta))
        current_tick = tick

    buf = io.BytesIO()
    mid.save(file=buf)
    return buf.getvalue()
