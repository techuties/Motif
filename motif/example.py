"""A tiny example script so the editor is never an empty mystery."""

from motif.models import Event, EventType, HumanizePreset, Script


def example_script() -> Script:
    script = Script(name="Welcome motif")
    script.humanize.apply_preset(HumanizePreset.PRECISE.value)
    script.origin_x = 200
    script.origin_y = 200
    script.origin_set = True
    script.loop.count = 2
    script.loop.return_to_origin = True
    script.notes = "Rename, drag, or delete any row. Add a colour trigger from the + menu."
    script.events = [
        Event(type=EventType.COMMENT.value, name="Start", notes="Everything is relative to origin."),
        Event(type=EventType.GO_ORIGIN.value, name="Go to zero ground", delay_ms=80),
        Event(type=EventType.MOVE.value, name="Approach", delay_ms=40, x=180, y=40),
        Event(
            type=EventType.CLICK.value,
            name="Click target",
            delay_ms=60,
            x=180,
            y=40,
            button="left",
            pressed=True,
        ),
        Event(
            type=EventType.CLICK.value,
            name="Release",
            delay_ms=70,
            x=180,
            y=40,
            button="left",
            pressed=False,
        ),
        Event(
            type=EventType.WAIT_PIXEL.value,
            name="When pixel turns green",
            x=180,
            y=40,
            color="#34C759",
            tolerance=22,
            match="is",
            timeout_ms=4000,
        ),
        Event(type=EventType.KEY_DOWN.value, name="Press enter", key="enter", delay_ms=80),
        Event(type=EventType.KEY_UP.value, name="Release enter", key="enter", delay_ms=50),
        Event(type=EventType.WAIT.value, name="Breathe", delay_ms=300),
    ]
    return script
