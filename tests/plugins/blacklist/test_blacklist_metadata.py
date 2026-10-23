from packages.blacklist import __plugin_meta__


def test_blacklist_metadata_uses_sdk_declarations():
    perms = __plugin_meta__.extra.get("command_permissions") or []
    ids = {row["id"] for row in perms}
    assert ids == {
        "blacklist.add",
        "blacklist.remove",
        "blacklist.list",
        "blacklist.scrub_add",
        "blacklist.scrub_remove",
        "blacklist.scrub_list",
        "blacklist.bot_scrub_add",
        "blacklist.bot_scrub_remove",
        "blacklist.bot_scrub_list",
    }
    assert __plugin_meta__.extra.get("reload_policy") == "metadata"
