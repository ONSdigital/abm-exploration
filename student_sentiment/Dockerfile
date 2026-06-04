FROM python:3.12.5

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    MPLBACKEND=Agg

WORKDIR /app

COPY requirements.txt /app/requirements.txt

RUN pip install --upgrade pip && pip install -r /app/requirements.txt

COPY students_spatial.py /app/students_spatial.py
COPY UoM_road_shapefiles /app/UoM_road_shapefiles

# Run as a non-root user for better container security.
RUN useradd -m appuser && chown -R appuser:appuser /app
USER appuser

CMD ["python", "-u", "students_spatial.py"]