"""Connection-scoped tool discovery; input permissions remain in the service."""
from .win32 import PilotError

TEST_TOOLS = frozenset({"launch_test", "close_test"})
LEGACY_OBSERVERS = frozenset({"observe", "observe_controls"})


class ToolPolicy:
    def __init__(self, config):
        if (not isinstance(config, dict) or set(config) - {"profile", "self_test"}
                or config.get("profile", "compact") not in ("compact", "legacy")
                or type(config.get("self_test", False)) is not bool):
            raise PilotError("INVALID_TOOL_POLICY")
        self.profile = config.get("profile", "compact")
        self.self_test = config.get("self_test", False)

    def visible(self, name):
        return ((name not in TEST_TOOLS or self.self_test)
                and (name not in LEGACY_OBSERVERS or self.profile == "legacy"))

    def require_public(self, name):
        if name in TEST_TOOLS and not self.self_test:
            raise PilotError("SELF_TEST_TOOLS_DISABLED")
        if name in LEGACY_OBSERVERS and self.profile != "legacy":
            raise PilotError("LEGACY_OBSERVER_DISABLED: use get_window_state or tools.profile=legacy")
