"""Session-static declared objectives for read_file; not an access-control policy."""

from copy import deepcopy


def intent_tool_schemas(agent, tools: list[dict]) -> list[dict]:
    """Copy only read_file's schema, pinning opt-in at the first surface build."""
    enabled = getattr(agent, "_read_file_declared_intent", None)
    if not isinstance(enabled, bool):
        from hermes_cli.config_effective import load_user_config_effective

        config = load_user_config_effective()
        enabled = (config.get("agent") or {}).get("read_file_declared_intent", False) is True
        agent._read_file_declared_intent = enabled
    if not enabled:
        return tools
    result = []
    for tool in tools:
        if (tool.get("function") or {}).get("name") == "read_file":
            tool = deepcopy(tool)
            parameters = tool["function"]["parameters"]
            parameters["properties"]["declared_intent"] = {
                "type": "string",
                "description": "Brief objective for this read, usually 3–10 words (not private reasoning).",
            }
            parameters["required"] = list(dict.fromkeys([*parameters.get("required", []), "declared_intent"]))
        result.append(tool)
    return result


def declared_intent_error(agent, name: str, args: dict) -> str | None:
    """Validate against the schema actually carried by this session (including resume pins)."""
    if name != "read_file":
        return None
    required = any(
        tool.get("function", {}).get("name") == name
        and "declared_intent" in tool["function"].get("parameters", {}).get("required", [])
        for tool in getattr(agent, "tools", [])
    )
    if required and (not isinstance(args.get("declared_intent"), str) or not args["declared_intent"].strip()):
        return "read_file requires declared_intent: a non-blank string describing the brief objective (usually 3–10 words)."
    return None
