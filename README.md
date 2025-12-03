#📘 2025-2 수강신청 AI 어시스턴트

한성대학교 수강신청 책자를 자동 분석하고, 자연어 질문에 AI가 답변하는 서비스

#📌 프로젝트 개요

이 프로젝트는 150페이지가 넘는 수강신청 책자를 자동으로 분석하여 데이터베이스에 저장하고,
학생들이 자연어로 질문하면 AI가 조건 기반 검색을 수행해 정확한 답변을 주는 웹 서비스입니다.

예시 질문:

“웹공학트랙 4학년 전공필수 과목 알려줘”

“클라우드 컴퓨팅 담당 교수는 누구야?”

“10시에 시작해서 12시 전에 끝나는 과목 있어?”

“온라인수업 3H인 과목 알려줘”

이 모든 질문에 대해 LLM 기반 의도 분석 + MySQL 정확 검색으로 답변합니다.

#🎯 개발 동기

학생들이 수강신청을 할 때 겪는 불편함을 해결하기 위해 시작했습니다.

문제점

📄 150+ 페이지 수강신청 책자를 학생이 직접 찾아야 함

⏱ 시간/요일 표기(M 표기 등)에 익숙하지 않아 과목 시간을 직관적으로 알기 어려움
ex. 화2-3M → 실제 수업시간 10:00~11:50

🔎 조건 기반 검색(전공필수 + 트랙 + 요일 + 시간)이 불가능함

이 문제들을 자동화하고 싶어 프로젝트를 개발했습니다.

#👥 역할 분담


데이터 구축 담당: 홍승기

1.pdfplumber로 PDF 테이블 추출

2.텍스트 정제 + 파싱

3.요일/교시(M 포함) → 실제 시간 변환 로직 구현

4.MySQL에 구조화된 테이블(courses, schedules) 저장


AI 질의응답 담당: 김재욱

1.Nova Lite LLM으로 질문 의도 분석(JSON 필터 생성)

2.자연어 → DB 검색 조건 변환

3.검색 결과 자연어 답변 생성

4.KB(지식기반) 보조 답변 기능 추가

#Flask 웹 UI 개발



#🔍 핵심 기능
✅ 1. PDF 자동 분석 & DB 저장

pdfplumber로 표 데이터 추출

페이지별 컨텍스트 추적 (학과/트랙/학년/카테고리 등)

교양필수/선택필수/전공필수/전공선택 자동 분류

요일·교시(M 표기 포함) → 실제 시간 자동 변환

schedules 테이블로 분리 저장

✅ 2. AI 기반 자연어 질의응답
✔ Nova Lite가 하는 일

질문에서 의도(intent) 분석

필요한 DB 필터를 JSON으로 생성
(keyword, main_category, track, grade, professor, day, time_start, time_end 등)

예:

"10시에 시작해서 12시 전에 끝나는 전공필수"
→ 
{
  "intent": "search_by_filters",
  "filters": {
      "main_category": "전공필수",
      "time_start": "10:00",
      "time_end": "12:00"
  }
}

✔ 파이썬이 하는 일

이 필터들을 MySQL 쿼리로 변환하여 정확한 정보 조회

최종 자연어 답변 생성

✅ 3. KB(지식기반) 보조 기능

AWS Bedrock Knowledge Base(RAG) 사용

수강신청책자 PDF를 문서 단위로 검색해 LLM 답변 생성

정형 질문(DB 기반)이 해결되지 않을 때 보조로 사용

🛠 사용 기술 스택
Backend

Python (Flask)

MySQL (RDS)

pdfplumber (PDF 파싱)

boto3 (AWS API 연동)

AI / NLP

AWS Bedrock Nova Lite (Intent 분석)

Bedrock Knowledge Base (RAG 보조 답변)

Infra

AWS EC2 (배포 서버)

AWS S3 (PDF 저장)

AWS RDS MySQL (DB)

Frontend

HTML + CSS (Flask Template)

#📈 기대 효과

⏳ 학생들의 수강신청 준비 시간을 대폭 단축

🧠 전공필수, 트랙, 학년, 요일, 시간 등 조건 기반 검색 가능

🗣 전문 검색 문법 없이 자연어로 질문 가능

📚 수강신청 책자의 복잡한 표기(M 교시) 자동 해석

🤖 AI 기반 검색이므로 가독성과 접근성이 크게 향상

#테스트화면
질문: 선택필수교양 중 온라인수업(사이버 강의)이 3시간인 과목을 추천해주고 뭘 배우는지 간단히 설명해줘.

<img width="624" height="750" alt="image" src="https://github.com/user-attachments/assets/0fffca12-fb3f-4687-a682-09c883dbd8b9" />


질문: 웹공학트랙 중 전공기초면서 12시이전에 들을 수 있는 수업 추천해줘.

<img width="634" height="650" alt="image" src="https://github.com/user-attachments/assets/d2b445e6-7c89-40dc-8ad2-359e83c5f25d" />


#📌 향후 개선점

UI 개선 (챗봇 스타일 인터페이스)

과목 간 시간표 중복 자동 체크 기능

사용자 맞춤 시간표 추천 기능

PDF 파싱 속도 향상 및 더 많은 대학 데이터 지원
