import os

source = r'd:\AddingUI\Antigravity - Copy\OneClickVM\ui\components\vm_viewport.py'
dest = r'd:\AddingUI\Antigravity - Copy\OneClickVM\ui\components\vm_viewport_corrupt.py'

if os.path.exists(source):
    os.rename(source, dest)
    print("Renamed successfully.")
else:
    print("Source does not exist.")
