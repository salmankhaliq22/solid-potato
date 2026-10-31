#!/usr/bin/env python3
"""Inline control_logic.js into control.html and write dist/control.html (stdlib only)."""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PLACEHOLDER = "/*__FLEET_LOGIC__*/"


def main():
    with open(os.path.join(HERE, "control.html"), encoding="utf-8") as fh:
        page = fh.read()
    with open(os.path.join(HERE, "control_logic.js"), encoding="utf-8") as fh:
        logic = fh.read()
    if page.count(PLACEHOLDER) != 1:
        sys.exit("control.html must contain %s exactly once" % PLACEHOLDER)
    if "</script" in logic.lower():
        sys.exit("control_logic.js must not contain a closing script tag")
    out = os.path.join(HERE, "dist", "control.html")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as fh:
        fh.write(page.replace(PLACEHOLDER, logic))
    print("wrote %s (%d bytes)" % (out, os.path.getsize(out)))


if __name__ == "__main__":
    main()
