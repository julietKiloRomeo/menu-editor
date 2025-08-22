# Use an official Python runtime as a parent image
FROM ghcr.io/astral-sh/uv:python3.13-alpine

# Set the working directory in the container
WORKDIR /app

# Copy the pyproject.toml and poetry.lock files to the container
COPY pyproject.toml /app/

# Install the dependencies
RUN uv sync --no-dev

# Copy the rest of the application code to the container
COPY . /app

# Make port 5000 available to the world outside this container
EXPOSE 5000

# Define environment variable
ENV PYTHONUNBUFFERED=1

# Run the application
CMD ["uv", "run", "--no-dev", "gunicorn", "-w", "4", "-b", "0.0.0.0:5000", "app:app",  "--log-level",  "debug", "--error-logfile", "-", "--access-logfile", "-"]
