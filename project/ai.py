# -*- coding: utf-8 -*-
"""
ai.py - 2025-2 수강신청 AI 도우미 최종 안정+버그픽스 버전

✔ LLM Intent 분석 + 강력한 프롬프트 가이드
✔ 선택필수교양 + 요일 + 시간 완전 지원
✔ main_category / track_major 절대 혼동 금지
✔ DB 기반 답변 ONLY (RAG 없음)
✔ keyword 공백 제거로 인한 매칭 실패 해결
✔ 교수 검색 시 LIKE '%%'로 전체 과목 나오는 문제 방지
✔ 검색 조건이 전혀 없을 때는 빈 결과 반환
"""

import pymysql
import boto3
import json
import re
from db import get_connection

# Bedrock LLM 클라이언트
llm = boto3.client("bedrock-runtime", region_name="us-east-1")

# 요일 매핑
DAY_MAP = {
    "월": "MON",
    "화": "TUE",
    "수": "WED",
    "목": "THU",
    "금": "FRI",
    "토": "SAT",
    "일": "SUN"
    
}

# LLM이 반드시 맞춰줘야 하는 필터 기본 구조
DEFAULT_FILTERS = {
    "keyword": "",
    "track_major": "",
    "department": "",
    "university": "",
    "main_category": "",
    "grade": "",
    "professor": "",
    "day": "",
    "time_start": "",
    "time_end": "",
    "room": "",
    "section": "",
    "code": "",
    "credit": "",
    "lecture_hours": "",
    "online_hours": ""
}

VALID_INTENTS = {
    "course_to_professor",
    "professor_to_course",
    "search_by_filters",
    "unknown"
}


# ============================================================
# 1) LLM → intent + filters JSON
# ============================================================
def analyze_question_with_ai(question: str):
    """
    사용자의 자연어 질문을 LLM에 보내서
    intent + filters 형태의 JSON 구조로 변환한다.
    """

    prompt = f"""
당신은 수강신청 도우미이며,
자연어 질문에서 'DB 검색에 필요한 조건만' JSON으로 추출해야 합니다.

⚠️ 절대 규칙(반드시 지켜라):
- track_major(트랙명) ≠ main_category(전공필수/전공선택/전공기초/선택필수교양)
- main_category 는 오직 이 4가지만 사용:
    ["전공필수", "전공선택", "전공기초", "선택필수교양"]
- 선택필수교양은 track_major 가 아니라 main_category 다.
- "온라인수업", "온라인 강의", "비대면", "동영상 강의" 등의 표현이 있으면 반드시 online_hours 필드에 매핑한다.
- 사용자가 '온라인수업 몇 시간' 또는 '온라인 몇 H' 라고 말하면 online_hours에 숫자나 H포함 문자열을 넣는다.
- lecture_hours는 오프라인 강의 시간이며, '온라인'이라는 단어가 없는 경우에만 사용한다.
- 온라인수업이 언급된 경우, time 표현(예: 1H, 1.5H, 3H, 3시간 등)은 반드시 online_hours 필드에 넣는다.
- 온라인 수업이 3H의 경우 강의실은 - 로 시간은 미정으로 되어있어야 한다.
- 요일(day)은 "월/화/수/목/금" 한 글자로만.
- 시간(time)은 반드시 "HH:MM" 형식으로 분리:
  - "12:00 이후" (after 12:00) → time_start="12:00", time_end=""
  - "12:00 이전" (before 12:00) → time_start="", time_end="12:00"
  - 시간 범위 (e.g., 10:00 to 14:00) → time_start="10:00", time_end="14:00"
- JSON 이외의 텍스트 출력 금지.

지원 intent:
- "course_to_professor"   → 특정 과목의 담당 교수
- "professor_to_course"   → 특정 교수가 담당하는 과목
- "search_by_filters"     → main_category/track_major/학년/day/time 등 복합 조건 검색
- "unknown"

질문: "{question}"

JSON ONLY:
{{
  "intent": "",
  "filters": {{
    "keyword": "",
    "track_major": "",
    "department": "",
    "university": "",
    "main_category": "",
    "grade": "",
    "professor": "",
    "day": "",
    "time_start": "",
    "time_end": "",
    "room": "",
    "section": "",
    "code": "",
    "credit": "",
    "lecture_hours": "",
    "online_hours": ""
  }}
}}
"""

    try:
        res = llm.invoke_model(
            modelId="amazon.nova-lite-v1:0",
            body=json.dumps({
                "inferenceConfig": {"max_new_tokens": 250},
                "messages": [{"role": "user", "content": [{"text": prompt}]}]
            })
        )
        out = json.loads(res["body"].read())
        text = out["output"]["message"]["content"][0]["text"].strip()

        # ```json ... ``` 형태로 감싸져 올 수 있으므로 제거
        if text.startswith("```"):
            text = text.replace("```json", "").replace("```", "").strip()

        parsed = json.loads(text)

        # ---------- 안전망: intent / filters 구조 정리 ----------
        intent = parsed.get("intent", "") or "unknown"
        if intent not in VALID_INTENTS:
            intent = "unknown"

        filters = parsed.get("filters", {}) or {}
        # 빠진 키 채워넣기
        cleaned_filters = {}
        for k, default_v in DEFAULT_FILTERS.items():
            v = filters.get(k, default_v)
            # None → "" 통일
            cleaned_filters[k] = "" if v is None else str(v)
        parsed["intent"] = intent
        parsed["filters"] = cleaned_filters

        return parsed

    except Exception as e:
        print("LLM 분석 오류:", e)
        # LLM 실패 시 전체 질문을 keyword로 사용하는 unknown intent
        return {
            "intent": "unknown",
            "filters": {
                "keyword": question,
                "track_major": "",
                "department": "",
                "university": "",
                "main_category": "",
                "grade": "",
                "professor": "",
                "day": "",
                "time_start": "",
                "time_end": "",
                "room": "",
                "section": "",
                "code": "",
                "credit": "",
                "lecture_hours": "",
                "online_hours": ""
            }
        }


def fix_intent(intent, filters):
    """
    intent를 완전히 갈아엎는 게 아니라,
    명백한 경우만 살짝 보정한다.
    """
    prof = (filters.get("professor") or "").strip()
    kw = (filters.get("keyword") or "").replace(" ", "")
    code = (filters.get("code") or "").strip()

    # 교수명이 명확히 있으면 교수→과목 intent로 고정
    if prof and len(prof) >= 2:
        return "professor_to_course"

    # 코드가 지정되어 있으면 필터 검색으로 고정
    if code:
        return "search_by_filters"

    # 그 외에는 LLM이 준 intent 그대로 사용
    return intent



def search_courses(intent, filters):
    """
    intent + filters 정보를 바탕으로
    courses / schedules 테이블에서 과목을 검색한다.

    - 교수 / 트랙 / main_category / 학년 / 요일 / 시간 등은
      값이 있으면 모두 AND 조건으로 건다.
    - keyword는 intent에 따라 사용 방식만 달라진다.
    """

    conn = get_connection()
    try:
        with conn.cursor(pymysql.cursors.DictCursor) as cur:

            sql = """
                SELECT
                    c.id, c.code, c.name, c.professor,
                    c.main_category, c.track_major,
                    c.department, c.university,
                    c.grade, c.room, c.credit, c.section, c.lecture_hours, c.online_hours,
                    s.day, s.start_time, s.end_time
                FROM courses c
                LEFT JOIN schedules s ON c.id = s.course_id
            """

            cond = []
            param = []

            # ====== 필터 값 정리 ======
            kw         = (filters.get("keyword")      or "").strip()
            prof       = (filters.get("professor")    or "").strip()
            track      = (filters.get("track_major")  or "").strip()
            dept       = (filters.get("department")   or "").strip()
            univ       = (filters.get("university")   or "").strip()
            main_cat   = (filters.get("main_category")or "").strip()
            grade      = (filters.get("grade")        or "").strip()
            day        = (filters.get("day")          or "").strip()
            time_start = (filters.get("time_start")   or "").strip()
            time_end   = (filters.get("time_end")     or "").strip()
            room       = (filters.get("room")         or "").strip()
            section    = (filters.get("section")      or "").strip()
            code       = (filters.get("code")         or "").strip()
            credit     = (filters.get("credit")       or "").strip()
            lecture_hours = (filters.get("lecture_hours") or "").strip()
            online_hours  = (filters.get("online_hours")  or "").strip()

            # ====== “강한” 필터들은 intent와 상관없이 항상 AND ======

            if prof:
                cond.append("c.professor LIKE %s")
                param.append(f"%{prof}%")

            if track:
                # 공백 무시 매칭 (웹공학 / 웹공학트랙 등)
                cond.append("REPLACE(c.track_major, ' ', '') LIKE REPLACE(%s, ' ', '')")
                param.append(f"%{track}%")

            if dept:
                cond.append("REPLACE(c.department, ' ', '') LIKE REPLACE(%s, ' ', '')")
                param.append(f"%{dept}%")

            if univ:
                cond.append("REPLACE(c.university, ' ', '') LIKE REPLACE(%s, ' ', '')")
                param.append(f"%{univ}%")

            if main_cat:
                cond.append("c.main_category = %s")
                param.append(main_cat)

            if grade.isdigit():
                cond.append("c.grade = %s")
                param.append(grade)

            if day:
                cond.append("s.day = %s")
                param.append(day)

            if time_start:
                cond.append("s.start_time >= %s")
                param.append(time_start)

            if time_end:
                cond.append("s.end_time <= %s")
                param.append(time_end)

            # --- 신규 필터 ----
            if room:
                cond.append("c.room LIKE %s")
                param.append(f"%{room}%")

            if section:
                cond.append("c.section = %s")
                param.append(section)

            if code:
                cond.append("c.code LIKE %s")
                param.append(f"%{code}%")

            if credit.isdigit():
                cond.append("c.credit = %s")
                param.append(credit)

            if lecture_hours:
                cond.append("c.lecture_hours LIKE %s")
                param.append(f"%{lecture_hours}%")

            if online_hours:
                cond.append("c.online_hours LIKE %s")
                param.append(f"%{online_hours}%")

            # ====== keyword 사용 방식 (intent에 따라 다름) ======
            if kw:
                if intent == "course_to_professor":
                    # 과목명 위주
                    cond.append("REPLACE(c.name, ' ', '') LIKE REPLACE(%s, ' ', '')")
                    param.append(f"%{kw}%")

                elif intent == "professor_to_course" and not prof:
                    # 교수 검색인데 professor 필터가 비어 있는 경우 → kw를 교수명으로 사용
                    cond.append("c.professor LIKE %s")
                    param.append(f"%{kw}%")

                else:
                    # 그 외에는 폭넓게 검색 (과목명 / 코드 / 트랙 / 학과)
                    cond.append(
                        "("
                        "REPLACE(c.name, ' ', '') LIKE REPLACE(%s, ' ', '') "
                        "OR REPLACE(c.code, ' ', '') LIKE REPLACE(%s, ' ', '') "
                        "OR c.room LIKE %s"
                        "OR c.section LIKE %s"
                        "OR c.online_hours LIKE %s"
                        "OR c.lecture_hours LIKE %s"
                        "OR REPLACE(c.track_major, ' ', '') LIKE REPLACE(%s, ' ', '') "
                        "OR REPLACE(c.department, ' ', '') LIKE REPLACE(%s, ' ', '')"
                        ")"
                    )
                    like_kw = f"%{kw}%"
                    param.extend([like_kw] * 8)

            # ====== 완전 노필터 방지 ======
            if not cond:
                # 아무 조건도 없으면 전체 검색 막기
                return []

            sql += " WHERE " + " AND ".join(cond)
            sql += " ORDER BY c.code, c.section, s.day, s.start_time"
            sql += " LIMIT 100"

            cur.execute(sql, tuple(param))
            rows = cur.fetchall()

            # 시간 문자열 조립 (NULL 안전 처리)
            for r in rows:
                d  = r.get("day") or ""
                st = r.get("start_time") or ""
                et = r.get("end_time") or ""
                if d and st and et:
                    r["time_str"] = f"{d} {st}~{et}"
                else:
                    r["time_str"] = ""

            return rows

    except Exception as e:
        print("DB 검색 오류:", e)
        return []

    finally:
        conn.close()



# ============================================================
# 4) 자연어 답변 생성
# ============================================================
def generate_answer(rows):
    """
    DB에서 가져온 row 리스트를
    사용자에게 보여줄 문자열로 변환한다.
    """
    if not rows:
        return "죄송합니다. 관련된 강의를 찾지 못했습니다."

    out = []
    for c in rows:
        time_part = c.get("time_str") or "시간 미정"
        room_part = c.get("room") or "강의실 미정"
        line = (
            f"{c['name']} ({c['code']}) - 담당: {c['professor']} / {c['credit']}학점 / "
            f"{time_part} / 강의실 {room_part}"
        ).strip()   # ← 앞뒤 공백 제거!

        out.append(line)
    return "\n".join(out)


# ============================================================
# 5) main 처리
# ============================================================
def answer_question(question: str):
    """
    전체 파이프라인:
    1) LLM으로 intent/filters 분석
    2) intent 보정
    3) 요일 한글 → 요일 코드 변환
    4) DB 검색
    5) 자연어 답변 생성
    """
    analysis = analyze_question_with_ai(question)
    print("LLM 분석 결과:", analysis)

    # intent 보정
    analysis["intent"] = fix_intent(analysis["intent"], analysis["filters"])

    # 요일 한글 → 영문 코드
    day_val = analysis["filters"].get("day")
    if day_val in DAY_MAP:
        analysis["filters"]["day"] = DAY_MAP[day_val]

    rows = search_courses(analysis["intent"], analysis["filters"])

    return generate_answer(rows)

# ============================================================
# 6) Knowledge Base 기반 답변
# ============================================================

kb = boto3.client("bedrock-agent-runtime", region_name="us-east-1")

KB_ID = "IVX0OG1VRG"  # 네가 준 KB ID
AGENT_ID = "IVX0OG1VRG"  # 동일하게 사용 (필요 시 따로 분리 가능)
AGENT_ALIAS_ID = "TSTALIASID"  # 기본 alias, 콘솔에서 확인 필요

def answer_kb(question: str) -> str:
    """
    AWS Bedrock Knowledge Base에서 답변을 가져오는 함수
    """
    try:
        response = kb.retrieve_and_generate(
            input={"text": question},
            retrieveAndGenerateConfiguration={
                "knowledgeBaseConfiguration": {
                    "knowledgeBaseId": KB_ID,
                    "modelArn": "arn:aws:bedrock:us-east-1::foundation-model/anthropic.claude-3-haiku-20240307-v1:0"
                },
                "type": "KNOWLEDGE_BASE"
            }
        )

        output = response["output"]["text"]
        return output.strip()

    except Exception as e:
        print("KB 오류:", e)
        return "지식기반에서 답변을 가져오는 중 오류가 발생했습니다."



# ============================================================
# 실행 테스트
# ============================================================
if __name__ == "__main__":
    q = "선택필수교양 중 온라인강의 3시간인 수업이 있나요?"
    print("질문:", q)
    print(answer_question(q))
