FROM python:3.10-slim

# 작업 디렉토리 설정
WORKDIR /app

# FFmpeg 및 필수 패키지 설치
RUN apt-get update && \
    apt-get install -y ffmpeg && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# 파이썬 패키지 복사 및 설치
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 소스 코드 복사
COPY . .

# 실행 명령어 (Render에서 제공하는 PORT 환경변수 사용)
CMD uvicorn main:app --host 0.0.0.0 --port ${PORT:-10000}
