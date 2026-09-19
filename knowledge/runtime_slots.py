"""通用业务槽位归一化与高置信度参数抽取。"""

from __future__ import annotations

import re
import unicodedata
from typing import Any


NUMBER = r"\d+(?:\.\d+)?"
MOBILE_PATTERN = re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")
BANDWIDTH_PATTERN = re.compile(
    rf"({NUMBER})\s*(gbps|mbps|g(?=\s*(?:宽带|带宽))|m(?=\s*(?:宽带|带宽))|兆(?=\s*(?:宽带|带宽)))\s*(?:宽带|带宽)?",
    re.IGNORECASE,
)
DATA_PATTERN = re.compile(rf"({NUMBER})\s*(tb|gb|g|mb)(?=流量|套餐|包|\b)", re.IGNORECASE)
AMOUNT_PATTERN = re.compile(rf"({NUMBER})\s*(?:元|块钱|人民币)", re.IGNORECASE)
VOICE_PATTERN = re.compile(
    r"(?:语音|通话)(?:时长|分钟数)?\D{0,4}(\d+)\s*分钟|"
    r"(\d+)\s*分钟(?:语音|通话)",
)
SMS_PATTERN = re.compile(r"(\d+)\s*条(?:短信|彩信)")
CONTRACT_PATTERN = re.compile(
    r"(?:合约|合同|协议|契约)(?:期|时长|期限)?\D{0,4}(\d+)\s*(年|个月|月)|"
    r"(\d+)\s*(年|个月|月)(?:合约|合同|协议|契约)",
)
QUANTITY_PATTERN = re.compile(r"(\d+)\s*(?:张|个|部)(?:手机卡|电话卡|SIM卡|号码|套餐|流量包)", re.IGNORECASE)
EFFECTIVE_TIME_PATTERN = re.compile(
    r"立即生效|马上生效|实时生效|当月生效|本月生效|次月生效|下月生效|下个月生效|"
    r"\d{4}[年/-]\d{1,2}[月/-]\d{1,2}日?(?:生效)?|\d{1,2}月\d{1,2}日(?:生效)?"
)
DATE_TIME_PATTERN = re.compile(
    r"今天|明天|后天|本周|下周|本月|下月|"
    r"\d{4}[年/-]\d{1,2}[月/-]\d{1,2}日?|\d{1,2}月\d{1,2}日"
)
NETWORK_TYPE_PATTERN = re.compile(r"(?<![a-z0-9])(?:2g|3g|4g|5g)(?![a-z0-9])", re.IGNORECASE)
ORDER_ID_PATTERN = re.compile(r"订单(?:号|编号)?[：:\s]*([a-zA-Z0-9_-]+)", re.IGNORECASE)
WORK_ORDER_ID_PATTERN = re.compile(r"工单(?:号|编号)?[：:\s]*([a-zA-Z0-9_-]+)", re.IGNORECASE)
BROADBAND_ACCOUNT_PATTERN = re.compile(r"宽带(?:账号|账户)[：:\s]*([a-zA-Z0-9_-]+)", re.IGNORECASE)
PRODUCT_ID_PATTERN = re.compile(r"产品(?:号|编号|ID)[：:\s]*([a-zA-Z0-9_-]+)", re.IGNORECASE)

REGIONS = (
    "北京", "上海", "天津", "重庆", "河北", "山西", "辽宁", "吉林", "黑龙江",
    "江苏", "浙江", "安徽", "福建", "江西", "山东", "河南", "湖北", "湖南",
    "广东", "海南", "四川", "贵州", "云南", "陕西", "甘肃", "青海", "台湾",
    "内蒙古", "广西", "西藏", "宁夏", "新疆", "香港", "澳门",
)
REGION_PATTERN = re.compile(rf"({'|'.join(REGIONS)})(?:省|市|自治区|特别行政区)?")

CHANNEL_PATTERNS = {
    "线上": re.compile(r"线上|网上|在线"),
    "营业厅": re.compile(r"营业厅|线下门店|门店"),
    "手机营业厅": re.compile(r"手机营业厅|移动app|移动APP"),
    "电话客服": re.compile(r"电话客服|10086"),
}

SLOT_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (WORK_ORDER_ID_PATTERN, "工单编号参数"),
    (ORDER_ID_PATTERN, "订单编号参数"),
    (BROADBAND_ACCOUNT_PATTERN, "宽带账户参数"),
    (PRODUCT_ID_PATTERN, "产品编号参数"),
    (MOBILE_PATTERN, "手机号码参数"),
    (CONTRACT_PATTERN, "合约期限参数"),
    (VOICE_PATTERN, "语音分钟参数"),
    (SMS_PATTERN, "短信数量参数"),
    (QUANTITY_PATTERN, "办理数量参数"),
    (BANDWIDTH_PATTERN, "宽带速率参数"),
    (DATA_PATTERN, "流量规格参数"),
    (AMOUNT_PATTERN, "金额参数"),
    (EFFECTIVE_TIME_PATTERN, "生效时间参数"),
    (DATE_TIME_PATTERN, "日期时间参数"),
    (NETWORK_TYPE_PATTERN, "网络制式参数"),
    (REGION_PATTERN, "地区参数"),
)

FILLER_PATTERN = re.compile(r"请问|请|麻烦|劳驾|帮我|给我|我想要|我想|我要|想要|能不能|可以|一下")
ACTION_NORMALIZATIONS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"开通|订购|购买|申请|办理"), "办理"),
    (re.compile(r"取消|退订|关闭|撤销"), "取消"),
    (re.compile(r"查看|查一下|查查|查询|查"), "查询"),
    (re.compile(r"更换|调整|改成|变更|修改"), "变更"),
    (re.compile(r"销号|销户|注销"), "注销"),
)
NON_WORD_PATTERN = re.compile(r"[^0-9a-zA-Z\u4e00-\u9fff]+")


def parameterize_utterance(text: str) -> str:
    """生成与具体参数值无关、保留业务动作和对象的匹配模式。"""

    normalized = unicodedata.normalize("NFKC", text).lower()
    for pattern, replacement in SLOT_PATTERNS:
        normalized = pattern.sub(replacement, normalized)
    for pattern, replacement in ACTION_NORMALIZATIONS:
        normalized = pattern.sub(replacement, normalized)
    normalized = FILLER_PATTERN.sub("", normalized)
    return NON_WORD_PATTERN.sub("", normalized)


def _first_number(match: re.Match[str] | None) -> float | None:
    if match is None:
        return None
    for value in match.groups():
        if value and re.fullmatch(NUMBER, value):
            return float(value)
    return None


def extract_runtime_slots(text: str) -> dict[str, Any]:
    """提取能够从原文确定的公共业务参数，不推断未表达字段。"""

    slots: dict[str, Any] = {}
    amount = _first_number(AMOUNT_PATTERN.search(text))
    if amount is not None:
        slots["amount_yuan"] = amount

    data_match = DATA_PATTERN.search(text)
    if data_match:
        value = float(data_match.group(1))
        unit = data_match.group(2).lower()
        slots["data_gb"] = value * 1024 if unit == "tb" else value / 1024 if unit == "mb" else value

    bandwidth_match = BANDWIDTH_PATTERN.search(text)
    if bandwidth_match and re.search(r"宽带|带宽|bps", bandwidth_match.group(0), re.IGNORECASE):
        value = float(bandwidth_match.group(1))
        unit = bandwidth_match.group(2).lower()
        slots["bandwidth_mbps"] = round(value * 1000 if unit in {"g", "gbps"} else value)

    voice_match = VOICE_PATTERN.search(text)
    if voice_match:
        slots["voice_minutes"] = int(next(value for value in voice_match.groups() if value))
    sms_match = SMS_PATTERN.search(text)
    if sms_match:
        slots["sms_count"] = int(sms_match.group(1))
    quantity_match = QUANTITY_PATTERN.search(text)
    if quantity_match:
        slots["quantity"] = int(quantity_match.group(1))

    contract_match = CONTRACT_PATTERN.search(text)
    if contract_match:
        groups = contract_match.groups()
        value = int(groups[0] or groups[2])
        unit = groups[1] or groups[3]
        slots["contract_months"] = value * 12 if unit == "年" else value

    effective_match = EFFECTIVE_TIME_PATTERN.search(text)
    if effective_match:
        slots["effective_time"] = effective_match.group(0)
    elif date_match := DATE_TIME_PATTERN.search(text):
        slots["occurrence_time"] = date_match.group(0)

    if mobile_match := MOBILE_PATTERN.search(text):
        slots["mobile_number"] = mobile_match.group(0)
        if re.search(r"联系(?:电话|手机|号码)|联系电话|联系人", text):
            slots["contact_mobile"] = mobile_match.group(0)
    for name, pattern in (
        ("work_order_id", WORK_ORDER_ID_PATTERN),
        ("order_id", ORDER_ID_PATTERN),
        ("broadband_account", BROADBAND_ACCOUNT_PATTERN),
        ("product_id", PRODUCT_ID_PATTERN),
    ):
        if match := pattern.search(text):
            slots[name] = match.group(1)

    if network_match := NETWORK_TYPE_PATTERN.search(text):
        slots["network_type"] = network_match.group(0).upper()
    if region_match := REGION_PATTERN.search(text):
        region = region_match.group(1)
        key = "city" if region in {"北京", "上海", "天津", "重庆", "香港", "澳门"} else "province"
        slots[key] = region
    for channel, pattern in CHANNEL_PATTERNS.items():
        if pattern.search(text):
            slots["service_channel"] = channel
            break
    return slots
