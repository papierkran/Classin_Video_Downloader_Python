import os
import re
import time
import csv
import pickle
import random
import requests
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.edge.service import Service
from webdriver_manager.microsoft import EdgeChromiumDriverManager
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# ---------------------------
# 基础配置与工具函数
# ---------------------------
# 设置 Edge 驱动（webdriver_manager 会自动下载匹配版本）
service = Service(EdgeChromiumDriverManager().install())

def sanitize_filename(name):
    """清理非法文件名字符"""
    return re.sub(r'[\\/*?:"<>|]', '_', name).strip()

def generate_unique_filename(base_name, extension, save_dir):
    """生成唯一文件名，避免重名覆盖"""
    index = 0
    while True:
        suffix = f"_{index}" if index > 0 else ""
        filename = f"{base_name}{suffix}{extension}"
        full_path = os.path.join(save_dir, filename)
        if not os.path.exists(full_path):
            return filename
        index += 1

def download_file(url, save_path, cookies=None):
    """下载文件，如果提供 Cookie 则加入请求头以保持登录状态"""
    headers = {}
    if cookies:
        cookie_str = "; ".join([f"{cookie['name']}={cookie['value']}" for cookie in cookies])
        headers["Cookie"] = cookie_str
    try:
        with requests.get(url, stream=True, headers=headers) as r:
            r.raise_for_status()
            with open(save_path, 'wb') as f:
                for chunk in r.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
        return True
    except Exception as e:
        print("下载出错:", e)
        return False

# ---------------------------
# 视频下载相关函数
# ---------------------------
def get_course_details(driver):
    """
    获取公共课程信息（课程名称）
    假设课程名称位于页面固定位置，格式如 "课程名称：Python编程入门"
    """
    try:
        course_name = WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.XPATH, '/html/body/div[1]/div/div[2]/div/div[2]/p[1]/span[1]'))
        ).text
        course_name = course_name.replace("课程名称：", "").strip()
        course_name = sanitize_filename(course_name)
        return course_name
    except Exception as e:
        print("获取课程名称失败:", e)
        return None

def get_download_info(driver, course_id, lesson_id):
    """
    根据课程ID和课节ID构造下载页面 URL，
    遍历页面中所有视频条目（每个 <tr> 表示一个视频），
    提取视频下载链接、录课时间、录制方式、片段标题。

    返回：
        course_name, videos

        其中 course_name 为公共课程名称，
        videos 为一个列表，每个元素为字典：
            {
                "download_url": "...",
                "record_date": "2024-07-15",
                "record_method": "录制现场",   # 或“教室”等
                "segment_title": "片段 1"      # 片段名称或编号
            }
    """
    # 构造下载页面 URL
    page_url = (
        f"https://console.eeo.cn/saas/school/index.html#/singlePage/"
        f"CourseManagement/recordLessonManagement?courseId={course_id}"
        f"&lessonId={lesson_id}&record=true&live=true"
    )
    driver.get(page_url)
    time.sleep(3)

    try:
        # 等待表格中的视频条目加载（所有 tr）
        WebDriverWait(driver, 15).until(
            EC.presence_of_all_elements_located((By.XPATH, '/html/body/div[1]/div/div[2]/div/div[4]/div/div[3]/table/tbody/tr'))
        )
    except Exception as e:
        print("等待视频列表加载失败:", e)
        return None, []

    # 获取公共课程名称
    course_name = get_course_details(driver)
    if not course_name:
        return None, []

    # 遍历所有视频条目（tr）
    video_rows = driver.find_elements(By.XPATH, '/html/body/div[1]/div/div[2]/div/div[4]/div/div[3]/table/tbody/tr')
    videos = []
    for row in video_rows:
        try:
            # 下载链接：假定位于当前 tr 下的 td[9]/div/a
            download_url = row.find_element(By.XPATH, "./td[9]/div/a").get_attribute("href")

            # 录课时间：假定位于当前 tr 下的 td[5]/div/span
            record_time_text = row.find_element(By.XPATH, "./td[5]/div/span").text.strip()
            # 例如 "2024-07-15 10:29:08 ~ 2024-07-15 12:29:05"
            # 取第一个日期部分作为录课日期
            record_date = record_time_text.split(" ")[0]

            # 录制方式：假定位于当前 tr 下的 td[4]/div
            record_method = row.find_element(By.XPATH, "./td[4]/div").text.strip()
            record_method = sanitize_filename(record_method)

            # 片段标题：假定位于当前 tr 下的 td[2]/div
            segment_title = row.find_element(By.XPATH, "./td[2]/div").text.strip()
            segment_title = sanitize_filename(segment_title)

            videos.append({
                "download_url": download_url,
                "record_date": record_date,
                "record_method": record_method,
                "segment_title": segment_title
            })
        except Exception as e:
            print("解析视频条目失败:", e)

    return course_name, videos



def load_courses_from_csv(csv_file):
    """
    从 CSV 文件中读取课程信息
    CSV 中至少包含以下列：课节ID, 课程ID
    从第四行开始读取，并打印列名
    """
    courses = []
    try:
        with open(csv_file, newline='', encoding="utf-8-sig") as f:
            reader = csv.reader(f)
            # 跳过前三行（非数据行）
            for _ in range(3):
                next(reader, None)
            headers = next(reader, None)
            if headers is None:
                print("CSV 文件格式错误：没有列名行")
                return []
            print("列名:", headers)
            dict_reader = csv.DictReader(f, fieldnames=headers)
            for row in dict_reader:
                course = {
                    "lesson_id": row.get("课节ID", "").strip(),
                    "course_id": row.get("课程ID", "").strip(),
                    "lesson_name": row.get("课节名称", "").strip(),
                    "course_name_csv": row.get("课程名称", "").strip(),
                    "start_time": row.get("开课时间", "").strip()
                }
                courses.append(course)
    except Exception as e:
        print("读取 CSV 文件失败:", e)
    return courses

def parse_cookie_string(cookie_str):
    """将 Cookie 字符串转换为字典列表"""
    cookies = []
    for cookie in cookie_str.split(";"):
        if cookie.strip():
            try:
                key, value = cookie.strip().split("=", 1)
                cookies.append({"name": key.strip(), "value": value.strip()})
            except Exception as e:
                print("解析 Cookie 失败：", e)
    return cookies


def download_videos():
    """
    读取 CSV 文件中的课程信息，进入下载页面并下载所有视频
    """
    driver = webdriver.Edge(service=service)
    # 先打开首页以建立域名（请根据实际情况修改 URL）
    driver.get("https://www.eeo.cn")
    cookie_str = ("sensorsdata2015jssdkcross=%7B%22distinct_id%22%3A%2282022576%22%2C%22first_id%22%3A%2219458a9e671581-01d7f7926fabb86-4c657b58-2073600-19458a9e67221ff%22%2C%22props%22%3A%7B%22%24latest_traffic_source_type%22%3A%22%E7%9B%B4%E6%8E%A5%E6%B5%81%E9%87%8F%22%2C%22%24latest_search_keyword%22%3A%22%E6%9C%AA%E5%8F%96%E5%88%B0%E5%80%BC_%E7%9B%B4%E6%8E%A5%E6%89%93%E5%BC%80%22%2C%22%24latest_referrer%22%3A%22%22%7D%2C%22identities%22%3A%22eyIkaWRlbnRpdHlfY29va2llX2lkIjoiMTk0NThhOWU2NzE1ODEtMDFkN2Y3OTI2ZmFiYjg2LTRjNjU3YjU4LTIwNzM2MDAtMTk0NThhOWU2NzIyMWZmIiwiJGlkZW50aXR5X2xvZ2luX2lkIjoiODIwMjI1NzYifQ%3D%3D%22%2C%22history_login_id%22%3A%7B%22name%22%3A%22%24identity_login_id%22%2C%22value%22%3A%2282022576%22%7D%2C%22%24device_id%22%3A%2219458a9e671581-01d7f7926fabb86-4c657b58-2073600-19458a9e67221ff%22%7D; _eeos_uid=82022576; _eeos_useraccount=19502702034; _eeos_userlogo=https%3A%2F%2Fstatic.eeo.cn%2Fimages%2Fuser.png; _eeos_domain=.eeo.cn; _eeos_remember=1; _eeos_traffic=%2FQ%2BNhv7jnH8QLl2PlAgU0FJPNUpqQzSZN1heNySf%2B7CX10fC2E2e9PbOR7UIFkb%2BniBGyfM1m8M%3D; _eeos_sub=1; _eeos_sid=72017310; _eeos_nsid=C0fnLGibET79l3%2BQsdqF0Q%3D%3D; locationArgumentLang=zh-CN; __tk_id=cd0300239c6a51900a2ca3d9670289e0")

    cookies = parse_cookie_string(cookie_str)

    for cookie in cookies:
        if "domain" not in cookie:
            cookie["domain"] = ".eeo.cn"
        driver.add_cookie(cookie)

    driver.refresh()
    time.sleep(3)

    SAVE_DIR = "./videos"
    os.makedirs(SAVE_DIR, exist_ok=True)
    CSV_FILE = "./courses.csv"
    courses = load_courses_from_csv(CSV_FILE)

    if not courses:
        print("未能加载到课程信息，请检查 CSV 文件。")
        driver.quit()
        return

    print(f"读取到 {len(courses)} 个课程")
    # print("课程数据:", courses)

    for course in courses:
        course_id = course["course_id"]
        lesson_id = course["lesson_id"]
        page_url = (
            f"https://console.eeo.cn/saas/school/index.html#/singlePage/"
            f"CourseManagement/recordLessonManagement?courseId={course_id}"
            f"&lessonId={lesson_id}&record=true&live=true"
        )
        driver.get(page_url)
        driver.refresh()
        time.sleep(3)

        print(f"\n处理课程：课程ID {course_id} - 课节ID {lesson_id}")

        course_name, videos = get_download_info(driver, course_id, lesson_id)
        print(f"获取到 {len(videos) if videos else 0} 个视频")
        if not course_name or not videos:
            print(f"课程 {course_id} - {lesson_id} 没有可下载的视频，跳过。")
            continue

        for video in videos:
            record_time = video["record_date"]
            record_method = video["record_method"]
            download_url = video["download_url"]

            folder_name = f"{record_time}_{course_name}"
            folder_path = os.path.join(SAVE_DIR, folder_name)
            os.makedirs(folder_path, exist_ok=True)

            base_filename = f"{record_time}_{course_name}_{record_method}"
            extension = ".mp4"
            filename = generate_unique_filename(base_filename, extension, folder_path)
            save_path = os.path.join(folder_path, filename)

            print(f"下载中: {save_path}")
            if download_file(download_url, save_path, cookies=cookies):
                print(f"下载成功: {save_path}")
            else:
                print(f"下载失败: {save_path}")

            time.sleep(3)


    driver.quit()


# ---------------------------
# 主流程
# ---------------------------
def main():
    download_videos()

if __name__ == "__main__":
    main()
