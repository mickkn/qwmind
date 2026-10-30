"""
:File:        src/qwbot/controller.py

:Details:     Map bot actions to console commands and release held keys.

:Date:        30-10-2026
:Author:      Mick K.
"""

from .models import Action

KEYS = ("forward", "moveleft", "moveright", "jump")


class Controller:
    def __init__(self, transport):
        self.transport = transport
        self.held = set()

    def command(self, cmd):
        self.transport.send(cmd)

    def apply(self, action: Action):
        wanted = {
            name
            for name, enabled in (
                ("forward", action.forward),
                ("moveleft", action.left),
                ("moveright", action.right),
                ("jump", action.jump),
            )
            if enabled
        }
        for name in KEYS:
            if name in self.held and name not in wanted:
                self.command("-" + name)
                self.held.remove(name)
        for name in KEYS:
            if name in wanted and name not in self.held:
                self.command("+" + name)
                self.held.add(name)
        if action.turn:
            # 'rotate' availability/semantics must be checked for the ezQuake build.
            self.command(f"rotate {action.turn:g}")

    def stop(self):
        # Force all releases, including keys held by a previous crashed run.
        for name in KEYS:
            self.command("-" + name)
        self.held.clear()
