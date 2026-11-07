FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# pyproject.toml es necesario: define asyncio_mode y los marcadores de pytest
COPY pyproject.toml .
COPY src/ src/
COPY tools/ tools/
COPY data/ data/
COPY docs/api/ docs/api/
COPY tests/ tests/

EXPOSE 3000
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "3000"]
