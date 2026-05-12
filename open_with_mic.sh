#!/bin/bash
# Open Chrome with microphone permissions auto-granted for localhost

google-chrome \
  --use-fake-ui-for-media-stream \
  --use-fake-device-for-media-stream \
  --autoplay-policy=no-user-gesture-required \
  http://localhost:8000
