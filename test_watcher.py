import sys, time
sys.path.append('.')
from core.change_watcher import ChangeWatcher
from core.logger import logger
watcher = ChangeWatcher('/home/ew/UI_example', lambda lines: print("CHANGED!", lines))
watcher.start()
time.sleep(3)
with open('/home/ew/UI_example/buttons/file.txt', 'a') as f:
    f.write('hello\n')
print("File written, waiting 5 seconds...")
time.sleep(5)
watcher.stop()
