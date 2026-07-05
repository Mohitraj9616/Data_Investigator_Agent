# use slim python image — full image is 1GB+, slim is ~200MB
FROM python:3.12-slim

# set working directory inside container
WORKDIR /app

# copy requirements first — Docker caches this layer
# so pip install only reruns when requirements.txt changes
# not every time your code changes
COPY requirements.txt .

# install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# copy project code
# .dockerignore controls what gets excluded
COPY . .

# create a non-root user — never run production apps as root
RUN adduser --disabled-password --gecos "" appuser
USER appuser

# expose the port uvicorn will listen on
EXPOSE 8000

# start the app
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]