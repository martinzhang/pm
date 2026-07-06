"""企业微信模板卡片构造工具

把「卡片长什么样」和「怎么把它发出去」彻底解耦：本模块只负责生成 SDK 认识的 dict，
不 import ws_client、不做任何网络 IO。返回值可直接传给：
    ws_client.reply_template_card(frame, card)
    ws_client.reply_stream_with_card(frame, sid, text, True, template_card=card)
    ws_client.update_template_card(frame, card)

设计要点：
- 5 个卡片类型各一个构造函数，只暴露业务真正用到的字段，其余高级字段用 **extra 透传。
- 「创建」和「更新」共用同一个构造函数：交互类卡片通过 disable / checked / selected
  参数切换到「已提交/已处理」的只读态，避免把同一份结构手写两遍。
- 子结构（来源、横向信息、跳转、按钮、选项）拆成小 helper，消除重复。

字段含义以官方长连接协议文档为准：
https://developer.work.weixin.qq.com/document/path/101463
"""
from __future__ import annotations

from typing import Any, Iterable, Sequence

# ── 卡片类型常量（对应 SDK 的 TemplateCardType 枚举取值） ──
TEXT_NOTICE = "text_notice"
NEWS_NOTICE = "news_notice"
BUTTON_INTERACTION = "button_interaction"
VOTE_INTERACTION = "vote_interaction"
MULTIPLE_INTERACTION = "multiple_interaction"

# ── 按钮样式（button_interaction 的 button.style） ──
BTN_BLUE = 1   # 蓝色（默认强调）
BTN_GRAY = 2   # 灰色（已处理/禁用态常用）
BTN_RED = 3    # 红色（拒绝/危险）


# ── 子结构 helper：把反复出现的小 dict 收敛成一处 ──
def source(desc: str, *, color: int = 0, icon_url: str | None = None) -> dict[str, Any]:
    """卡片左上角来源信息。color: 0 灰 / 1 黑 / 2 红 / 3 绿。"""
    src: dict[str, Any] = {"desc": desc, "desc_color": color}
    if icon_url:
        src["icon_url"] = icon_url
    return src


def main_title(title: str, desc: str | None = None) -> dict[str, Any]:
    """卡片主标题区。"""
    mt: dict[str, Any] = {"title": title}
    if desc is not None:
        mt["desc"] = desc
    return mt


def action_jump(url: str) -> dict[str, Any]:
    """整卡点击动作 / jump 项：跳转网页。"""
    return {"type": 1, "url": url}


def kv(keyname: str, value: str) -> dict[str, Any]:
    """一条纯文本横向信息。"""
    return {"keyname": keyname, "value": value}


def kv_link(keyname: str, value: str, url: str) -> dict[str, Any]:
    """一条可点击跳转的横向信息（type=1）。"""
    return {"keyname": keyname, "value": value, "type": 1, "url": url}


def jump(title: str, url: str) -> dict[str, Any]:
    """底部跳转列表的一项：跳转网页（type=1）。"""
    return {"type": 1, "url": url, "title": title}


def button(text: str, key: str, *, style: int = BTN_BLUE) -> dict[str, Any]:
    """一个交互按钮。"""
    return {"text": text, "style": style, "key": key}


def option(id: str, text: str, *, checked: bool | None = None) -> dict[str, Any]:
    """一个投票/选择项。checked 非 None 时写入 is_checked（用于更新态回显）。"""
    opt: dict[str, Any] = {"id": id, "text": text}
    if checked is not None:
        opt["is_checked"] = checked
    return opt


# ── 5 个卡片构造函数 ──
def text_notice(
    *,
    title: str,
    desc: str | None = None,
    source_desc: str | None = None,
    emphasis: tuple[str, str] | None = None,
    horizontal: Sequence[dict[str, Any]] | None = None,
    jumps: Sequence[dict[str, Any]] | None = None,
    action_url: str | None = None,
    **extra: Any,
) -> dict[str, Any]:
    """文本通知卡片。

    :param emphasis: (值, 说明)，渲染成醒目的大号数字/文案，如 ("100%", "完成度")。
    :param horizontal: 横向信息列表，用 kv() / kv_link() 构造。
    :param jumps: 底部跳转列表，用 jump() 构造。
    :param action_url: 整卡点击跳转的 URL。
    """
    card: dict[str, Any] = {"card_type": TEXT_NOTICE, "main_title": main_title(title, desc)}
    if source_desc:
        card["source"] = source(source_desc)
    if emphasis:
        card["emphasis_content"] = {"title": emphasis[0], "desc": emphasis[1]}
    if horizontal:
        card["horizontal_content_list"] = list(horizontal)
    if jumps:
        card["jump_list"] = list(jumps)
    if action_url:
        card["card_action"] = action_jump(action_url)
    card.update(extra)
    return card


def news_notice(
    *,
    title: str,
    desc: str | None = None,
    image_url: str,
    aspect_ratio: float = 2.25,
    source_desc: str | None = None,
    vertical: Sequence[dict[str, Any]] | None = None,
    horizontal: Sequence[dict[str, Any]] | None = None,
    jumps: Sequence[dict[str, Any]] | None = None,
    action_url: str | None = None,
    **extra: Any,
) -> dict[str, Any]:
    """图文展示卡片（带大图）。

    :param image_url: 卡片顶部大图 URL；aspect_ratio 为宽高比（1.3~2.25）。
    :param vertical: 竖向信息列表，元素形如 {"title":..., "desc":...}。
    """
    card: dict[str, Any] = {
        "card_type": NEWS_NOTICE,
        "main_title": main_title(title, desc),
        "card_image": {"url": image_url, "aspect_ratio": aspect_ratio},
    }
    if source_desc:
        card["source"] = source(source_desc)
    if vertical:
        card["vertical_content_list"] = list(vertical)
    if horizontal:
        card["horizontal_content_list"] = list(horizontal)
    if jumps:
        card["jump_list"] = list(jumps)
    if action_url:
        card["card_action"] = action_jump(action_url)
    card.update(extra)
    return card


def button_interaction(
    *,
    title: str,
    task_id: str,
    buttons: Sequence[dict[str, Any]],
    desc: str | None = None,
    horizontal: Sequence[dict[str, Any]] | None = None,
    action_url: str | None = None,
    **extra: Any,
) -> dict[str, Any]:
    """按钮交互卡片。创建与更新共用：更新时传入新的 title/desc/buttons 即可。

    :param task_id: 交互标识；更新卡片时必须与回调收到的 task_id 一致。
    :param buttons: 按钮列表，用 button() 构造。
    """
    card: dict[str, Any] = {
        "card_type": BUTTON_INTERACTION,
        "main_title": main_title(title, desc),
        "button_list": list(buttons),
        "task_id": task_id,
    }
    if horizontal:
        card["horizontal_content_list"] = list(horizontal)
    if action_url:
        card["card_action"] = action_jump(action_url)
    card.update(extra)
    return card


def vote_interaction(
    *,
    title: str,
    task_id: str,
    question_key: str,
    options: Iterable[tuple[str, str]],
    desc: str | None = None,
    mode: int = 0,
    submit_text: str = "提交",
    submit_key: str = "submit_vote",
    checked_ids: Iterable[str] | None = None,
    disable: bool = False,
    **extra: Any,
) -> dict[str, Any]:
    """投票选择卡片。创建与更新共用。

    :param options: [(id, text), ...] 选项列表。
    :param mode: 0 单选 / 1 多选。
    :param checked_ids: 已选中的 option id 集合（更新态回显打勾）。
    :param disable: True 时禁用交互（提交后的只读态）。
    """
    checked = set(checked_ids) if checked_ids is not None else None
    option_list = [
        option(oid, text, checked=(oid in checked) if checked is not None else None)
        for oid, text in options
    ]
    checkbox: dict[str, Any] = {"question_key": question_key, "mode": mode, "option_list": option_list}
    if disable:
        checkbox["disable"] = True
    card: dict[str, Any] = {
        "card_type": VOTE_INTERACTION,
        "main_title": main_title(title, desc),
        "checkbox": checkbox,
        "submit_button": {"text": submit_text, "key": submit_key},
        "task_id": task_id,
    }
    card.update(extra)
    return card


def multiple_interaction(
    *,
    title: str,
    task_id: str,
    selects: Iterable[tuple[str, str, Iterable[tuple[str, str]]]],
    desc: str | None = None,
    submit_text: str = "提交",
    submit_key: str = "submit_multi",
    selected: dict[str, str] | None = None,
    disable: bool = False,
    **extra: Any,
) -> dict[str, Any]:
    """多项选择（多个下拉框）卡片。创建与更新共用。

    :param selects: [(question_key, 标题, [(option_id, text), ...]), ...]。
    :param selected: {question_key: 选中的 option_id}，更新态回显用。
    :param disable: True 时禁用交互（提交后的只读态）。
    """
    select_list: list[dict[str, Any]] = []
    for key, sel_title, opts in selects:
        item: dict[str, Any] = {
            "question_key": key,
            "title": sel_title,
            "option_list": [option(oid, text) for oid, text in opts],
        }
        if disable:
            item["disable"] = True
        if selected and key in selected:
            item["selected_id"] = selected[key]
        select_list.append(item)
    card: dict[str, Any] = {
        "card_type": MULTIPLE_INTERACTION,
        "main_title": main_title(title, desc),
        "select_list": select_list,
        "submit_button": {"text": submit_text, "key": submit_key},
        "task_id": task_id,
    }
    card.update(extra)
    return card
