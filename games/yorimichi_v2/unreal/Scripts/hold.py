"""Hold the guarded editor open for V2_HOLD_SECONDS (default 300) and write nothing: collaboration test C20 cancels
the build during this wait and checks that its guarded child stops and nothing else is touched."""
import os
import time

import unreal as U

U.log('V2 HOLD START')
time.sleep(float(os.environ.get('V2_HOLD_SECONDS', '300')))
U.log('V2 HOLD END')
