# -*- coding: utf-8 -*-
"""Correct imported clinic details without rewriting clinical advice or URL slugs."""
import re

from site_info import SITE


# Match complete addresses before any city/street-name substitutions. This also
# recognizes the partially converted addresses in the previously imported data.
_ADDRESS = re.compile(
    r"(?:(?:경기도|충북|충청북도)\s*)?"
    r"(?:(?:파주시|청주시\s*청원구)\s*)?"
    r"(?:(?:오창읍|운정신도시)\s*)?(?:(?:주성리|동패동)\s*)?"
    r"(?:청석로|2산단로)\s*(?:115|132)\s*,?\s*(?:건물\s*)?"
    r"(?:5층(?:\s*,?\s*507호)?|301\s*[·,~～]\s*302호|부민빌딩\s*3층|3층)"
    r"(?:\s*\((?:오창읍\s*)?(?:주성리|동패동)\))?"
)
_PAREN_ADDRESS = re.compile(
    r"(?:오창읍|운정신도시)(?:\s*중심)?\("
    r"(?:주성리|동패동)\s*(?:청석로|2산단로)"
    r"(?:\s*(?:115|132)\s*,?\s*(?:5층(?:\s*507호)?|3층))?\)"
)
_AREA = r"(?:청주\s+)?(?:오창1·2·3동|오창읍|오창동|오창|야당동|야당|와동동|주성리|각리|양청리|청주(?:\s*북부)?)"
_AREA_LIST = re.compile(rf"{_AREA}(?:\s*[,·]\s*{_AREA})+")
_FOREIGN_AREA = re.compile(r"야당|와동동|오창1·2·3동|오창동")


def _repair_area_list(match):
    value = match.group()
    areas = re.split(r"\s*[,·]\s*", value)
    if (_FOREIGN_AREA.search(value) or len(areas) != len(set(areas))
            or "오창·오창" in value or "청주·청주" in value):
        return "오창·청주"
    return value


def normalize_clinic_details(text):
    """Repair only known imported location/contact/opening-hours mistakes.

    This function is for imported condition/column content, not staff careers
    or the network directory, where references to other branches are valid.
    """
    if not isinstance(text, str):
        return text
    text = _PAREN_ADDRESS.sub(SITE["address"], text)
    text = _ADDRESS.sub(SITE["address"], text)
    text = re.sub(r"경기도(?=\s*청주시)", "충북", text)
    text = re.sub(r"2산단로\s*115(?:\s*건물)?", "2산단로 132, 부민빌딩 3층", text)

    # The imported station names do not describe access to the Ochang clinic.
    text = text.replace("오창역이나 야당역 근처에서", "오창에서")
    text = text.replace("오창역이나 야당역에서", "출퇴근길 대중교통에서")
    text = text.replace("오창역, 야당역, 오창 방면에서", "오창 생활권에서")
    text = text.replace("오창역·야당역", "오창읍")
    text = text.replace("오창역", "오창").replace("야당역", "오창")

    text = re.sub(r"(?:청주\s*)?오창(?:읍)?(?:이)?[나와]\s*(?:야당|오창)", "오창·청주", text)
    text = re.sub(r"야당(?:동)?(?:이나\s*오창)?", "오창", text)
    text = _AREA_LIST.sub(_repair_area_list, text)
    text = re.sub(r"오창(?:\s+오창)+", "오창", text)
    text = text.replace("청주 오창읍와", "청주 오창읍과").replace("오창읍와", "오창읍과")
    text = text.replace("각리은", "각리는")
    text = text.replace("오창·청주은 물론", "오창·청주는 물론")
    text = text.replace("청주·청주에서 서울로 출퇴근하시는 분들", "출퇴근 시간이 긴 분들")
    text = text.replace("서울·청주으로 출퇴근하시는 분들", "출퇴근 시간이 긴 분들")
    text = text.replace("오창·청주에서 서울로 출퇴근하시는 분들", "출퇴근 시간이 긴 분들")

    # Remove transplanted claims about Seoul/Paju commuting routes. Retain the
    # clinical scenario (long journeys, sitting posture, fatigue) without
    # claiming that these routes describe the clinic's local catchment area.
    text = re.sub(r"(?:청주\s*)?오창(?:읍)?처럼 서울로 (?:장거리 )?출퇴근하는 분이 많은 지역에서는",
                  "장거리 출퇴근으로 이동 시간이 긴 분들은", text)
    text = re.sub(r"(?:청주\s*)?오창(?:읍)?처럼 서울(?:로)? (?:장거리 )?출퇴근(?:하는 분들은| 시간이 긴 지역에서는)",
                  "장거리 출퇴근을 하는 분들은", text)
    text = text.replace("청주 오창읍는 서울 출퇴근 시간이 긴 편이라", "출퇴근 시간이 긴 분들은")
    text = re.sub(r"(?:청주\s*)?오창(?:읍)?에서 서울로 (?:장거리 |장시간 )?출퇴근", "장거리 출퇴근", text)
    text = text.replace("청주에서 서울로 출퇴근", "장거리 출퇴근")
    text = text.replace("서울까지 출퇴근하는데", "장거리 출퇴근을 하는데")
    text = text.replace("청주 오창에서 서울이나 청주으로 오가는 길처럼", "출퇴근길처럼")
    text = text.replace("오창읍에서 서울 방면으로 오가는 길이 길어지면", "출퇴근 이동 시간이 길어지면")
    text = text.replace("서울 출퇴근 시간이 길어", "출퇴근 시간이 길어")
    text = text.replace("자유로나 서울오창고속도로를 자주 타는 청주 거주자분들이 자주 말씀하시는 장면입니다.",
                        "장거리 운전을 하는 분들이 겪을 수 있는 장면입니다.")
    text = text.replace("자유로나 지하철에서", "버스나 다른 대중교통에서")
    for old, new in (
        ("청주 오창에서 시술받는 병원은 서울인데", "시술받는 병원은 다른 지역인데"),
        ("청주 오창 지역은 서울로 통근하는 분이 많아", "통근 시간이 긴 분들은"),
        ("청주 오창 일대에서 서울로 출퇴근하시는 분들은", "장거리 출퇴근을 하시는 분들은"),
        ("청주 오창읍처럼 서울 방향 출근이 많은 지역은 가족 전체의 기상 시각이 이른 편입니다.",
         "부모의 출근 시간이 이르면 가족 전체의 기상 시각도 빨라질 수 있습니다."),
        ("청주 오창처럼 서울 방향 통근이 긴 지역에서는", "장거리 통근을 하는 경우에는"),
        ("청주 오창에서 서울 방면으로 출퇴근하시는 분들은", "장거리 출퇴근을 하시는 분들은"),
        ("청주 오창은 서울로 출퇴근하는 분이 많아", "출퇴근 시간이 길면"),
        ("자유로나 경의중앙선 인근 도로를 오가며 출퇴근하는 분들이 자주 말씀하시는 증상입니다.",
         "장거리 운전을 하는 분들이 겪을 수 있는 증상입니다."),
        ("자유로나 지방도를 이용해 서울로 출퇴근하는 청주 오창 거주자라면", "장거리 운전으로 출퇴근하는 분이라면"),
        ("청주 오창 진료권은 서울 출퇴근을 하시는 분이 많아,", "장거리 출퇴근을 하는 경우,"),
        ("청주 오창처럼 서울 출퇴근 거리가 긴 생활권에서는", "출퇴근 거리가 긴 경우에는"),
        ("청주 오창에서 서울 방향으로 출퇴근하면", "장거리 운전으로 출퇴근하면"),
        ("청주에서 서울 방향으로 출퇴근하며", "장거리 출퇴근을 하며"),
        ("청주처럼 서울 출퇴근 시간이 긴 지역은", "출퇴근 시간이 긴 경우에는"),
        ("오창·청주에서 서울 방향으로 장거리 출퇴근을 하시는 경우도", "장거리 출퇴근을 하시는 경우도"),
        ("자유로나 제2자유로를 오래 타는", "정체가 잦은 구간을 오래 운전하는"),
        ("자유로나 제2자유로에서", "정체가 잦은 출퇴근길에서"),
        ("자유로나 청주 시내 출퇴근길처럼", "청주 시내 출퇴근길처럼"),
        ("자유로나 청주 시내 구간처럼", "출퇴근길의 익숙한 도로처럼"),
        ("자유로나", "출퇴근 도로나"),
        ("자유로에서", "출퇴근길에서"),
        ("자유로와 국도를", "고속도로와 국도를"),
        ("자유로 출근길에서", "출근길에서"),
        ("자유로 출퇴근", "장거리 출퇴근"),
        ("자유로를 달리는 출퇴근길", "운전으로 이동하는 출퇴근길"),
        ("오창와", "오창과"),
    ):
        text = text.replace(old, new)

    # Search-topic lists can contain duplicates after removing an old locality.
    if " · " in text:
        text = " · ".join(dict.fromkeys(text.split(" · ")))

    # Scope the correction to the clinic's weekday opening time; a patient's
    # bedtime or medication schedule mentioning 10시 must remain untouched.
    if any(marker in text for marker in ("한의원", "2산단로", "청석로", "진료시간", "진료합니다")):
        text = re.sub(r"평일(은|에는)?\s*(?:오전\s*)?10시부터\s*20시까지",
                      r"평일\1 09:30부터 20:00까지", text)
        text = re.sub(r"평일(은|에는)?\s*10:00\s*[-~–]\s*20:00",
                      r"평일\1 09:30~20:00", text)
        text = text.replace("점심시간 13:00 - 14:30", "점심시간 13:00 - 14:00")
    return text


def normalize_imported_content(value):
    if isinstance(value, str):
        return normalize_clinic_details(value)
    if isinstance(value, list):
        return [normalize_imported_content(item) for item in value]
    if isinstance(value, dict):
        # URL identities and related-page references must not change.
        return {key: item if key in ("slug", "related") else normalize_imported_content(item)
                for key, item in value.items()}
    return value
