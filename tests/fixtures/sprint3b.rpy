# Sprint 3B 测试夹具：对话翻译标识符与对话 tl 生成
# 覆盖：say 结构字段（who/attributes/临时属性/with 表达式/arguments/nointeract/id）、
# 叙述、centered/nvl 变体、extend 续写、连续空格、跨行三引号。

define e = Character(_("Eileen"))
define m = Character("May")

label start:

    # --- 简单对白 ---
    e "Hello world."

    # --- 叙述 ---
    "Narrator line."

    # --- say 变体 ---
    centered "A centered line."
    nvl "An NVL line."

    # --- who + attributes ---
    nvl centered "NVL centered."

    # --- who + 临时属性 ---
    e @ flash "Flash line."

    # --- who + with 表达式（含括号）---
    e "Fade with args." with Dissolve(0.5, alpha=True)

    # --- who + arguments ---
    e "With arguments." (test=1)

    # --- who + nointeract ---
    e "No interact line." nointeract

    # --- who + 显式 id ---
    e "Explicit id." id custom_abc

    # --- who + id（带行尾冒号）---
    e "Id with colon." id start_colon_id:

    # --- 连续空格对白 ---
    e "Two  spaces  here."

    # --- extend 续写 ---
    e "First part."
    extend " second part."

    # --- 带点号 who ---
    m.e "Dotted who."

    return

label second:

    # --- 同一文本在不同 label（冲突后缀验证）---
    e "Repeated text."
    e "Repeated text."
