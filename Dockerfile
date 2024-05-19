FROM python:3.10-slim-buster

WORKDIR /app

RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc curl gnupg2 && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

RUN curl -sSL https://install.python-poetry.org | python3 -

ENV PATH="${PATH}:/root/.local/bin"

ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

COPY pyproject.toml poetry.lock ./

# Configure Poetry: Do not create a virtual environment as the container itself provides isolation
RUN poetry config virtualenvs.create false

RUN poetry install --only main

COPY . /app

EXPOSE 8000

CMD ["poetry", "run", "uvicorn", "dtc_api:app", "--reload", "--host", "0.0.0.0", "--port", "8000"]
