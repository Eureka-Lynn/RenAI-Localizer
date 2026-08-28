# Sprint 2 测试夹具
# 覆盖多行字符串、单引号字符串、_()/__()、say id 子句、say 变体与反例。

define e = Character(_("Eileen"))
define silent = Character("Silent")  # 反例：define 裸字符串不提取

default mood = _("curious")
default greeting = __("hello")

define about = _p("multi line paragraph")  # 反例：_p 不在本 Sprint 范围
define name = ___("triple")  # 反例：___ 不在本 Sprint 范围

label start:

    # --- say 变体：centered / nvl ---
    centered "A centered line."
    nvl "An NVL line."
    nvl centered "NVL centered line."

    # --- 单引号字符串 ---
    e 'Single-quoted dialogue.'
    s 'It\'s got an escaped quote.'

    # --- 三引号多行 say（line 记录起始行）---
    e """This is a multi-line
dialogue that spans
several lines."""

    # --- say 的 id 子句 ---
    e "This has an id." id start_special_1
    e "This has an id with colon." id start_special_2:
    e "Fade text." with dissolve

    # --- 行尾注释不影响提取 ---
    e "Commented line." # 行内注释

    # 反例：注释中的引号不应提取
    # "not real dialogue"
    $ tmp = "not translatable"
    python:
        phrase = "also not translatable"
        other = _("not here either")

    return

init -1 python:
    also_not = _("init python string")

    # 注释行不影响块边界
    other_also_not = __("init python double")

screen test_screen():
    frame:
        style_group ""
        scrollbars "vertical"
        text _("Screen Label")
        textbutton _("Screen Button"):
            action Return()
