import os, sys, time, subprocess
import win32gui, win32process, win32con, psutil
from PIL import ImageGrab

EXE = r"D:\XGGDCOSSim2\bin\XGCOSSimDesktop.exe"
WD  = r"D:\XGGDCOSSim2\bin"
OUT = r"F:\DeepSeek工作区\_cossim_auto"

p = subprocess.Popen([EXE], cwd=WD,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
print("pid", p.pid, flush=True)

def windows_of(pid):
    res = []
    def cb(h, _):
        try:
            _, wpid = win32process.GetWindowThreadProcessId(h)
            if wpid == pid and win32gui.IsWindowVisible(h):
                res.append(h)
        except Exception:
            pass
        return True
    win32gui.EnumWindows(cb, None)
    return res

t0 = time.time()
last = None
while time.time() - t0 < 90:
    wins = windows_of(p.pid)
    if wins:
        info = []
        for h in wins:
            title = win32gui.GetWindowText(h)
            rect = win32gui.GetWindowRect(h)
            cls = win32gui.GetClassName(h)
            info.append((h, cls, title, rect))
        big = [x for x in info if (x[3][2]-x[3][0]) > 300]
        if big:
            last = big
            break
    time.sleep(1.0)

print("waited %.1f s" % (time.time()-t0))
if last:
    for h, cls, title, rect in last:
        print(f"hwnd={h} class={cls!r} title={title!r} rect={rect}")
    h, cls, title, rect = max(last, key=lambda x: (x[3][2]-x[3][0])*(x[3][3]-x[3][1]))
    win32gui.SetForegroundWindow(h)
    time.sleep(1.0)
    img = ImageGrab.grab(all_screens=False)
    path = os.path.join(OUT, "01_launch.png")
    img.save(path)
    print("screenshot", path, img.size, flush=True)
else:
    print("no main window found; pid alive:", psutil.pid_exists(p.pid))
    img = ImageGrab.grab(all_screens=False)
    img.save(os.path.join(OUT, "01_launch_none.png"))
print("PID_KEEP", p.pid)
