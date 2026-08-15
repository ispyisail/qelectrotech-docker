"""
scenarios — deterministic, goal-directed GUI test scripts for QElectroTech.

Different job from fuzzer/ (random-action crash hunting, success = "didn't
crash") and simulator/ (CLI-only file mutation, never touches the GUI). A
scenario drives the real GUI through a specific, scripted sequence -- open
QET, build a specific circuit, save -- and asserts the saved file actually
has the structure it should.

Built on top of what already existed rather than duplicating it:
  - fuzzer.actions.base.XDo / QETLayout for driving the GUI (click, drag,
    type, find the window). Carries the three reliability fixes diagnosed
    2026-08-15 (click-doubling, wrong-window matching, wrong geometry).
  - simulator.canon for verification: build the circuit, save, canonicalize
    the file, and assert on real structure (element count, conductor count,
    specific labels) instead of eyeballing a screenshot.

Add a new scenario by adding a new file next to simple_motor_starter.py and
registering it in __main__.py's REGISTRY.
"""
