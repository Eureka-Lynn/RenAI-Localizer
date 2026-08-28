# Sprint 3.5 测试夹具：文本值保真（转义与空白折叠）
# 覆盖：
# - say 的 \n 结尾 → 真换行（Lexer.string dequote）
# - say 的 \[ \] \{ \} \% \uXXXX 与未知转义 \t 各自还原
# - 菜单选项连续空格折叠为单空格
# - _() / __() 按 Python 字符串转义还原（\n → 换行、\t → 制表符）

define narrator = Character(None)

default hint = _("Line one.\nLine two.")
define back = __("Column\tTabbed")

label start:

    # --- say：\n 结尾 → 真换行（对应 flashback.rpy 的真实形态）---
    n "It's cold, and dark, and there are people screaming somewhere.\n"

    # --- say：字面量括号 / 花括号转义（dequote 后括号加倍）---
    e "Bracket \[escaped\] and brace \{escaped\}."

    # --- say：\% / \uXXXX / 未知转义 \t ---
    e "Percent \% and unicode \u4f60\u597d and unknown \t."

    # --- 菜单选项：连续空格折叠为单空格 ---
    menu:
        "{i}•  Run.{/i}":
            pass

    return
