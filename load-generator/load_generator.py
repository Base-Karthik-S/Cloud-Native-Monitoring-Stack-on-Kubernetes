import os
import time
import requests

# Configuration via Environment Variables
target = os.getenv('TARGET', 'http://localhost:30000/primecheck')
try:
    frequency = float(os.getenv('FREQUENCY', '5'))
except ValueError:
    print("Invalid FREQUENCY setting. Defaulting to 5.")
    frequency = 5.0

print(f"Load Generator Starting")
print(f"Target: {target}")
print(f"Frequency: {frequency} req/s")

# Metrics
total_requests = 0
failures = 0
total_response_time = 0

interval = 1.0 / frequency

while True:
    start_time = time.time()
    total_requests += 1

    try:
        # Generate Request with 10s Timeout
        response = requests.get(target, timeout=10)

        # Check status code
        if response.status_code == 200:
            total_response_time += response.elapsed.total_seconds()
        else:
            failures += 1

    except requests.exceptions.RequestException:
        # Timeout or connection error counts as failure
        failures += 1

    # Calculate & Print Metrics
    avg_rt = 0
    successes = total_requests - failures
    if successes > 0:
        avg_rt = total_response_time / successes

    print(f"Total: {total_requests} | Failures: {failures} | "
          f"Avg Response Time: {avg_rt:.4f}s")

    # Frequency Control
    elapsed = time.time() - start_time
    sleep_time = interval - elapsed
    if sleep_time > 0:
        time.sleep(sleep_time)
