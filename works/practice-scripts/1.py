from selenium import webdriver
from selenium.webdriver.edge.options import Options as EdgeOptions
from selenium.webdriver.edge.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import logging
from selenium import webdriver

# 设置selenium的日志级别为DEBUG
selenium_logger = logging.getLogger('selenium')
selenium_logger.setLevel(logging.DEBUG)

# 设置urllib3的日志级别为DEBUG
urllib3_logger = logging.getLogger('urllib3')
urllib3_logger.setLevel(logging.DEBUG)

# 创建一个handler，用于输出日志到控制台
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.DEBUG)

# 设置日志格式
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
console_handler.setFormatter(formatter)

# 将handler添加到selenium和urllib3的logger
selenium_logger.addHandler(console_handler)
urllib3_logger.addHandler(console_handler)

# 接下来是您的selenium WebDriver代码
# ...

# 设置Selenium使用的浏览器驱动路径
driver_path = "C:/Users/x1503/AppData/Local/Programs/Python/Python39/msedgedriver/msedgedriver.exe"

# 创建Edge浏览器选项
options = EdgeOptions()
options.headless = False  # 设置为非无头模式

# 创建Edge服务
service = Service(executable_path=driver_path)

# 使用服务创建 WebDriver 实例
from selenium import webdriver
from selenium.webdriver.common.desired_capabilities import DesiredCapabilities

caps = DesiredCapabilities().EDGE
caps['timeouts'] = {'implicit': 10, 'pageLoad': 300, 'script': 30}
options = EdgeOptions()
options.headless = False

browser = webdriver.Edge(executable_path=driver_path)

# 设置页面加载策略等选项
browser.capabilities['pageLoadStrategy'] = 'normal'

# 豆瓣评论页面的URL
url = 'https://movie.douban.com/subject/34444648/'  # 修正 URL

# 使用Selenium打开页面
browser.get(url)

# 等待页面加载完成
try:
    WebDriverWait(browser, 10).until(
        EC.presence_of_element_located((By.CLASS_NAME, 'comment-item'))
    )
    # 提取评论内容
    comments = browser.find_elements(By.CLASS_NAME, 'comment-item')
    for comment in comments:
        print(comment.text)
finally:
    # 关闭浏览器
    browser.quit()