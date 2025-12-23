import os
import sys

# Add app directory to path
sys.path.append(os.getcwd())

from config import Config

expected_value = 128 * 1024 * 1024
actual_value = Config.MAX_CONTENT_LENGTH

print(f"Expected MAX_CONTENT_LENGTH: {expected_value}")
print(f"Actual MAX_CONTENT_LENGTH: {actual_value}")

if expected_value == actual_value:
    print("SUCCESS: MAX_CONTENT_LENGTH is correctly configured.")
else:
    print("FAILURE: MAX_CONTENT_LENGTH is not correct.")
