define e = Character(_("Eileen"))
define n = Character("Narrator")

label start:
    # ordinary dialogue
    e "Hello from official extraction."

    # narration
    "This is a narration line."

    # menu labels and menu branch dialogue
    menu:
        "Choose the first path":
            e "The first path is selected."
        "Choose the repeated path":
            e "Repeated dialogue."

    # Menu is translation-relevant and this following say is deliberately
    # adjacent, so Ren'Py's Restructurer can emit one multi-statement block.
    e "Dialogue after menu."

    # nvl / voice statement coverage
    nvl clear
    n "This is an NVL-style narrator line."
    voice "audio/voice.ogg"

    # marked strings
    $ marked_one = _("Marked string one")
    $ marked_two = __("Marked string two")

    # repeated dialogue occurrences are intentionally separate
    e "Repeated dialogue."
    e "Repeated dialogue."

    # explicit id
    e "Explicit identifier dialogue." id explicit_validation_id
    return
