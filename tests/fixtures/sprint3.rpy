# Sprint 3 测试夹具
# 覆盖：extend 续写（speaker=None、空文本过滤、id/with/注释尾部）、
# 资源引用语句跳过（shader / font / voice）、空文本兜底过滤。

define e = Character(_("Eileen"))

label start:

    e "First half of the line."
    extend " second half."
    extend " and a trailing bit." with dissolve
    extend " with an id." id start_extend_1:
    extend " with a comment." # 行内注释

    # 空文本续写不产出单元（extend ""）
    menu:
        extend ""

    # 资源引用语句：不是可翻译文本，必须跳过
    shader "distortion_perlin"
    font "gui/fonts/KelmscottRomanNF.ttf"
    voice "audio/v001.ogg"

    # 空文本兜底："" 与 _("") 均不产出单元
    e ""
    extend ""
    $ tmp = _("")

    # 反例：define 裸字符串、注释内引号
    define silence = Character("Silent")
    # "not real dialogue"

    return
