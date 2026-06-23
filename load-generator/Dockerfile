FROM python:3.9-slim

# Install dependencies
RUN pip install requests

# Add the script
COPY load_generator.py /app/load_generator.py
WORKDIR /app

# Set unbuffered output so logs show up immediately in Kubernetes
ENV PYTHONUNBUFFERED=1

# Command to run
CMD ["python", "load_generator.py"]
