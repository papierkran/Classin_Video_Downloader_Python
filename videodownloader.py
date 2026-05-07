import os
import re
import sys
import time
import csv
import requests
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

import driver_auto


def _get_base_dir():
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def sanitize_filename(name):
    if not name:
        return name
    s = re.sub(r'[\\/*?:"<>|]', '_', str(name)).strip()
    s = s.rstrip('. ')
    return s if s else '_'


def format_start_time_for_filename(start_time_str):
    if not start_time_str:
        return ""
    try:
        formatted = start_time_str.replace('/', '-').replace(' ', '_').replace(':', '-')
        parts = formatted.split('_')
        if len(parts) >= 2:
            date_part = parts[0]
            time_part = parts[1]
            date_parts = date_part.split('-')
            if len(date_parts) == 3:
                year, month, day = date_parts
                date_part = f"{year}-{month.zfill(2)}-{day.zfill(2)}"
            formatted = f"{date_part}_{time_part}"
        return formatted
    except Exception:
        return sanitize_filename(start_time_str)


def generate_unique_filename(base_name, extension, save_dir):
    index = 0
    while True:
        suffix = f"_{index}" if index > 0 else ""
        filename = f"{base_name}{suffix}{extension}"
        full_path = os.path.join(save_dir, filename)
        if not os.path.exists(full_path):
            return filename
        index += 1


def download_file(url, save_path, cookies=None, progress_callback=None):
    headers = {}
    if cookies:
        cookie_str = "; ".join([f"{cookie['name']}={cookie['value']}" for cookie in cookies])
        headers["Cookie"] = cookie_str
    try:
        with requests.get(url, stream=True, headers=headers) as r:
            r.raise_for_status()
            total = int(r.headers.get('Content-Length') or 0)
            done = 0
            last_t = time.time()
            last_done = 0
            with open(save_path, 'wb') as f:
                for chunk in r.iter_content(chunk_size=1024 * 256):
                    if not chunk:
                        continue
                    f.write(chunk)
                    done += len(chunk)
                    if progress_callback:
                        now = time.time()
                        if now - last_t >= 0.5:
                            delta_bytes = done - last_done
                            delta_t = max(now - last_t, 1e-6)
                            speed_mbps = (delta_bytes / 1024 / 1024) / delta_t
                            percent = int(done * 100 / total) if total > 0 else 0
                            info = f"{done/1024/1024:.1f}MB/{(total/1024/1024):.1f}MB" if total > 0 else f"{done/1024/1024:.1f}MB"
                            progress_callback(percent, speed_mbps, info)
                            last_t = now
                            last_done = done
            if progress_callback:
                progress_callback(100, 0.0, '完成')
        return True
    except Exception as e:
        print('下载出错:', e)
        if progress_callback:
            try:
                progress_callback(0, 0.0, f'失败: {e}')
            except Exception:
                pass
        return False


def get_course_details(driver):
    try:
        course_name = WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.XPATH, '/html/body/div[1]/div/div[2]/div/div[2]/p[1]/span[1]'))
        ).text
        course_name = course_name.replace('课程名称：', '').strip()
        return sanitize_filename(course_name)
    except Exception as e:
        print('获取课程名称失败:', e)
        return None


def get_download_info(driver, course_id, lesson_id):
    page_url = (
        f"https://console.eeo.cn/saas/school/index.html#/singlePage/"
        f"CourseManagement/recordLessonManagement?courseId={course_id}"
        f"&lessonId={lesson_id}&record=true&live=true"
    )
    
    # 使用JavaScript直接导航，确保SPA路由正确更新
    driver.get("https://console.eeo.cn/saas/school/index.html")
    time.sleep(2)
    
    # 通过JS设置hash来触发SPA路由变化
    js_navigate = f"""
    window.location.hash = '/singlePage/CourseManagement/recordLessonManagement?courseId={course_id}&lessonId={lesson_id}&record=true&live=true';
    """
    driver.execute_script(js_navigate)
    time.sleep(3)
    
    # 等待表格出现（增加超时时间）
    try:
        WebDriverWait(driver, 25).until(
            EC.presence_of_all_elements_located((By.XPATH, '/html/body/div[1]/div/div[2]/div/div[4]/div/div[3]/table/tbody/tr'))
        )
        # 额外等待确保数据完全加载
        time.sleep(2)
    except Exception as e:
        print('等待视频列表加载失败:', e)
        return None, []

    # 获取课程名称
    course_name = get_course_details(driver)
    if not course_name:
        return None, []

    video_rows = driver.find_elements(By.XPATH, '/html/body/div[1]/div/div[2]/div/div[4]/div/div[3]/table/tbody/tr')
    print(f'[DEBUG] 找到 {len(video_rows)} 行视频数据 (课程ID:{course_id}, 课堂ID:{lesson_id}, 课程名:{course_name})')
    videos = []
    for row_idx, row in enumerate(video_rows):
        try:
            # 获取所有td元素，以便调试
            tds = row.find_elements(By.TAG_NAME, 'td')
            print(f'[DEBUG] 第{row_idx}行有 {len(tds)} 个td')
            
            # 尝试从不同的td获取数据
            # 通常表格列顺序：序号, 视频标题, 课堂, 录制方式, 开始时间, 结束时间, 时长, 文件大小, 下载
            download_url = None
            record_time_text = None
            record_method = None
            segment_title = None
            
            # 遍历所有td找到下载链接
            for td_idx, td in enumerate(tds):
                try:
                    a_elem = td.find_elements(By.TAG_NAME, 'a')
                    if a_elem:
                        href = a_elem[0].get_attribute('href')
                        if href and 'http' in href:
                            download_url = href
                            print(f'[DEBUG] 第{row_idx}行在td[{td_idx}]找到下载URL')
                except:
                    pass
            
            # 按常见位置尝试获取其他字段
            if len(tds) > 4:
                try:
                    segment_title = sanitize_filename(tds[1].text.strip())
                except:
                    segment_title = None
            
            if len(tds) > 3:
                try:
                    record_method = sanitize_filename(tds[3].text.strip())
                except:
                    record_method = None
            
            if len(tds) > 4:
                try:
                    record_time_text = tds[4].text.strip()
                except:
                    record_time_text = None
            
            if not download_url:
                print(f'[DEBUG] 第{row_idx}行未找到下载URL，跳过此行')
                continue
                
            record_date = record_time_text.split(' ')[0] if record_time_text else '未知日期'
            record_method = record_method or '未知方式'
            segment_title = segment_title or f'片段_{row_idx+1}'
            
            print(f'[DEBUG] 第{row_idx}行: 标题={segment_title}, 日期={record_date}, 方式={record_method}, URL={download_url[:50]}...')
            videos.append({'download_url': download_url, 'record_date': record_date, 'record_method': record_method, 'segment_title': segment_title})
        except Exception as e:
            print(f'[DEBUG] 解析第{row_idx}行视频条目失败: {e}')
    return course_name, videos


def load_courses_from_csv(csv_file):
    def _read(encoding):
        courses = []
        with open(csv_file, newline='', encoding=encoding) as f:
            reader = csv.DictReader(f)
            if reader.fieldnames:
                reader.fieldnames = [h.strip().lstrip('\ufeff') for h in reader.fieldnames]
            for row in reader:
                if not isinstance(row, dict):
                    continue
                lesson_id = (row.get('课堂ID') or '').strip()
                if not lesson_id:
                    continue
                courses.append({
                    'lesson_id': lesson_id,
                    'course_id': (row.get('班级ID') or '').strip(),
                    'lesson_name': (row.get('课堂名称') or '').strip(),
                    'class_name': (row.get('班级名称') or '').strip(),
                    'start_time': (row.get('开课时间') or '').strip(),
                    'creation_time': (row.get('创建时间') or '').strip(),
                })
        return courses
    try:
        return _read('utf-8-sig')
    except UnicodeDecodeError:
        return _read('gbk')
    except Exception as e:
        print('读取 CSV 文件失败:', e)
        return []


def parse_cookie_string(cookie_str):
    cookies = []
    for cookie in cookie_str.split(';'):
        if cookie.strip():
            try:
                key, value = cookie.strip().split('=', 1)
                cookies.append({'name': key.strip(), 'value': value.strip()})
            except Exception as e:
                print('解析 Cookie 失败：', e)
    return cookies


def download_videos(save_dir, csv_file, cookie_str, driver_path=None, headless=False,
                    log_callback=None, pause_event=None, stop_event=None,
                    progress_callback=None, lesson_done_callback=None, driver_ref=None,
                    course_status_callback=None, courses_override=None, max_workers=4):
    def log(msg):
        print(msg)
        try:
            if log_callback:
                log_callback(msg)
        except Exception:
            pass

    browser, bin_path = driver_auto.detect_browser_preference()
    if not browser:
        raise RuntimeError('未检测到可用浏览器：请安装 Microsoft Edge 或 Chrome/Chromium')
    if driver_path and os.path.exists(driver_path):
        driver_exe = driver_path
    else:
        driver_exe = driver_auto.ensure_driver(browser, base_dir=_get_base_dir())
    driver = driver_auto.create_webdriver(browser, driver_exe, headless=headless, binary_path=bin_path)
    if driver_ref is not None:
        driver_ref['driver'] = driver

    driver.get('https://www.eeo.cn')
    cookies = parse_cookie_string(cookie_str or '')
    for cookie in cookies:
        if 'domain' not in cookie:
            cookie['domain'] = '.eeo.cn'
        try:
            driver.add_cookie(cookie)
        except Exception as e:
            log(f'添加 cookie 失败: {e}')
    driver.refresh()
    time.sleep(3)

    save_dir = os.path.normpath(os.path.abspath(save_dir or os.path.join(os.path.expanduser('~'), 'videos')))
    os.makedirs(save_dir, exist_ok=True)

    if courses_override is not None:
        courses = courses_override
        log(f'使用 GUI 传入课程列表：{len(courses)} 条')
    else:
        csv_file = csv_file or os.path.join(_get_base_dir(), 'courses.csv')
        courses = load_courses_from_csv(csv_file)
        if not courses:
            log('未能加载到课程信息，请检查 CSV 文件。')
            try:
                driver.quit()
            finally:
                if driver_ref is not None:
                    driver_ref.pop('driver', None)
            return
        log(f'读取到 {len(courses)} 个课程')

    from collections import defaultdict
    class_earliest_start = defaultdict(lambda: None)
    for c in courses:
        cid = c.get('course_id')
        st = c.get('start_time', '')
        if cid and st:
            try:
                dt = st.replace('/', '-').replace(' ', 'T').split('T')[0]
                existing = class_earliest_start[cid]
                if existing is None or dt < existing:
                    class_earliest_start[cid] = dt
            except Exception:
                pass

    if progress_callback:
        try:
            progress_callback(len(courses), 0, None, None)
        except Exception:
            pass

    for course_index, course in enumerate(courses, start=1):
        try:
            if course_status_callback:
                course_status_callback(course_index, course, 'downloading', '开始处理')
        except Exception:
            pass

        if stop_event is not None and getattr(stop_event, 'is_set', lambda: False)():
            log('收到停止信号，终止下载。')
            break

        course_id = course['course_id']
        lesson_id = course['lesson_id']
        log(f'处理课程：课程ID {course_id} - 课堂ID {lesson_id}')
        if progress_callback:
            try:
                progress_callback(len(courses), course_index, course, None)
            except Exception:
                pass

        course_name, videos = get_download_info(driver, course_id, lesson_id)
        total_videos = len(videos) if videos else 0
        log(f'获取到 {total_videos} 个视频')

        if not course_name or not videos:
            log(f'课程 {course_id} - {lesson_id} 没有可下载的视频，跳过。')
            try:
                if course_status_callback:
                    course_status_callback(course_index, course, 'failed', '没有可下载的视频')
            except Exception:
                pass
            try:
                if lesson_done_callback:
                    lesson_done_callback({'course_id': course_id, 'lesson_id': lesson_id, 'course_name': course_name or course.get('class_name') or '未知班级', 'class_name': course.get('class_name') or '未知班级', 'lesson_name': course.get('lesson_name'), 'total_videos': 0, 'downloaded': 0, 'course_row_index': course_index, 'total_courses': len(courses)})
            except Exception:
                pass
            continue

        class_name_csv = course.get('class_name') or course.get('course_id') or '未知班级'
        lesson_name_csv = course.get('lesson_name') or course.get('lesson_id') or None
        start_time_csv = course.get('start_time', '')
        earliest_date = class_earliest_start.get(course_id) or ''
        formatted_earliest = f"{earliest_date.replace('-', '-')}" if earliest_date else ''
        class_name_part = sanitize_filename(class_name_csv) or '未知班级'
        class_dir_name = f'{formatted_earliest}_{class_name_part}' if formatted_earliest else class_name_part
        formatted_start = format_start_time_for_filename(start_time_csv)
        lesson_name_part = sanitize_filename(lesson_name_csv or course_name or '未知课堂')
        lesson_dir_name = f'{formatted_start}_{lesson_name_part}' if formatted_start else lesson_name_part
        folder_path = os.path.join(save_dir, class_dir_name, lesson_dir_name)
        os.makedirs(folder_path, exist_ok=True)

        downloaded_count = 0
        failed_count = 0
        download_lock = threading.Lock()
        
        def download_video_task(idx, video, course_name, folder_path, total_videos):
            """单个视频下载任务"""
            nonlocal downloaded_count, failed_count
            
            record_time = video['record_date']
            record_method = video['record_method']
            download_url = video['download_url']
            segment_title = video.get('segment_title') or f'片段{idx}'
            
            # [调试日志]
            print(f'[DEBUG] 开始下载视频{idx}/{total_videos}:')
            print(f'       标题: {segment_title}')
            print(f'       日期: {record_time}')
            print(f'       方式: {record_method}')
            print(f'       URL: {download_url[:80]}...')
            
            base_filename = f'{record_time}_{sanitize_filename(course_name)}_{record_method}_{sanitize_filename(segment_title)}'
            filename = generate_unique_filename(base_filename, '.mp4', folder_path)
            save_path = os.path.join(folder_path, filename)
            log(f'下载中: {save_path}')
            
            # 修复lambda闭包问题 - 将变量作为默认参数传递
            def make_progress_callback(idx_val, total_val, course_val):
                def callback(percent, speed_mbps, info):
                    if progress_callback:
                        try:
                            progress_callback(len(courses), course_index, course_val, 
                                            {'percent': percent, 'speed_mbps': speed_mbps, 'info': info, 
                                             'video_index': idx_val, 'total_videos': total_val})
                        except Exception:
                            pass
                return callback if progress_callback else None
            
            progress_cb_for_this_video = make_progress_callback(idx, total_videos, course)
            
            success = download_file(download_url, save_path, cookies=cookies,
                                    progress_callback=progress_cb_for_this_video)
            
            with download_lock:
                if success:
                    downloaded_count += 1
                    log(f'下载成功: {save_path}')
                else:
                    failed_count += 1
                    log(f'下载失败: {save_path}')
                if progress_callback:
                    try:
                        progress_callback(len(courses), course_index, course, idx)
                    except Exception:
                        pass
        
        # 使用线程池并发下载（可配置的线程数）
        max_workers = max(1, min(8, max_workers))
        print(f'[DEBUG] 使用 {max_workers} 个线程进行并发下载')
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {}
            for idx, video in enumerate(videos, start=1):
                # 检查暂停/停止信号
                while pause_event is not None and getattr(pause_event, 'is_set', lambda: False)():
                    if stop_event is not None and getattr(stop_event, 'is_set', lambda: False)():
                        break
                    time.sleep(0.3)
                
                if stop_event is not None and getattr(stop_event, 'is_set', lambda: False)():
                    log('收到停止信号，取消剩余下载任务。')
                    executor.shutdown(wait=False)
                    break
                
                # 提交下载任务到线程池
                future = executor.submit(download_video_task, idx, video, course_name, folder_path, total_videos)
                futures[future] = idx
            
            # 等待所有任务完成
            for future in as_completed(futures):
                try:
                    future.result()
                except Exception as e:
                    log(f'下载任务异常: {e}')

        try:
            if course_status_callback:
                st = 'success' if downloaded_count == total_videos and total_videos > 0 else ('failed' if total_videos == 0 or downloaded_count == 0 else 'success')
                msg = f'完成：{downloaded_count}/{total_videos}' if total_videos else '没有视频'
                course_status_callback(course_index, course, st, msg)
        except Exception:
            pass

        try:
            if lesson_done_callback:
                lesson_done_callback({'course_id': course_id, 'lesson_id': lesson_id, 'course_name': course_name, 'class_name': class_name_csv, 'lesson_name': lesson_name_csv, 'total_videos': total_videos, 'downloaded': downloaded_count, 'course_row_index': course_index, 'total_courses': len(courses)})
            if progress_callback:
                progress_callback(len(courses), course_index, course, None)
        except Exception:
            pass

    try:
        driver.quit()
    finally:
        if driver_ref is not None:
            driver_ref.pop('driver', None)


if __name__ == '__main__':
    pass
