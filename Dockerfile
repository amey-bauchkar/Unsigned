FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN python scripts/evaluate.py --train >/dev/null
EXPOSE 8000
CMD ["python", "-m", "unsigned", "--host", "0.0.0.0", "--port", "8000"]
