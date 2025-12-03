# -*- coding: utf-8 -*-
import re
from typing import List, Dict, Optional, Any

# --- 강의 교시 및 시간표 매핑 (사용자 제공 데이터를 기반으로 최종 확정) ---
# Format: { '교시': ['시작_HH:MM:SS', '종료_HH:MM:SS'] }
# 복합 교시(예: 1-2, 2-3M) 파싱 시, 시작 교시의 시작 시각과 종료 교시의 종료 시각을 사용합니다.

# 1. 월, 수, 목 (75분 블록 패턴 기반)
# 사용자님의 75분 블록 데이터를 기반으로 시각을 설정했습니다.
MON_WED_THU_TIME_MAP: Dict[str, List[str]] = {
    # 주간 교시 (75분 블록 단위)
    # 1-2 (09:00-10:15)
    '1': ['09:00:00', '10:15:00'], 
    '2': ['09:00:00', '10:15:00'],
    '1M': ['09:00:00', '10:15:00'], 
    
    # 2M-3M (10:30-11:45)
    '2M': ['10:30:00', '11:45:00'],
    '3': ['10:30:00', '11:45:00'], 
    '3M': ['10:30:00', '11:45:00'],

    # 4-5 (12:00-13:15)
    '4': ['12:00:00', '13:15:00'], 
    '5': ['12:00:00', '13:15:00'],
    '4M': ['12:00:00', '13:15:00'],
    
    # 5M-6M (13:30-14:45)
    '5M': ['13:30:00', '14:45:00'],
    '6': ['13:30:00', '14:45:00'],
    '6M': ['13:30:00', '14:45:00'],
    
    # 7-8 (15:00-16:15)
    '7': ['15:00:00', '16:15:00'], 
    '8': ['15:00:00', '16:15:00'],
    '7M': ['15:00:00', '16:15:00'],
    
    # 8M-9M (16:30-17:45)
    '8M': ['16:30:00', '17:45:00'],
    '9': ['16:30:00', '17:45:00'],
    '9M': ['16:30:00', '17:45:00'],
    
    # 야간 교시 (75분 블록 단위)
    # 10-11 (18:00-19:15)
    '10': ['18:00:00', '19:15:00'],
    '11': ['18:00:00', '19:15:00'],
    '10M': ['18:00:00', '19:15:00'], # 10M 시각은 10-11 블록과 동일하다고 가정

    # 11M-12M (19:25-20:40)
    '11M': ['19:25:00', '20:40:00'],
    '12': ['19:25:00', '20:40:00'],
    '12M': ['19:25:00', '20:40:00'],
    
    # 13-14 (20:45-22:00)
    '13': ['20:45:00', '22:00:00'],
    '14': ['20:45:00', '22:00:00'],
    '13M': ['20:45:00', '22:00:00'],
    '14M': ['20:45:00', '22:00:00'],
}

# 2. 화, 금 (50분 블록 패턴 기반)
# 사용자님의 50분 블록 데이터 (예: 1-1M)를 기반으로 시각을 설정했습니다.
TUE_FRI_TIME_MAP: Dict[str, List[str]] = {
    # 50분 블록 단위 (1-1M 블록)
    '1': ['09:00:00', '09:50:00'], '1M': ['09:00:00', '09:50:00'],
    # 2-2M 블록
    '2': ['10:00:00', '10:50:00'], '2M': ['10:00:00', '10:50:00'],
    # 3-3M 블록
    '3': ['11:00:00', '11:50:00'], '3M': ['11:00:00', '11:50:00'],
    # 4-4M 블록
    '4': ['12:00:00', '12:50:00'], '4M': ['12:00:00', '12:50:00'], 
    # 5-5M 블록
    '5': ['13:00:00', '13:50:00'], '5M': ['13:00:00', '13:50:00'],
    # 6-6M 블록
    '6': ['14:00:00', '14:50:00'], '6M': ['14:00:00', '14:50:00'],
    # 7-7M 블록
    '7': ['15:00:00', '15:50:00'], '7M': ['15:00:00', '15:50:00'],
    # 8-8M 블록
    '8': ['16:00:00', '16:50:00'], '8M': ['16:00:00', '16:50:00'],
    # 9-9M 블록
    '9': ['17:00:00', '17:50:00'], '9M': ['17:00:00', '17:50:00'],
    # 10-10M 블록
    '10': ['18:00:00', '18:50:00'], '10M': ['18:00:00', '18:50:00'],
    
    # 야간 교시 (50분 블록 단위)
    # 11-11M 블록
    '11': ['18:55:00', '19:45:00'], '11M': ['18:55:00', '19:45:00'],
    # 12-12M 블록
    '12': ['19:50:00', '20:40:00'], '12M': ['19:50:00', '20:40:00'], 
    # 13-13M 블록
    '13': ['20:45:00', '21:35:00'], '13M': ['20:45:00', '21:35:00'],
    # 14-14M 블록
    '14': ['21:40:00', '22:30:00'], '14M': ['21:40:00', '22:30:00'],
}

# 요일 코드 매핑
DAY_MAP: Dict[str, str] = {
    '월': 'MON', '화': 'TUE', '수': 'WED', '목': 'THU',
    '금': 'FRI', '토': 'SAT', '일': 'SUN'
}

def get_time_map_for_day(day_char: str) -> Dict[str, List[str]]:
    """요일 문자에 따라 적절한 시간표 맵을 반환합니다."""
    if day_char in ['월', '수', '목']:
        return MON_WED_THU_TIME_MAP
    elif day_char in ['화', '금']:
        return TUE_FRI_TIME_MAP
    # 토, 일요일은 화/금 패턴과 유사하다고 가정합니다.
    return TUE_FRI_TIME_MAP


def parse_time_segment(day_char: str, period_str: str) -> Optional[Dict[str, str]]:
    """
    단일 요일과 교시 문자열(예: '월', '3-4')을 파싱하여 시작/종료 시각을 반환합니다.
    """
    if day_char not in DAY_MAP:
        return None 
    
    day = DAY_MAP[day_char]
    time_map = get_time_map_for_day(day_char) # 요일별 맵 선택
    
    # 정규식 패턴: [시작교시][M?](~[종료교시][M?])?
    # 이 정규식은 '2', '2M', '3', '3M' 등 교시 코드를 분리합니다.
    # '금2-3M'와 같은 형태도 시작 교시='2', 종료 교시='3M'으로 정확히 분리합니다.
    match = re.match(r'(\d+)(M?)(?:~|-)?(\d+)?(M?)$', period_str)
    if not match:
        return None
        
    start_num, start_m, end_num, end_m = match.groups()

    # 1. 시작 교시 코드 결정 (예: '2' 또는 '2M')
    start_period = f"{start_num}{start_m}" if start_m else start_num
    
    # 2. 종료 교시 코드 결정 및 시간 범위 파악
    if end_num:
        # 범위가 지정된 경우 (예: 3~4, 3M~4M, 1-3M)
        end_period = f"{end_num}{end_m}" if end_m else end_num
    else:
        # 단일 교시인 경우 (예: 3, 3M)
        end_period = start_period
        
    # TIME_MAP에서 시작 시각과 종료 시각을 찾습니다.
    start_time_data = time_map.get(start_period)
    end_time_data = time_map.get(end_period)

    # 데이터가 유효한지 확인
    if not start_time_data or not end_time_data:
        # print(f"경고: 교시 파싱 실패 - 유효하지 않은 코드: {period_str} (시작:{start_period}, 종료:{end_period})")
        return None

    # 강의 시작 시각은 시작 교시의 시작 시각, 종료 시각은 종료 교시의 종료 시각을 사용합니다.
    return {
        'day': day,
        'start_time': start_time_data[0], 
        'end_time': end_time_data[1]      
    }

def parse_course_time(time_str: str) -> List[Dict[str, str]]:
    """
    강의 시간표 문자열을 파싱해 요일 및 교시를 모두 처리.
    - 쉼표(,), 슬래시(/) 모두 구분자로 사용
    - 요일이 연속된 형태(수7-8목8M-9M)도 자동 분리
    """
    if not time_str or time_str in ['미정', '-']:
        return []

    # 1) , 또는 / 를 모두 분리자로 처리
    raw_segments = re.split(r'[,/]', time_str)

    # 2) 각 segment 내부에서 '요일이 두 개 이상 연속 등장'하는 경우 자동 분리
    cleaned_segments = []
    DAY = "월화수목금토일"

    for seg in raw_segments:
        seg = seg.strip()
        if not seg:
            continue

        # 예: "수7-8목8M-9M" → ['수7-8', '목8M-9M']
        temp = []
        i = 0
        while i < len(seg):
            if i + 1 < len(seg) and seg[i] in DAY and seg[i+1] in DAY:
                # 두 요일이 연속되어 있으면 split
                temp.append(seg[i])
                seg = seg[i+1:]
                i = 0
                continue
            i += 1

        # 다시 정규식으로 완전 분리
        pieces = re.findall(r'[월화수목금토일][0-9M\-~]+', seg)
        if pieces:
            cleaned_segments.extend(pieces)
        else:
            cleaned_segments.append(seg)

    results: List[Dict[str, str]] = []
    time_pattern = re.compile(r'([월화수목금토일])(.+)')

    for segment in cleaned_segments:
        match = time_pattern.match(segment)
        if not match:
            continue

        day_char = match.group(1)
        period_raw = match.group(2)

        # 상/하반기 같은 불필요 단어 제거
        period_str = period_raw.replace('상반기', '').replace('하반기', '').strip()

        parsed_segment = parse_time_segment(day_char, period_str)
        if parsed_segment:
            results.append(parsed_segment)

    if not results and time_str not in ['미정', '-']:
        print(f"경고: 최종 강의 시간 문자열 파싱 실패: {time_str}")

    return results


