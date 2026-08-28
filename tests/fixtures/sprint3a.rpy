# Sprint 3A 测试夹具：Writer（字符串翻译通道）
# 覆盖：
# - 菜单选项（menu_choice）与 _() / __() 标记字符串（string）
# - 菜单选项的 \% → %%（Lexer.string 语义），写 tl 时 %% → %（old_substitutions）
# - string 的 %% 保留不替换
# - 对白（dialogue）不进入字符串翻译通道（Writer 跳过，测试断言不出现）
# - 含 \n 真实换行、制表符、转义字符的字符串
# - 相同 old 值出现多次（去重）

default hint = _("Discount 50%% for you.")
define label = __("Save file\t[slot]")
define ui_text = _("Column one.\nColumn two.")

label start:

    e "This dialogue must NOT appear in strings.rpy."

    menu:
        "Keep 100%% of it.":
            pass
        "Keep 100%% of it.":
            pass
        "A quote \" and slash \\ inside choice.":
            pass
        "Choice with newline.\nSecond line.":
            pass
        "Discount 50%% for you.":
            pass

    return
