
import pymysql
import os 
from typing import List, Dict

def get_connection():
    """
    RDS MySQL 데이터베이스 연결을 설정합니다.
    보안상 민감한 정보는 환경 변수 또는 AWS Secrets Manager를 사용해야 합니다.
    """
    
    return pymysql.connect(
        host=os.getenv("DB_HOST"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        db=os.getenv("DB_NAME"),
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
        
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
           
            sql = """
            SELECT * FROM courses
            WHERE name LIKE %s OR code LIKE %s OR professor LIKE %s
            LIMIT 10 
            """
            keyword = f"%{question}%" 

            
            cursor.execute(sql, (keyword, keyword, keyword))
            result = cursor.fetchall()
            
    except Exception as e:
        print(f"DB 검색 중 오류 발생: {e}")
    finally:
        conn.close()
        
    return result
