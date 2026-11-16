import cv2
import numpy as np
def video_demo():
    capture = cv2.VideoCapture(1) #0表示内置摄像头
    while(True):
        ret, frame = capture.read()
        if not ret:
            print("Failed to grab frame")
            break
        frame = cv2.flip(frame, 1)
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY) #抓取灰度视频流
        ret, thresh = cv2.threshold(gray, 200, 255, cv2.THRESH_BINARY)
    # 寻找轮廓
        contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    # 找到亮度最高的区域
        if contours:
            max_contour = max(contours, key=cv2.contourArea)
            x, y, w, h = cv2.boundingRect(max_contour)

        # 在原视频中绘制矩形框
            cv2.rectangle(frame, (x, y), (x+w, y+h), (0, 255, 0), 2)
            cv2.rectangle(gray, (x, y), (x+w, y+h), (0, 255, 0), 2)
        cv2.imshow("video",frame)
        cv2.imshow("gray",gray)
        #设置esc键退出
        c = cv2.waitKey(50)
        if c == 27:
            break

video_demo()
cv2.destroyAllwindows()
