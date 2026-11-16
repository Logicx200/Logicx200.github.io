import ctypes, time, os
from PIL import ImageGrab
OUT = r"F:\DeepSeek工作区\_cossim_auto"
ImageGrab.grab(all_screens=False).crop((0,0,1920,1032)).save(os.path.join(OUT,"50_state.png"))
print("saved 50_state.png")
import psutil
print([ (p.pid, p.name()) for p in psutil.process_iter(["pid","name"]) if "XGCOSSim" in (p.info["name"] or "")])
