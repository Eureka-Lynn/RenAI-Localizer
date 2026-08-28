# RenAI Localizer 测试夹具
# 模拟 Ren'Py 脚本中最常见的可本地化文本场景。

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
