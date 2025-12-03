# -*- coding: utf-8 -*-
"""
ingest_data.py — 2025-2 수강신청 PDF 완전 통합 파서 최종본

✔ 선택필수교양 / 일반교양 / 교양필수 완전 복원
✔ 상상력 과목군 + Micro Degree 과정 감지
✔ 트랙/학과/단과대 context 유지 (페이지 넘어가도 유지)
✔ page 넘어가도 grade / main_category / course_group 유지
✔ 구분(전필/전선/전기/MD전선/선택필수교양/교양필수/일반교양) 자동 보정
"""

import boto3
import pymysql
import io
import os
import re
import pdfplumber
from typing import List, Dict, Optional
from db import get_connection
from course_parser import parse_course_time

# ============================== 설정 ==============================
S3_BUCKET_NAME = "hong-bucket-25"
S3_FILE_KEY = "2025-2 수강신청책자_강의정보_20250825.pdf"
LOCAL_PDF_PATH = "course.pdf"

IS_LIBERAL = False            # 상상력(예술과 스포츠 상상력 등) 페이지 여부
CURRENT_LIB_GROUP = ""        # 예술과 스포츠 상상력 / Micro Degree 과정 등
CURRENT_GENERAL_LIBERAL = ""  # 일반교양 / 일반선택 / 교양필수 / 선택필수교양
DAY = "월화수목금토일"

FIELD_MAPPING = {
    "grade": ["학년"],
    "category": ["구분"],
    "code": ["과목코드"],
    "name": ["교과목명"],
    "section": ["분반"],
    "professor": ["교수명"],
    "credit": ["학점"],
    "lecture_hours": ["시간"],
    "time_str": ["요일 및 교시"],
    "online_hours": ["온라인강의"],
    "room": ["강의실"],
}

# 페이지 context
PAGE_CTX = {
    "university": "미정",
    "department": "미정",
    "track_major": "미정",
    "grade": "미정",
}

COL_INDEX: Dict[str, int] = {}
last_category_code = ""  # (안 써도 되지만 일단 유지)


# ============================== PDF 로드 ==============================
def get_pdf_data(bucket_name: str, file_key: str) -> Optional[bytes]:
    if os.path.exists(LOCAL_PDF_PATH):
        with open(LOCAL_PDF_PATH, "rb") as f:
            print("로컬 PDF 사용")
            return f.read()

    try:
        s3 = boto3.client("s3")
        obj = s3.get_object(Bucket=bucket_name, Key=file_key)
        print("S3 다운로드 성공")
        return obj["Body"].read()
    except Exception as e:
        print("PDF 로드 실패:", e)
        return None


# ============================== 헤더 감지 ==============================
def find_column_indices(header_row: List[str]) -> Dict[str, int]:
    """
    테이블 헤더에서 각 필드가 몇 번째 컬럼인지 찾는다.
    줄바꿈/공백을 모두 제거하고 매칭.
    """
    cleaned = [re.sub(r"\s+", "", h or "") for h in header_row]
    indices: Dict[str, int] = {}

    for field, keywords in FIELD_MAPPING.items():
        for keyword in keywords:
            kw = keyword.replace(" ", "")
            for i, col in enumerate(cleaned):
                if kw in col:
                    indices[field] = i
                    break

    if "code" not in indices or "name" not in indices or "time_str" not in indices:
        return {}

    return indices


# ============================== 구분(cat_val) 매핑 ==============================
def normalize_major_category(raw: str) -> str:
    """
    '구분' 원시 텍스트를 main_category 로 매핑한다.
    전필/전선/전기 + MD전선 + 선택필수교양/교양필수/일반교양 모두 지원.
    (요구사항: MD전선은 그대로 "MD전선" 으로 저장)
    """
    if not raw:
        return ""

    t = raw.replace("\n", "").replace(" ", "").strip()

    # Micro Degree
    if t.startswith("MD전선"):
        return "MD전선"

    # 전공 계열
    if t.startswith("전필"):
        return "전공필수"
    if t.startswith("전선"):
        return "전공선택"
    if t.startswith("전기"):
        return "전공기초"

    # 선택필수교양 / 선필교양
    if "선택필수교양" in t or t.startswith("선필교양"):
        return "선택필수교양"

    # 교양필수 / 교필
    if "교양필수" in t or t.startswith("교필"):
        return "교양필수"

    # 일반교양
    if "일반교양" in t:
        return "일반교양"

    return ""


# ============================== 멀티라인 row 분리 ==============================
def split_multiline_row_by_time(row, col_index):

    time_idx = col_index["time_str"]
    raw_time = row[time_idx] if time_idx < len(row) else ""

    if raw_time is None:
        raw_time = ""

    time_lines = [t.strip() for t in str(raw_time).split("\n") if t.strip()]

    if str(raw_time).strip() == "":
        single = {}
        for key, idx in col_index.items():
            val = row[idx] if idx < len(row) else ""
            single[key] = (str(val).strip() if val is not None else "")
        return [single]



    count = len(time_lines)

    extracted_cols = {}
    for key, idx in col_index.items():
        val = row[idx] if idx < len(row) else ""
        if val is None:
            val = ""

        lines = [v.strip() for v in str(val).split("\n") if v.strip()]

        # 최소 1개의 값은 유지
        if len(lines) == 0:
            lines = ["-"]

        extracted_cols[key] = lines

    splitted = []

    for i in range(count):
        new_row = {}
        for key, lines in extracted_cols.items():

            # 줄 수가 충분할 때
            if len(lines) >= count:
                val = lines[i]

            # 단일 값(모든 row 공유)
            elif len(lines) == 1:
                val = lines[0]

            # 줄이 부족하면 마지막 줄 반복
            else:
                val = lines[-1]

            new_row[key] = val

        splitted.append(new_row)

    return splitted


# ============================== 시간 문자열 정규화 ==============================
def normalize_time_str(raw: str) -> str:
    if not raw:
        return ""

    # 1) 줄바꿈 → 슬래시로 구분
    s = raw.replace("\n", "/")

    # 2) "요일 + 공백 + 교시" → 공백 제거
    s = re.sub(r'([{}])\s+'.format(DAY), r'\1', s)

    # 3) 전체 공백 제거
    s = re.sub(r'\s+', '', s)

    # 4) ~, –, ／ 등을 모두 "-" 또는 "/"로 통일
    s = s.replace("~", "-").replace("–", "-").replace("／", "/")

    # 5) 요일이 연속될 때 자동 "/" 삽입
    s = re.sub(r'([{}])(?=[{}])'.format(DAY, DAY), r'\1/', s)

    # 6) 중복된 구분자 제거
    s = re.sub(r'[,/]+', '/', s)

    return s.strip("/")


# ============================== PDF Parsing ==============================
def extract_course_info_from_pdf(pdf_bytes: bytes) -> List[Dict]:
    global PAGE_CTX, COL_INDEX, IS_LIBERAL, CURRENT_LIB_GROUP, CURRENT_GENERAL_LIBERAL

    last_main_category = ""
    last_code = ""
    last_name = ""

    pdf = pdfplumber.open(io.BytesIO(pdf_bytes))
    pages = pdf.pages
    results: List[Dict] = []

    # 상상력 / Micro Degree 과목군 (공백 제거 버전으로 매칭)
    LIB_GROUPS = {
        "예술과스포츠상상력": "예술과 스포츠 상상력",
        "인문학적상상력": "인문학적 상상력",
        "사회과학적상상력": "사회과학적 상상력",
        "과학기술상상력": "과학기술 상상력",
        "융합적상상력": "융합적 상상력",
        "한국어집중": "한국어 집중",
        "MicroDegree과정": "Micro Degree 과정",
    }

    for page in pages:
        text = page.extract_text() or ""
        text_clean = text.replace(" ", "").replace("\u3000", "")

        # ------------ 1) 페이지 상단 카테고리(일반교양/일반선택/교양필수/선택필수교양) 감지 ------------
        header_found = False

        if re.search(r"일\s*반\s*교\s*양", text) or "일반교양" in text_clean:
            CURRENT_GENERAL_LIBERAL = "일반교양"
            IS_LIBERAL = False
            CURRENT_LIB_GROUP = ""
            PAGE_CTX["track_major"] = "미정"
            PAGE_CTX["department"] = "미정"
            header_found = True

        elif re.search(r"일\s*반\s*선\s*택", text) or "일반선택" in text_clean:
            CURRENT_GENERAL_LIBERAL = "일반선택"
            IS_LIBERAL = False
            CURRENT_LIB_GROUP = ""
            PAGE_CTX["track_major"] = "미정"
            PAGE_CTX["department"] = "미정"
            header_found = True

        elif re.search(r"교\s*양\s*필\s*수", text) or "교양필수" in text_clean:
            CURRENT_GENERAL_LIBERAL = "교양필수"
            IS_LIBERAL = False
            CURRENT_LIB_GROUP = ""
            PAGE_CTX["track_major"] = "미정"
            PAGE_CTX["department"] = "미정"
            header_found = True

        elif "선택필수교양" in text_clean:
            CURRENT_GENERAL_LIBERAL = "선택필수교양"
            IS_LIBERAL = False
            CURRENT_LIB_GROUP = ""
            PAGE_CTX["track_major"] = "미정"
            PAGE_CTX["department"] = "미정"
            header_found = True

        # 헤더가 전혀 없으면 이전 페이지 값 유지 (reset 하지 않음)

        # ------------ 2) 상상력 / Micro Degree 과목군 감지 ------------
        detected_group = None
        for key, val in LIB_GROUPS.items():
            if key in text_clean:
                detected_group = val
                break

        if detected_group:
            if detected_group == "Micro Degree 과정":
                # Micro Degree는 선택필수교양처럼 취급하지만 IS_LIBERAL=False (별도)
                IS_LIBERAL = False
                CURRENT_LIB_GROUP = detected_group
                # 일반 교양 카테고리는 비움 (구분 컬럼 + 문맥으로 결정)
                CURRENT_GENERAL_LIBERAL = ""
            else:
                # 상상력 과목군 (예술과 스포츠 상상력 등)
                IS_LIBERAL = True
                CURRENT_LIB_GROUP = detected_group
                # 상상력 페이지에서는 별도 교양 카테고리 텍스트는 없을 수 있으므로
                # CURRENT_GENERAL_LIBERAL 은 그대로 두거나 별도로 판정
            PAGE_CTX["track_major"] = "미정"
            PAGE_CTX["department"] = "미정"
        else:
            # 새로운 과목군 텍스트는 없지만 "OO대학" 등장 → 전공 페이지로 전환
            if re.search(r"[가-힣A-Za-z]+대학", text):
                IS_LIBERAL = False
                CURRENT_LIB_GROUP = ""
                # 전공 페이지이므로 교양 카테고리도 없다고 보고 초기화
                CURRENT_GENERAL_LIBERAL = ""

        # ------------ 3) 학부/학과/트랙 감지 ------------
        dept = re.search(r"([가-힣A-Za-z0-9]+학부|[가-힣A-Za-z0-9]+학과|[가-힣A-Za-z0-9]+트랙)", text)
        if dept:
            name = dept.group(1)
            if "트랙" in name:
                PAGE_CTX["track_major"] = name
            elif "학부" in name or "학과" in name:
                PAGE_CTX["department"] = name

        # ------------ 4) 테이블 파싱 ------------
        tables = page.extract_tables() or []
        for table in tables:
            if not table or len(table) < 2:
                continue

            # 교양필수 특수 헤더(2줄 헤더) 처리
            if CURRENT_GENERAL_LIBERAL == "교양필수":
                # table[1]이 빈 줄이면 → table[0]만 헤더
                if table[1] and all((c is None or str(c).strip() == "") for c in table[1]):
                    real_header = table[0]
                    start = 2
                else:
                    # table[0]과 table[1]을 합친 헤더
                    merged_header = [
                        ((h1 or "") + " " + (h2 or "")).strip()
                        for h1, h2 in zip(table[0], table[1])
                    ]
                    real_header = merged_header
                    start = 2

                idx = find_column_indices(real_header)
                if not idx:
                    continue
                COL_INDEX = idx
            else:
                # 일반 전공/일반 교양 처리
                header = table[0]
                idx = find_column_indices(header)

                if idx:
                    COL_INDEX = idx
                    start = 1
                else:
                    # 이 테이블은 헤더 생략된 연속 테이블 → 이전 COL_INDEX 사용
                    if not COL_INDEX:
                        continue
                    start = 0

            last_grade_in_table = PAGE_CTX.get("grade", "미정")

            # ------------ 행(row) 단위 파싱 ------------
            for row in table[start:]:
                grade_idx = COL_INDEX.get("grade", -1)
                if 0 <= grade_idx < len(row):
                    g_val = row[grade_idx]
                    raw_grade = str(g_val).strip() if g_val is not None else ""
                else:
                    raw_grade = ""

                if raw_grade not in ["", "-", None, ""]:
                    PAGE_CTX["grade"] = raw_grade
                    last_grade_in_table = raw_grade

                # 여러 줄 분할 처리
                splitted_rows = split_multiline_row_by_time(row, COL_INDEX)

                for srow in splitted_rows:
                    # 값 꺼내기 함수
                    def get(f):
                        return (srow.get(f, "") or "").strip()

                    grade_value = last_grade_in_table

                    # 과목 코드 / 이름 병합 셀 처리
                    code_raw = get("code")
                    name_raw = get("name")

                    if code_raw in ["", "-"]:
                        code = last_code
                    else:
                        code = code_raw
                        last_code = code

                    if name_raw in ["", "-"]:
                        name = last_name
                    else:
                        name = name_raw
                        last_name = name

                    if not code:
                        continue  # 진짜 코드가 없으면 스킵

                    # ================== main_category 최종 결정 ==================
                    raw_category = get("category")
                    raw_category_clean = raw_category.replace(" ", "").replace("\n", "")

                    if raw_category_clean == "" or raw_category_clean == "-":
                        # ---- 구분 셀이 비어 있을 때 우선순위 ----
                        # 1) 선택필수교양 페이지 또는 상상력 그룹이면 무조건 선택필수교양
                        if CURRENT_GENERAL_LIBERAL == "선택필수교양" or (
                            IS_LIBERAL and CURRENT_LIB_GROUP != "Micro Degree 과정"
                        ):
                            main_category = "선택필수교양"

                        # 2) 일반교양 / 일반선택 / 교양필수 페이지이면 그 값 사용
                        elif CURRENT_GENERAL_LIBERAL:
                            main_category = CURRENT_GENERAL_LIBERAL

                        # 3) 그래도 없으면 이전 main_category 이어받기
                        elif last_main_category:
                            main_category = last_main_category

                        # 4) 아무 정보도 없을 때
                        else:
                            main_category = "미정"

                    else:
                        # ---- 새 구분이 실제로 적혀 있는 경우 ----
                        major_cat = normalize_major_category(raw_category_clean)

                        if major_cat:
                            main_category = major_cat
                        elif CURRENT_GENERAL_LIBERAL:
                            main_category = CURRENT_GENERAL_LIBERAL
                        elif IS_LIBERAL and CURRENT_LIB_GROUP != "Micro Degree 과정":
                            main_category = "선택필수교양"
                        else:
                            main_category = "미정"

                        # 새로운 main_category는 다음 행들을 위해 기억
                        last_main_category = main_category


                    # ================== 요일/교시 복원 ==================
                    raw_time = get("time_str") or ""
                    time_str_clean = normalize_time_str(raw_time)

                    # 요일 붙어있는 경우 자동 분리
                    DAY_CHARS = "월화수목금토일"
                    fixed = []
                    s = time_str_clean
                    i = 0
                    while i < len(s):
                        if i + 1 < len(s) and s[i] in DAY_CHARS and s[i + 1] in DAY_CHARS:
                            fixed.append(s[i] + "/")
                            i += 1
                        else:
                            fixed.append(s[i])
                            i += 1
                    time_str_clean = "".join(fixed)

                    # ================== course_group 결정 ==================
                    # 상상력 과목군(IS_LIBERAL=True) 또는 Micro Degree 과정(CURRENT_LIB_GROUP) 은 course_group 유지
                    if IS_LIBERAL or CURRENT_LIB_GROUP == "Micro Degree 과정":
                        course_group_value = CURRENT_LIB_GROUP
                    else:
                        course_group_value = "미정"

                    # ================== 결과 저장 ==================
                    result = {
                        "code": code,
                        "name": name,
                        "main_category": main_category,
                        "course_group": course_group_value,
                        "university": PAGE_CTX["university"],
                        "department": PAGE_CTX["department"],
                        "track_major": PAGE_CTX["track_major"],
                        "grade": grade_value,
                        "section": get("section") or "000",
                        "credit": get("credit"),
                        "lecture_hours": get("lecture_hours"),
                        "time_str": time_str_clean,
                        "room": get("room"),
                        "professor": get("professor"),
                        "online_hours": get("online_hours") or "-",
                        "page": page.page_number,
                        "cross_enrollment_type": "",
                    }

                    results.append(result)

    print(f"총 {len(results)}개 강의 파싱 완료")
    return results


# ============================== DB INSERT ==============================
def insert_course_data(course_list: List[Dict]):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SET FOREIGN_KEY_CHECKS = 0;")
            cur.execute("TRUNCATE TABLE schedules")
            cur.execute("TRUNCATE TABLE courses")
            cur.execute("SET FOREIGN_KEY_CHECKS = 1;")
            conn.commit()

        with conn.cursor() as cur:
            sql_course = """
                INSERT INTO courses
                (code, name, main_category, course_group, university, department,
                 track_major, grade, section, credit, lecture_hours, room,
                 professor, page, cross_enrollment_type, online_hours)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """

            sql_sched = """
                INSERT INTO schedules (course_id, day, start_time, end_time, room)
                VALUES (%s,%s,%s,%s,%s)
            """

            for course in course_list:
                time_str = course.pop("time_str", "")
                parsed = parse_course_time(time_str)

                values = (
                    course["code"], course["name"], course["main_category"],
                    course["course_group"], course["university"], course["department"],
                    course["track_major"], course["grade"], course["section"],
                    course["credit"], course["lecture_hours"], course["room"],
                    course["professor"], course["page"], course["cross_enrollment_type"],
                    course["online_hours"]
                )

                cur.execute(sql_course, values)
                cid = cur.lastrowid

                if not parsed:
                    parsed = [
                        {"day": "TBD", "start_time": "00:00", "end_time": "00:00"}
                    ]

                for t in parsed:
                    room_value = (course.get("room") or "").strip()
                    if room_value in ["", "-", None]:
                        room_value = None
                    cur.execute(
                        sql_sched,
                        (cid, t["day"], t["start_time"], t["end_time"], room_value),
                    )

            conn.commit()
            print("DB 저장 완료")

    finally:
        conn.close()


# ============================== main ==============================
if __name__ == "__main__":
    data = get_pdf_data(S3_BUCKET_NAME, S3_FILE_KEY)
    if not data:
        print("PDF 불러오기 실패")
        exit()

    courses = extract_course_info_from_pdf(data)
    insert_course_data(courses)
