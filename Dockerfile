# Use an official Python runtime as a parent image
FROM python:3.12

# Install system dependencies including TeX Live, Pandoc, and fonts
RUN apt-get update && apt-get install -y \
    pandoc \
    texlive-xetex \
    texlive-fonts-recommended \
    texlive-fonts-extra \
    fonts-dejavu \
    wget \
    unzip \
    && rm -rf /var/lib/apt/lists/*

# Download and install Montserrat font from GitHub
RUN wget -q https://github.com/JulietaUla/Montserrat/archive/refs/heads/master.zip -O montserrat.zip && \
    unzip -q montserrat.zip -d /tmp && \
    mkdir -p /usr/local/share/fonts/montserrat && \
    cp /tmp/Montserrat-master/fonts/ttf/*.ttf /usr/local/share/fonts/montserrat/ && \
    rm -rf /tmp/Montserrat-master montserrat.zip && \
    fc-cache -f

# Set the working directory in the container
WORKDIR /app

# Install Poetry
RUN pip install uv

# Copy the pyproject.toml and poetry.lock files to the container
COPY pyproject.toml /app/

# Install the dependencies
RUN uv sync

# Copy the rest of the application code to the container
COPY . /app

# Make port 5000 available to the world outside this container
EXPOSE 5000

# Define environment variable
ENV FLASK_APP=app.py

# Run the application
CMD ["uv", "run", "flask", "run", "--host=0.0.0.0"]