# Sprint 3B 修复夹具：误提取回归（play/queue/show + ATL/style 块）
# 覆盖反例：
# - 保留语句关键字（镜像 Ren'Py parser.py 语句分发）：
#   play / queue / stop / show / scene / camera / window / voice / shader / font
# - image / transform / style 块内的 ATL 引号行与样式属性行
#   （"bg fire dark" with Dissolve(...) / color / thumb / background / layout /
#   size_group / unscrollable 等均不是对白）
# 正例：块结束后的对白仍要提取（验证块状态正确退出）。

define e = Character(_("Eileen"))

label start:

    # --- 保留语句关键字（不是对白）---
    play music "audio/x.ogg"
    play sound "audio/boom.ogg"
    queue sound "audio/step.ogg"
    stop music
    show text "Hello on screen"
    scene "bg room"
    window show
    voice "audio/voice.ogg"
    shader "distortion_perlin"
    font "gui/fonts/KelmscottRomanNF.ttf"

    # --- 关键字行上的 _() 标记字符串仍要提取（正例）---
    # Ren'Py scanstrings 全文件扫描 _()，与语句类型无关。
    show text _("Warning line one.\nWarning line two.")
    play music _("queue intro")
    # 关键字行上的普通字符串（未标记）仍不提取。
    show text "Not marked"

    # --- 块结束后的对白仍要提取 ---
    e "Dialogue after statements."

    # --- image 块：ATL 引号行不是对白 ---
    image bg fire dark:
        "bg fire dark" with Dissolve(0.5, alpha=True)
        "bg fire base"
    image bg fire single = "bg fire base"

    # --- transform 块：ATL 行不是对白 ---
    transform t:
        linear 0.5 xoffset 10
        "raw quoted line" with dissolve

    # --- style 块：属性字符串不是对白 ---
    style default:
        color "#000"
        hover_color "#cc0000"
        thumb "gui/slider/horizontal_[prefix_]thumb.png"
        background "gui/overlay/main_menu.png"
        layout "subtitle"
        size_group "navigation"
        unscrollable "hide"
        font "gui/fonts/AmaticSC-Bold.ttf"

    style plain is default

    # --- 块结束后的对白仍要提取 ---
    e "Dialogue after blocks."

    return
