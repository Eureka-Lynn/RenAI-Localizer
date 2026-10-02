# Copied from the legacy project's tests/fixtures/sprint3b.rpy.
define e = Character(_("Eileen"))
label start:
    e "Hello world."
    "Narrator line."
    centered "A centered line."
    nvl centered "NVL centered."
    e @ flash "Flash line."
    e "Fade with args." with Dissolve(0.5, alpha=True)
    e "With arguments." (test=1)
    e "No interact line." nointeract
    e "Explicit id." id custom_abc
    e "First part."
    extend " second part."
    return
