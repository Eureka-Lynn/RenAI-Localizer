# Copied from the legacy project's tests/fixtures/sample.rpy.
define e = Character(_("Eileen"))

label start:
    "Welcome to Scarlet Hollow."
    e "Hello, traveler!"
    e "It's great to see you again, [player_name]."
    menu:
        "Ask about the town":
            e "The town has many secrets."
        "Talk to [npc_name]" if has_leaving_choice:
            "You decide to leave."
        "Stay quiet" (condition=allow_idle):
            pass
    e "Farewell. \"Take care of yourself.\""
    return
