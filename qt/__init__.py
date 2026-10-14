"""PS Focus's interface, built on Qt (PySide6)

Run from source with `py -m qt`. Run that way it keeps its own data folder, a copy of the real one, see preview.py;
`--real-data` uses the real folder instead.

Many comments match a measurement or behaviour to the Tk app this interface replaced, naming its files (ui_*.py,
main.py, rendering.py) or its PSFocusApp methods. Those files were removed in commit 3e15ae5; the commit before it
still has them.
"""
