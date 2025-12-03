# -*- coding: utf-8 -*-
import pymysql
import os # 보안 강화를 위해 환경 변수 사용을 권장
from typing import List, Dict

def get_connection():
    """
    RDS MySQL 데이터베이스 연결을 설정합니다.
    보안상 민감한 정보는 환경 변수 또는 AWS Secrets Manager를 사용해야 합니다.
    """
    # **경고: 실제 운영 환경에서는 암호를 코드에 직접 넣지 마세요.**
    return pymysql.connect(
        host=os.getenv("DB_HOST", "hsg-db-server.col0swwietso.us-east-1.rds.amazonaws.com"),
        user=os.getenv("DB_USER", "admin"),
        password=os.getenv("DB_PASSWORD", "1234qwer"), # 이 암호는 예시입니다.
        db=os.getenv("DB_NAME", "course_db"),
        charset="utf8"
    )

def search_courses(question: str) -> List[Dict]:
    """
    사용자 질문에서 키워드를 추출하여 과목을 검색하고, 결과를 AI에 전달합니다.
    
    Args:
        question: 사용자 질문 문자열

    Returns:
        과목 정보 딕셔너리 리스트
    """
    conn = get_connection()
    result = []
    try:
        # 질문을 단순 키워드로 사용하여 과목명 또는 코드 검색
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            # 과목명(name) 또는 코드(code)에 질문 내용이 포함된 과목을 검색
            sql = """
            SELECT * FROM courses
            WHERE name LIKE %s OR code LIKE %s OR professor LIKE %s
            LIMIT 10 
            """
            keyword = f"%{question}%" # 전체 질문을 키워드로 사용

            # 실제 서비스에서는 자연어 처리(NLP)를 통해 질문에서 핵심 키워드(예: '파이썬', '김교수')를 추출해야 더 정확합니다.
            cursor.execute(sql, (keyword, keyword, keyword))
            result = cursor.fetchall()
            
    except Exception as e:
        print(f"DB 검색 중 오류 발생: {e}")
    finally:
        conn.close()
        
    return result
