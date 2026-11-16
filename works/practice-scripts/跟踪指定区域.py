import cv2
import numpy as np
OPENCV_OBJECT_TRACKERS = {
    'boosting': cv2.legacy.TrackerBoosting_create,
    'csrt': cv2.legacy.TrackerCSRT_create,
    'kcf': cv2.legacy.TrackerKCF_create,
    'mil': cv2.legacy.TrackerMIL_create,
    'tld': cv2.legacy.TrackerTLD_create,
    'medianflow': cv2.legacy.TrackerMedianFlow_create,
    'mosse': cv2.legacy.TrackerMOSSE_create  
}

cap = cv2.VideoCapture('"D:\files\Projects\6月22日.mp4"')
if not cap.isOpened():
    print("Error: Could not open video.")
#新建一个KCF跟踪器
tracker = cv2.legacy.TrackerMOSSE_create()

#获取第一帧roi
ret, frame = cap.read()
if not ret:
    print('failed to get the frame')
else:
    cv2.namedWindow("frame", 0)  # 0可调大小，注意：窗口名必须imshow里面的一窗口名一直
    cv2.resizeWindow("frame", 800, 450)    # 设置长和宽
    cv2.imshow('frame', frame)

roi = cv2.selectROI('frame',frame, showCrosshair=True, fromCenter=False)
print(roi)
x, y, w, h = roi

#初始化跟踪器
tracker.init(frame, roi)

#继续读取下一帧
while (True):
    ret, frame = cap.read()
    
    if not ret:
        print('failed to get the frame')
        break
    success, roi = tracker.update(frame)
    if success:
        # 绘制边界框
        p1 = (int(roi[0]), int(roi[1]))
        p2 = (int(roi[0] + roi[2]), int(roi[1] + roi[3]))
    cv2.rectangle(frame, p1, p2, (255, 0, 0), 2, 1)
    cv2.namedWindow("frame", 0)  # 0可调大小，注意：窗口名必须imshow里面的一窗口名一直
    cv2.resizeWindow("frame", 800, 450)    # 设置长和宽
    cv2.imshow('frame', frame)

    key = cv2.waitKey(50)
    if key == 27:
        break

cap.release()
cv2.destroyAllWindows