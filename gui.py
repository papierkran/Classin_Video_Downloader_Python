import os
import json
import threading
import queue
import tkinter as tk
from tkinter import filedialog, messagebox
from tkinter.scrolledtext import ScrolledText
import tempfile
import subprocess
import sys
import time

import videodownloader
from tkinter import ttk


def _get_base_dir():
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


CONFIG_PATH = os.path.join(_get_base_dir(), 'config.json')

BG_COLOR = '#f5f7fa'
CARD_BG = '#ffffff'
ACCENT = '#3182ce'
ACCENT_HOVER = '#2c5282'
TEXT_COLOR = '#2d3748'
TEXT_MUTED = '#718096'
BORDER_COLOR = '#e2e8f0'
SUCCESS_COLOR = '#38a169'
DANGER_COLOR = '#e53e3e'


def _make_entry(parent, **kw):
    e = tk.Entry(parent, **kw)
    e.config(font=('Microsoft YaHei UI', 10), relief='flat', highlightthickness=1,
             highlightbackground=BORDER_COLOR, highlightcolor=ACCENT, bd=0,
             bg='#fff', fg=TEXT_COLOR, insertbackground=ACCENT)
    return e


def _make_label(parent, text, **kw):
    return tk.Label(parent, text=text, fg=TEXT_COLOR, font=('Microsoft YaHei UI', 10), **kw)


def _make_btn(parent, text, command, style='primary', **kw):
    bg = ACCENT if style == 'primary' else CARD_BG
    fg = '#fff' if style == 'primary' else TEXT_COLOR
    btn = tk.Button(parent, text=text, command=command, font=('Microsoft YaHei UI', 10),
                    bg=bg, fg=fg, activebackground=ACCENT_HOVER if style == 'primary' else BORDER_COLOR,
                    activeforeground='#fff' if style == 'primary' else TEXT_COLOR,
                    relief='flat', bd=0, cursor='hand2', padx=14, pady=6, **kw)
    if style == 'danger':
        btn.config(bg=DANGER_COLOR, activebackground='#c53030')
    return btn


class App:
    def center_window(self, win, width, height):
        try:
            self.root.update_idletasks()
            win.update_idletasks()
            rx = self.root.winfo_rootx()
            ry = self.root.winfo_rooty()
            rw = self.root.winfo_width()
            rh = self.root.winfo_height()
            x = rx + (rw - width) // 2
            y = ry + (rh - height) // 2
            win.geometry(f"{width}x{height}+{x}+{y}")
        except Exception:
            try:
                win.geometry(f"{width}x{height}")
            except Exception:
                pass

    def __init__(self, root):
        self.root = root
        root.title('ClassIn 视频下载器')
        root.configure(bg=BG_COLOR)
        root.minsize(960, 680)
        root.geometry('1050x750')

        self.log_q = queue.Queue()
        self.total_items = 0
        self.success_count = 0
        self.fail_count = 0
        self._is_downloading = False
        self._check_done_id = None

        main = tk.Frame(root, bg=BG_COLOR, padx=16, pady=12)
        main.pack(fill=tk.BOTH, expand=True)

        header = tk.Frame(main, bg=BG_COLOR)
        header.pack(fill=tk.X, pady=(0, 10))
        tk.Label(header, text='ClassIn 视频下载器', font=('Microsoft YaHei UI', 16, 'bold'),
                 fg=ACCENT, bg=BG_COLOR).pack(side=tk.LEFT)
        tk.Label(header, text='批量下载课堂录播视频', font=('Microsoft YaHei UI', 9),
                 fg=TEXT_MUTED, bg=BG_COLOR).pack(side=tk.LEFT, padx=(10, 0), pady=4)

        config_card = tk.Frame(main, bg=CARD_BG, relief='flat', padx=14, pady=10)
        config_card.pack(fill=tk.X, pady=(0, 8))
        config_card.config(highlightbackground=BORDER_COLOR, highlightthickness=1)

        _make_label(config_card, '浏览器驱动').grid(row=0, column=0, sticky='w', pady=(0, 4))
        self.driver_entry = _make_entry(config_card, width=50)
        self.driver_entry.grid(row=0, column=1, padx=(10, 6), pady=(0, 4), sticky='we')
        _make_btn(config_card, '浏览', self.browse_driver, style='secondary').grid(row=0, column=2, pady=(0, 4))

        _make_label(config_card, '保存目录').grid(row=1, column=0, sticky='w', pady=4)
        self.save_entry = _make_entry(config_card, width=50)
        self.save_entry.grid(row=1, column=1, padx=(10, 6), pady=4, sticky='we')
        _make_btn(config_card, '浏览', self.browse_save, style='secondary').grid(row=1, column=2, pady=4)

        _make_label(config_card, '数据文件').grid(row=2, column=0, sticky='w', pady=4)
        self.csv_entry = _make_entry(config_card, width=50)
        self.csv_entry.grid(row=2, column=1, padx=(10, 6), pady=4, sticky='we')
        _make_btn(config_card, '浏览', self.browse_csv, style='secondary').grid(row=2, column=2, pady=4)

        _make_label(config_card, 'Cookie').grid(row=3, column=0, sticky='nw', pady=(4, 0))
        self.cookie_text = tk.Text(config_card, height=3, width=50, font=('Consolas', 9),
                                   relief='flat', highlightthickness=1, highlightbackground=BORDER_COLOR,
                                   highlightcolor=ACCENT, bd=0, bg='#fff', fg=TEXT_COLOR,
                                   insertbackground=ACCENT, wrap=tk.WORD)
        self.cookie_text.grid(row=3, column=1, padx=(10, 6), pady=4, sticky='we')
        _make_btn(config_card, '获取Cookie', self.get_cookie, style='secondary').grid(row=3, column=2, pady=4, sticky='n')

        _make_label(config_card, '下载线程数').grid(row=4, column=0, sticky='w', pady=4)
        self.threads_entry = _make_entry(config_card, width=50)
        self.threads_entry.grid(row=4, column=1, padx=(10, 6), pady=4, sticky='we')
        self.threads_entry.insert(0, '4')
        tk.Label(config_card, text='(1-8)', fg=TEXT_MUTED, font=('Microsoft YaHei UI', 9)).grid(row=4, column=2, pady=4, sticky='w', padx=6)

        config_card.columnconfigure(1, weight=1)

        action_frame = tk.Frame(main, bg=BG_COLOR)
        action_frame.pack(fill=tk.X, pady=(0, 8))
        self.save_btn = _make_btn(action_frame, '保存配置', self.save_config, style='secondary')
        self.save_btn.pack(side=tk.LEFT, padx=(0, 6))
        self.start_btn = _make_btn(action_frame, '开始下载', self.start_download, style='primary')
        self.start_btn.pack(side=tk.LEFT, padx=(0, 6))
        self.pause_btn = _make_btn(action_frame, '暂停', self.toggle_pause, style='secondary')
        self.pause_btn.pack(side=tk.LEFT, padx=(0, 6))
        self.stop_btn = _make_btn(action_frame, '停止', self.stop_download, style='danger')
        self.stop_btn.pack(side=tk.LEFT)

        progress_frame = tk.Frame(main, bg=BG_COLOR)
        progress_frame.pack(fill=tk.X, pady=(0, 6))
        row1 = tk.Frame(progress_frame, bg=BG_COLOR)
        row1.pack(fill=tk.X)
        self.video_progress_label = _make_label(row1, '当前视频: 0% | 0.00 MB/s')
        self.video_progress_label.pack(side=tk.LEFT, padx=(0, 10))
        self.video_progress_var = tk.IntVar()
        pb_style = ttk.Style()
        try:
            pb_style.configure('Video.Horizontal.TProgressbar', troughcolor=BORDER_COLOR, background=ACCENT)
            video_style = 'Video.Horizontal.TProgressbar'
        except tk.TclError:
            video_style = 'Horizontal.TProgressbar'
        self.video_progress_bar = ttk.Progressbar(row1, variable=self.video_progress_var, maximum=100,
                                                  style=video_style, length=300)
        self.video_progress_bar.pack(side=tk.LEFT, fill=tk.X, expand=True)

        row2 = tk.Frame(progress_frame, bg=BG_COLOR)
        row2.pack(fill=tk.X, pady=(4, 0))
        self.total_progress_label = _make_label(row2, '总进度: 0/0 | 成功 0 失败 0')
        self.total_progress_label.pack(side=tk.LEFT, padx=(0, 10))
        self.total_canvas = tk.Canvas(row2, height=14, bg=BORDER_COLOR, highlightthickness=0)
        self.total_canvas.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.total_canvas.bind('<Configure>', lambda e: self._redraw_total_bar())
        row1.pack_forget()
        row2.pack_forget()
        self._progress_row1 = row1
        self._progress_row2 = row2

        list_frame = tk.Frame(main, bg=BG_COLOR)
        list_frame.pack(fill=tk.BOTH, expand=True)
        _make_label(list_frame, '任务列表').pack(anchor='w', pady=(0, 4))
        table_card = tk.Frame(list_frame, bg=CARD_BG, relief='flat')
        table_card.pack(fill=tk.BOTH, expand=True)
        table_card.config(highlightbackground=BORDER_COLOR, highlightthickness=1)

        columns = ('course_id', 'lesson_id', 'class_name', 'lesson_name', 'start_time', 'status', 'message')
        self.tree = ttk.Treeview(table_card, columns=columns, show='headings', height=6)
        self.tree.heading('course_id', text='班级ID')
        self.tree.heading('lesson_id', text='课堂ID')
        self.tree.heading('class_name', text='班级名称')
        self.tree.heading('lesson_name', text='课堂名称')
        self.tree.heading('start_time', text='开课时间')
        self.tree.heading('status', text='状态')
        self.tree.heading('message', text='消息')
        self.tree.column('course_id', width=100, anchor='w')
        self.tree.column('lesson_id', width=100, anchor='w')
        self.tree.column('class_name', width=120, anchor='w')
        self.tree.column('lesson_name', width=120, anchor='w')
        self.tree.column('start_time', width=130, anchor='w')
        self.tree.column('status', width=70, anchor='center')
        self.tree.column('message', width=180, anchor='w')
        vsb = ttk.Scrollbar(table_card, orient='vertical', command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        self.tree.tag_configure('pending', background='#ffffff')
        self.tree.tag_configure('downloading', background='#FFF3CD')
        self.tree.tag_configure('success', background='#D1E7DD')
        self.tree.tag_configure('failed', background='#F8D7DA')

        table_actions = tk.Frame(list_frame, bg=BG_COLOR)
        table_actions.pack(fill=tk.X, pady=(6, 6))
        _make_btn(table_actions, '导入CSV/XLSX', self.import_table_file, style='secondary').pack(side=tk.LEFT, padx=(0, 6))
        _make_btn(table_actions, '新增行', self.add_row_dialog, style='secondary').pack(side=tk.LEFT, padx=(0, 6))
        _make_btn(table_actions, '编辑行', self.edit_selected_row_dialog, style='secondary').pack(side=tk.LEFT, padx=(0, 6))
        _make_btn(table_actions, '删除行', self.delete_selected_rows, style='danger').pack(side=tk.LEFT)

        log_frame = tk.Frame(list_frame, bg=BG_COLOR)
        log_frame.pack(fill=tk.BOTH, expand=True)
        _make_label(log_frame, '任务日志').pack(anchor='w', pady=(0, 4))
        log_card = tk.Frame(log_frame, bg=CARD_BG, relief='flat')
        log_card.pack(fill=tk.BOTH, expand=True)
        log_card.config(highlightbackground=BORDER_COLOR, highlightthickness=1)
        self.log_area = ScrolledText(log_card, height=8, width=80, state='disabled',
                                     font=('Consolas', 9), bg='#fafafa', fg=TEXT_COLOR,
                                     relief='flat', padx=10, pady=8, wrap=tk.WORD)
        self.log_area.pack(fill=tk.BOTH, expand=True, padx=1, pady=1)

        self.load_config()
        self.auto_load_videodata_folder()
        self.root.after(200, self.flush_log_queue)

    def browse_driver(self):
        f = filedialog.askopenfilename(filetypes=[('Driver', '*.exe'), ('All Files', '*.*')])
        if f:
            self.driver_entry.delete(0, tk.END)
            self.driver_entry.insert(0, f)

    def browse_save(self):
        d = filedialog.askdirectory()
        if d:
            self.save_entry.delete(0, tk.END)
            self.save_entry.insert(0, d)

    def browse_csv(self):
        f = filedialog.askopenfilename(filetypes=[('CSV/XLSX Files', '*.csv;*.xlsx;*.xls'), ('All Files', '*.*')])
        if f:
            self.csv_entry.delete(0, tk.END)
            self.csv_entry.insert(0, f)
            self.load_table_from_file(f)

    def save_config(self, silent=False):
        cfg = {
            'driver_path': self.driver_entry.get().strip(),
            'save_dir': self.save_entry.get().strip(),
            'csv_file': self.csv_entry.get().strip(),
            'cookie': self.cookie_text.get('1.0', tk.END).strip(),
            'max_workers': self.threads_entry.get().strip() or '4'
        }
        try:
            if os.path.exists(CONFIG_PATH):
                with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
                    old = json.load(f)
                for key in ['last_success', 'download_history', 'last_update_time']:
                    if key in old:
                        cfg[key] = old[key]
        except Exception:
            pass
        try:
            with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
                json.dump(cfg, f, ensure_ascii=False, indent=2)
            if not silent:
                messagebox.showinfo('保存', '配置已保存到 config.json')
        except Exception as e:
            if not silent:
                messagebox.showerror('错误', f'保存配置失败: {e}')

    def load_config(self):
        if os.path.exists(CONFIG_PATH):
            try:
                with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
                    cfg = json.load(f)
                self.driver_entry.delete(0, tk.END)
                self.driver_entry.insert(0, cfg.get('driver_path', ''))
                self.save_entry.delete(0, tk.END)
                self.save_entry.insert(0, cfg.get('save_dir', ''))
                self.csv_entry.delete(0, tk.END)
                self.csv_entry.insert(0, cfg.get('csv_file', ''))
                self.cookie_text.delete('1.0', tk.END)
                self.cookie_text.insert('1.0', cfg.get('cookie', ''))
                self.threads_entry.delete(0, tk.END)
                self.threads_entry.insert(0, cfg.get('max_workers', '4'))
            except Exception:
                pass

    def auto_load_videodata_folder(self):
        folder = os.path.join(_get_base_dir(), 'videodata')
        if not os.path.isdir(folder):
            return
        candidates = []
        for fn in os.listdir(folder):
            if fn.lower().endswith(('.xlsx', '.xls', '.csv')):
                full = os.path.join(folder, fn)
                if os.path.isfile(full):
                    candidates.append(full)
        if not candidates:
            return
        candidates.sort(key=lambda p: os.path.getmtime(p), reverse=True)
        target = candidates[0]
        self.csv_entry.delete(0, tk.END)
        self.csv_entry.insert(0, target)
        self.load_table_from_file(target)
        self.append_log(f'已默认加载：{target}')

    def import_table_file(self):
        f = filedialog.askopenfilename(filetypes=[('CSV/XLSX Files', '*.csv;*.xlsx;*.xls'), ('All Files', '*.*')])
        if f:
            self.csv_entry.delete(0, tk.END)
            self.csv_entry.insert(0, f)
            self.load_table_from_file(f)

    def _clear_table(self):
        for iid in self.tree.get_children():
            self.tree.delete(iid)

    def _insert_course_row(self, course: dict, status='pending', message=''):
        values = (
            course.get('course_id', ''), course.get('lesson_id', ''), course.get('class_name', ''),
            course.get('lesson_name', ''), course.get('start_time', ''), status, message
        )
        return self.tree.insert('', tk.END, values=values, tags=(status,))

    def load_table_from_file(self, path):
        try:
            courses = self._load_courses_any(path)
        except Exception as e:
            messagebox.showerror('错误', f'读取失败: {e}')
            return
        self._clear_table()
        for c in courses:
            self._insert_course_row(c)
        self.append_log(f'已加载 {len(courses)} 条任务')

    def _load_courses_any(self, path):
        if path.lower().endswith('.csv'):
            return videodownloader.load_courses_from_csv(path)
        return self._load_courses_from_xlsx(path)

    def _load_courses_from_xlsx(self, path):
        import openpyxl
        wb = openpyxl.load_workbook(path, data_only=True)
        ws = wb.active
        rows = list(ws.iter_rows(values_only=True))
        if not rows:
            return []
        headers = [str(x).strip().lstrip('\ufeff') if x is not None else '' for x in rows[0]]
        out = []
        for r in rows[1:]:
            row = {headers[i]: ('' if i >= len(r) or r[i] is None else str(r[i]).strip()) for i in range(len(headers))}
            lesson_id = (row.get('课堂ID') or '').strip()
            if not lesson_id:
                continue
            out.append({
                'lesson_id': lesson_id,
                'course_id': (row.get('班级ID') or '').strip(),
                'lesson_name': (row.get('课堂名称') or '').strip(),
                'class_name': (row.get('班级名称') or '').strip(),
                'start_time': (row.get('开课时间') or '').strip(),
                'creation_time': (row.get('创建时间') or '').strip(),
            })
        return out

    def add_row_dialog(self):
        self._row_dialog('新增行')

    def edit_selected_row_dialog(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showwarning('提示', '请先选中一行')
            return
        iid = sel[0]
        vals = self.tree.item(iid, 'values')
        init = {'course_id': vals[0], 'lesson_id': vals[1], 'class_name': vals[2], 'lesson_name': vals[3], 'start_time': vals[4]}
        self._row_dialog('编辑行', iid=iid, init=init)

    def _row_dialog(self, title, iid=None, init=None):
        init = init or {}
        win = tk.Toplevel(self.root)
        win.title(title)
        win.configure(bg=BG_COLOR)
        self.center_window(win, 460, 320)
        frm = tk.Frame(win, bg=BG_COLOR, padx=18, pady=14)
        frm.pack(fill=tk.BOTH, expand=True)
        fields = [('班级ID(course_id)', 'course_id'), ('课堂ID(lesson_id)', 'lesson_id'), ('班级名称(class_name)', 'class_name'), ('课堂名称(lesson_name)', 'lesson_name'), ('开课时间(start_time)', 'start_time')]
        entries = {}
        for i, (label, key) in enumerate(fields):
            _make_label(frm, label, bg=BG_COLOR).grid(row=i, column=0, sticky='w', pady=8)
            e = _make_entry(frm, width=36)
            e.grid(row=i, column=1, sticky='we', pady=8)
            e.insert(0, init.get(key, ''))
            entries[key] = e
        frm.columnconfigure(1, weight=1)

        def on_ok():
            course = {k: entries[k].get().strip() for _, k in fields}
            if not course.get('course_id') or not course.get('lesson_id'):
                messagebox.showwarning('提示', '班级ID 和 课堂ID 为必填')
                return
            values = (course['course_id'], course['lesson_id'], course['class_name'], course['lesson_name'], course['start_time'], 'pending', '')
            if iid is None:
                self.tree.insert('', tk.END, values=values, tags=('pending',))
            else:
                self.tree.item(iid, values=values, tags=('pending',))
            win.destroy()

        btns = tk.Frame(frm, bg=BG_COLOR)
        btns.grid(row=len(fields), column=0, columnspan=2, pady=(18, 0), sticky='e')
        _make_btn(btns, '取消', win.destroy, style='secondary').pack(side=tk.RIGHT, padx=(8, 0))
        _make_btn(btns, '确定', on_ok, style='primary').pack(side=tk.RIGHT)

    def delete_selected_rows(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showwarning('提示', '请先选中要删除的行')
            return
        if not messagebox.askyesno('确认', f'确认删除选中的 {len(sel)} 行吗？'):
            return
        for iid in sel:
            self.tree.delete(iid)

    def set_row_status(self, course_index, status, message=''):
        iids = self.tree.get_children()
        if course_index <= 0 or course_index > len(iids):
            return
        iid = iids[course_index - 1]
        vals = list(self.tree.item(iid, 'values'))
        vals[5] = status
        vals[6] = message
        self.tree.item(iid, values=vals, tags=(status,))

    def collect_courses_from_table(self):
        courses = []
        for iid in self.tree.get_children():
            vals = self.tree.item(iid, 'values')
            courses.append({'course_id': vals[0], 'lesson_id': vals[1], 'class_name': vals[2], 'lesson_name': vals[3], 'start_time': vals[4]})
        return courses

    def append_log(self, msg):
        self.log_area.configure(state='normal')
        self.log_area.insert(tk.END, str(msg) + '\n')
        self.log_area.see(tk.END)
        self.log_area.configure(state='disabled')

    def flush_log_queue(self):
        try:
            while True:
                msg = self.log_q.get_nowait()
                if isinstance(msg, tuple) and msg and msg[0] == '__DONE__':
                    continue
                self.append_log(msg)
        except queue.Empty:
            pass
        self.root.after(200, self.flush_log_queue)

    def toggle_pause(self):
        if not hasattr(self, 'pause_event'):
            return
        if self.pause_event.is_set():
            self.pause_event.clear()
            self.pause_btn.config(text='暂停')
            self.append_log('已继续下载')
        else:
            self.pause_event.set()
            self.pause_btn.config(text='继续')
            self.append_log('已暂停下载')

    def stop_download(self):
        if not hasattr(self, 'stop_event'):
            return
        if not self._is_downloading:
            return

        self.stop_event.set()
        self.append_log('已发送停止信号，等待线程退出...')
        
        # 取消check_done的定时回调
        if hasattr(self, '_check_done_id') and self._check_done_id is not None:
            self.root.after_cancel(self._check_done_id)
            self._check_done_id = None
        
        # 重置暂停事件状态
        if hasattr(self, 'pause_event'):
            self.pause_event.clear()
            self.pause_btn.config(text='暂停')
        
        # 立即重置UI状态，不等线程退出
        self._is_downloading = False
        self.start_btn.config(state='normal')
        self.save_btn.config(state='normal')
        self.video_progress_var.set(0)
        self.video_progress_label.config(text='当前视频: 0% | 0.00 MB/s')
        self.total_progress_label.config(text='总进度: 0/0 | 成功 0 失败 0')
        self._progress_row1.pack_forget()
        self._progress_row2.pack_forget()
        self.total_items = 0
        self.success_count = 0
        self.fail_count = 0
        self._redraw_total_bar()
        
        # 延迟关闭driver，给下载线程一点时间退出
        def close_driver_later():
            if hasattr(self, 'driver_ref') and self.driver_ref:
                try:
                    driver = self.driver_ref.get('driver')
                    if driver is not None:
                        driver.quit()
                        self.driver_ref['driver'] = None
                        self.append_log('已关闭浏览器')
                except Exception as e:
                    self.append_log(f'关闭浏览器时出错: {e}')
            self.driver_ref = {}
        
        self.root.after(1000, close_driver_later)

    def _redraw_total_bar(self):
        try:
            w = int(self.total_canvas.winfo_width())
            h = int(self.total_canvas.winfo_height())
            if w <= 2 or h <= 2:
                return
            total = max(int(self.total_items or 0), 1)
            succ = min(max(int(self.success_count or 0), 0), total)
            fail = min(max(int(self.fail_count or 0), 0), total - succ)
            succ_w = int(w * (succ / total))
            fail_w = int(w * (fail / total))
            self.total_canvas.delete('all')
            self.total_canvas.create_rectangle(0, 0, w, h, fill='#E2E8F0', outline='#CBD5E0')
            if succ_w > 0:
                self.total_canvas.create_rectangle(0, 0, succ_w, h, fill=SUCCESS_COLOR, outline=SUCCESS_COLOR)
            if fail_w > 0:
                self.total_canvas.create_rectangle(succ_w, 0, succ_w + fail_w, h, fill=DANGER_COLOR, outline=DANGER_COLOR)
        except Exception:
            pass

    def update_progress(self, total_items, done_count, success_count, fail_count):
        try:
            self.total_items = max(self.total_items, int(total_items or 0))
            self.success_count = int(success_count or 0)
            self.fail_count = int(fail_count or 0)
            done = int(done_count or 0)
            self._progress_row1.pack(fill=tk.X)
            self._progress_row2.pack(fill=tk.X, pady=(6, 0))
            self.total_progress_label.config(text=f'总进度: {done}/{self.total_items} | 成功 {self.success_count} 失败 {self.fail_count}')
            self._redraw_total_bar()
        except Exception:
            pass

    def update_video_progress(self, percent, speed_mbps, info=''):
        try:
            self._progress_row1.pack(fill=tk.X)
            p = int(max(0, min(100, percent or 0)))
            self.video_progress_var.set(p)
            sp = float(speed_mbps or 0.0)
            text = f'当前视频: {p}% | {sp:.2f} MB/s'
            if info:
                text += f' | {info}'
            self.video_progress_label.config(text=text)
        except Exception:
            pass

    def get_cookie(self):
        cookie_file = os.path.join(tempfile.gettempdir(), 'classin_cookies.json')
        driver_path = self.driver_entry.get().strip() or os.path.join(_get_base_dir(), 'msedgedriver.exe')
        script = f'''import json\nimport time\nfrom selenium import webdriver\nfrom selenium.webdriver.edge.service import Service\nservice = Service(executable_path=r"{driver_path}")\ndriver = webdriver.Edge(service=service)\ndriver.get("https://www.eeo.cn/cn/login")\nprint("请登录后等待保存 cookie")\ntime.sleep(40)\ncookies = driver.get_cookies()\ndriver.quit()\nwith open(r"{cookie_file}", "w", encoding="utf-8") as f:\n    json.dump(cookies, f, ensure_ascii=False)\nprint("cookie 已保存")\n'''
        tmp_py = os.path.join(tempfile.gettempdir(), 'get_cookie_tmp.py')
        with open(tmp_py, 'w', encoding='utf-8') as f:
            f.write(script)
        try:
            subprocess.Popen([sys.executable, tmp_py], creationflags=subprocess.CREATE_NEW_CONSOLE if hasattr(subprocess, 'CREATE_NEW_CONSOLE') else 0)
        except Exception:
            subprocess.Popen([sys.executable, tmp_py])
        messagebox.showinfo('操作提示', '已弹出浏览器，请在新窗口登录后等待自动保存 Cookie。登录完成后点击“导入Cookie”按钮。')

        def import_cookie():
            if os.path.exists(cookie_file):
                try:
                    with open(cookie_file, 'r', encoding='utf-8') as f:
                        cookies = json.load(f)
                    cookie_str = '; '.join([f"{c['name']}={c['value']}" for c in cookies])
                    self.cookie_text.delete('1.0', tk.END)
                    self.cookie_text.insert('1.0', cookie_str)
                    messagebox.showinfo('成功', 'Cookie 已导入并填入文本框！')
                except Exception as e:
                    messagebox.showerror('错误', f'导入Cookie失败: {e}')
            else:
                messagebox.showwarning('未找到', '未检测到 cookie 文件，请确认已登录并等待脚本完成。')

        import_win = tk.Toplevel(self.root)
        import_win.title('导入 Cookie')
        import_win.configure(bg=BG_COLOR)
        self.center_window(import_win, 360, 140)
        tk.Label(import_win, text='登录完成后点击下方按钮导入 Cookie：', font=('Microsoft YaHei UI', 10), fg=TEXT_COLOR, bg=BG_COLOR).pack(padx=24, pady=20)
        _make_btn(import_win, '导入 Cookie', import_cookie, style='primary').pack(pady=(0, 20))

    def start_download(self):
        # 防止多次快速点击导致多个下载同时进行
        if hasattr(self, '_is_downloading') and self._is_downloading:
            messagebox.showwarning('提示', '下载正在进行中，请勿重复点击')
            return
        
        driver_path = self.driver_entry.get().strip() or None
        save_dir = self.save_entry.get().strip() or None
        csv_file = self.csv_entry.get().strip() or None
        cookie = self.cookie_text.get('1.0', tk.END).strip() or ''
        max_workers_str = self.threads_entry.get().strip() or '4'
        try:
            max_workers = max(1, min(8, int(max_workers_str)))
        except ValueError:
            max_workers = 4
            self.threads_entry.delete(0, tk.END)
            self.threads_entry.insert(0, '4')
        
        courses_override = self.collect_courses_from_table()
        if not courses_override:
            messagebox.showwarning('提示', '任务列表为空，请先导入或新增任务行')
            return
        self.save_config(silent=True)
        self.start_btn.config(state='disabled')
        self.save_btn.config(state='disabled')
        self._is_downloading = True
        self.total_items = len(courses_override)
        self.success_count = 0
        self.fail_count = 0
        self.update_progress(self.total_items, 0, 0, 0)
        self.update_video_progress(0, 0.0, '')

        def log_cb(msg):
            self.log_q.put(msg)

        self.pause_event = threading.Event()
        self.stop_event = threading.Event()
        self.driver_ref = {}
        self._download_session = getattr(self, '_download_session', 0) + 1

        def progress_cb(total_courses, current_course_index, course, video_index):
            try:
                if isinstance(video_index, dict):
                    self.root.after(0, lambda: self.update_video_progress(video_index.get('percent', 0), video_index.get('speed_mbps', 0.0), video_index.get('info', '')))
                    return
                done = self.success_count + self.fail_count
                self.root.after(0, lambda: self.update_progress(self.total_items or total_courses, done, self.success_count, self.fail_count))
            except Exception:
                pass

        def lesson_done_cb(info):
            try:
                cfg = {}
                if os.path.exists(CONFIG_PATH):
                    with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
                        cfg = json.load(f)
                cfg['last_success'] = {
                    'course_id': info.get('course_id'), 'lesson_id': info.get('lesson_id'),
                    'course_name': info.get('course_name'), 'class_name': info.get('class_name'),
                    'lesson_name': info.get('lesson_name'), 'total_videos': info.get('total_videos'),
                    'downloaded': info.get('downloaded'), 'course_row_index': info.get('course_row_index'),
                    'total_courses': info.get('total_courses'), 'timestamp': time.strftime('%Y-%m-%d %H:%M:%S')
                }
                with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
                    json.dump(cfg, f, ensure_ascii=False, indent=2)
            except Exception as e:
                log_cb(f'记录 last_success 失败: {e}')

        def target():
            try:
                def course_status_cb(course_index, course, status, message):
                    def _apply():
                        self.set_row_status(course_index, status, message)
                        if status == 'success':
                            self.success_count += 1
                        elif status == 'failed':
                            self.fail_count += 1
                        done = self.success_count + self.fail_count
                        self.update_progress(self.total_items, done, self.success_count, self.fail_count)
                    self.root.after(0, _apply)

                videodownloader.download_videos(save_dir, csv_file, cookie,
                                                driver_path=driver_path,
                                                headless=True,
                                                log_callback=log_cb,
                                                pause_event=self.pause_event,
                                                stop_event=self.stop_event,
                                                progress_callback=progress_cb,
                                                lesson_done_callback=lesson_done_cb,
                                                driver_ref=self.driver_ref,
                                                course_status_callback=course_status_cb,
                                                courses_override=courses_override,
                                                max_workers=max_workers)
                log_cb('全部任务完成')
            except Exception as e:
                log_cb(f'下载任务异常: {e}')
            finally:
                self.log_q.put(('__DONE__', self._download_session))

        threading.Thread(target=target, daemon=True).start()

        def check_done():
            try:
                while True:
                    msg = self.log_q.get_nowait()
                    if isinstance(msg, tuple) and msg[0] == '__DONE__':
                        if msg[1] == self._download_session:
                            self.start_btn.config(state='normal')
                            self.save_btn.config(state='normal')
                            self.driver_ref.clear()
                            self._is_downloading = False
                            self._check_done_id = None
                        return
                    self.append_log(msg)
            except queue.Empty:
                pass
            # 保存定时器ID，以便后续取消
            self._check_done_id = self.root.after(200, check_done)

        self._check_done_id = None
        self._check_done_id = self.root.after(200, check_done)


if __name__ == '__main__':
    root = tk.Tk()
    app = App(root)
    root.mainloop()
