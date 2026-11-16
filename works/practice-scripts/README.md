# 练习脚本合集（Selenium / OpenCV）

早期学习时写的零散练习脚本：用 Selenium 抓取网页评论、用 OpenCV 做视频目标跟踪等，代码原样保留。

## 文件清单
- `1.py`：Selenium + Edge 打开豆瓣电影页面并抓取评论区文本（`comment-item`）；
- `跟踪指定区域.py`：OpenCV 读取本地 mp4，手选 ROI 后用 MOSSE/CSRT 等跟踪器跟踪；
- `跟踪最亮的点.py`：OpenCV 打开摄像头，二值化后寻找最亮区域轮廓；
- `comments.txt` / `douban_comments.txt`：抓取结果（空文件）；
- `火箭发射.mp4`：观测样例视频（约 6.4 MB）。

## 说明
- 来源机器路径：`I:\files\Projects`；脚本依赖本机路径（EdgeDriver、视频文件），运行前需按环境改路径；
- 未归档：`2.py`（内含明文账号/密码，安全原因不发布）、`3.py`（0 字节）以及另外 3 个大体积视频。
