import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import pandas as pd
import os
import sys
import subprocess
import threading
import re
from datetime import datetime

class PredictGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("保留时间预测工具 (本地版)")
        self.root.geometry("650x500")
        self.root.resizable(True, True)

        # 变量
        self.model_type = tk.StringVar(value="RP_6min")
        self.input_file = tk.StringVar()
        self.custom_model_dir = tk.StringVar()
        self.min_rt = tk.StringVar(value="0.0")
        self.max_rt = tk.StringVar(value="6.0")
        self.process = None
        self.running = False

        self.create_widgets()

    def create_widgets(self):
        # 主框架
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)

        # 1. 模型选择
        ttk.Label(main_frame, text="选择预测模型:").grid(row=0, column=0, sticky=tk.W, pady=5)
        model_frame = ttk.Frame(main_frame)
        model_frame.grid(row=0, column=1, columnspan=3, sticky=tk.W)
        ttk.Radiobutton(model_frame, text="RP_6min", variable=self.model_type, value="RP_6min", command=self.on_model_change).pack(side=tk.LEFT, padx=5)
        ttk.Radiobutton(model_frame, text="HILIC_6min", variable=self.model_type, value="HILIC_6min", command=self.on_model_change).pack(side=tk.LEFT, padx=5)
        ttk.Radiobutton(model_frame, text="自定义", variable=self.model_type, value="custom", command=self.on_model_change).pack(side=tk.LEFT, padx=5)

        # 自定义模型目录选择
        self.custom_frame = ttk.Frame(main_frame)
        self.custom_frame.grid(row=1, column=0, columnspan=4, sticky=tk.W+tk.E, pady=5)
        ttk.Label(self.custom_frame, text="模型目录:").pack(side=tk.LEFT, padx=(20,5))
        self.custom_dir_entry = ttk.Entry(self.custom_frame, textvariable=self.custom_model_dir, width=40, state="disabled")
        self.custom_dir_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        self.browse_btn = ttk.Button(self.custom_frame, text="浏览", command=self.browse_model_dir, state="disabled")
        self.browse_btn.pack(side=tk.LEFT, padx=5)
        self.custom_frame.grid_remove()  # 默认隐藏

        # 自定义 RT 范围
        rt_frame = ttk.Frame(main_frame)
        rt_frame.grid(row=2, column=0, columnspan=4, sticky=tk.W, pady=5)
        ttk.Label(rt_frame, text="保留时间下限:").pack(side=tk.LEFT, padx=5)
        self.min_entry = ttk.Entry(rt_frame, textvariable=self.min_rt, width=8, state="disabled")
        self.min_entry.pack(side=tk.LEFT, padx=5)
        ttk.Label(rt_frame, text="上限:").pack(side=tk.LEFT, padx=5)
        self.max_entry = ttk.Entry(rt_frame, textvariable=self.max_rt, width=8, state="disabled")
        self.max_entry.pack(side=tk.LEFT, padx=5)

        # 2. 输入文件选择
        ttk.Label(main_frame, text="输入 CSV 文件:").grid(row=3, column=0, sticky=tk.W, pady=10)
        ttk.Entry(main_frame, textvariable=self.input_file, width=50).grid(row=3, column=1, columnspan=2, sticky=tk.W+tk.E, padx=5)
        ttk.Button(main_frame, text="浏览", command=self.browse_input).grid(row=3, column=3, padx=5)

        # 3. 控制按钮
        btn_frame = ttk.Frame(main_frame)
        btn_frame.grid(row=4, column=0, columnspan=4, pady=10)
        self.run_btn = ttk.Button(btn_frame, text="开始预测", command=self.start_prediction)
        self.run_btn.pack(side=tk.LEFT, padx=5)
        self.cancel_btn = ttk.Button(btn_frame, text="取消", command=self.cancel_prediction, state=tk.DISABLED)
        self.cancel_btn.pack(side=tk.LEFT, padx=5)

        # 4. 进度条
        self.progress = ttk.Progressbar(main_frame, mode='indeterminate')
        self.progress.grid(row=5, column=0, columnspan=4, sticky=tk.EW, pady=5)
        self.progress.grid_remove()

        # 5. 日志输出文本框
        log_frame = ttk.LabelFrame(main_frame, text="运行日志", padding="5")
        log_frame.grid(row=6, column=0, columnspan=4, sticky=tk.NSEW, pady=5)
        main_frame.rowconfigure(6, weight=1)
        main_frame.columnconfigure(1, weight=1)

        self.log_text = tk.Text(log_frame, height=12, wrap=tk.WORD, state=tk.DISABLED)
        scrollbar = ttk.Scrollbar(log_frame, orient=tk.VERTICAL, command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=scrollbar.set)
        self.log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # 状态栏
        self.status_var = tk.StringVar(value="就绪")
        ttk.Label(self.root, textvariable=self.status_var, relief=tk.SUNKEN, anchor=tk.W).pack(fill=tk.X, side=tk.BOTTOM)

    def on_model_change(self):
        if self.model_type.get() == "custom":
            self.custom_frame.grid()
            self.min_entry.config(state="normal")
            self.max_entry.config(state="normal")
            self.custom_dir_entry.config(state="normal")
            self.browse_btn.config(state="normal")
        else:
            self.custom_frame.grid_remove()
            self.min_entry.config(state="disabled")
            self.max_entry.config(state="disabled")
            self.custom_dir_entry.config(state="disabled")
            self.browse_btn.config(state="disabled")
            # 重置默认值
            self.min_rt.set("0.0")
            self.max_rt.set("6.0")

    def browse_model_dir(self):
        dir_path = filedialog.askdirectory(title="选择模型目录（包含model_config.json）")
        if dir_path:
            self.custom_model_dir.set(dir_path)

    def browse_input(self):
        filename = filedialog.askopenfilename(
            title="选择输入CSV文件",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")]
        )
        if filename:
            self.input_file.set(filename)

    def check_csv_column(self, path):
        try:
            for enc in ("utf-8-sig", "gbk", "utf-8"):
                try:
                    df = pd.read_csv(path, nrows=0, encoding=enc)
                    return 'IsomericSMILES' in df.columns
                except (UnicodeDecodeError, UnicodeError):
                    continue
        except Exception:
            return False
        return False

    def get_output_filename(self):
        input_path = self.input_file.get()
        base, ext = os.path.splitext(input_path)
        if self.model_type.get() == "custom":
            model_dir = os.path.basename(self.custom_model_dir.get().rstrip(os.sep))
            suffix = f"_{model_dir}_{self.min_rt.get()}-{self.max_rt.get()}_predict"
        else:
            suffix = f"_{self.model_type.get()}_predict"
        return base + suffix + ext

    def start_prediction(self):
        # 验证输入
        if not self.input_file.get():
            messagebox.showerror("错误", "请选择输入CSV文件")
            return
        if not os.path.exists(self.input_file.get()):
            messagebox.showerror("错误", "文件不存在")
            return
        if not self.check_csv_column(self.input_file.get()):
            messagebox.showerror("错误", "CSV文件必须包含 'IsomericSMILES' 列")
            return

        # 确定模型目录
        if self.model_type.get() == "custom":
            model_dir = self.custom_model_dir.get().strip()
            if not model_dir:
                messagebox.showerror("错误", "请选择自定义模型目录")
                return
            if not os.path.exists(os.path.join(model_dir, "model_config.json")):
                messagebox.showerror("错误", "模型目录必须包含 model_config.json 文件")
                return
            min_rt = self.min_rt.get()
            max_rt = self.max_rt.get()
            try:
                float(min_rt)
                float(max_rt)
            except ValueError:
                messagebox.showerror("错误", "保留时间上下限必须是数字")
                return
        else:
            # 确定内置模型目录（兼容打包后的路径）
            if getattr(sys, 'frozen', False):
                base_dir = sys._MEIPASS  # PyInstaller 临时解压目录
            else:
                base_dir = os.path.dirname(os.path.abspath(__file__))
            model_dir = os.path.join(base_dir, f"AttentiveModel_{self.model_type.get()}")
            if not os.path.exists(model_dir):
                # 若不在内嵌资源中，尝试与exe同级目录
                model_dir = os.path.join(os.path.dirname(sys.executable) if getattr(sys, 'frozen', False) else base_dir,
                                         f"AttentiveModel_{self.model_type.get()}")
            min_rt = "0.0"
            max_rt = "6.0"

        # 检查模型目录有效性
        if not os.path.exists(model_dir):
            messagebox.showerror("错误", f"模型目录不存在: {model_dir}")
            return

        # 输出文件名
        output_file = self.get_output_filename()
        error_file = output_file.replace(".csv", "_errors.csv")

        # 禁用控件
        self.run_btn.config(state=tk.DISABLED)
        self.cancel_btn.config(state=tk.NORMAL)
        self.progress.grid()
        self.progress.start()
        self.clear_log()
        self.log("="*60)
        self.log("开始预测任务")
        self.log(f"输入文件: {self.input_file.get()}")
        self.log(f"模型目录: {model_dir}")
        self.log(f"RT 范围: [{min_rt}, {max_rt}]")
        self.log(f"输出文件: {output_file}")
        self.log("="*60)
        self.status_var.set("预测中...")

        # 构建命令行参数
        script_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "predict.py")
        if not os.path.exists(script_path):
            # 尝试在打包后内嵌资源中找
            if getattr(sys, 'frozen', False):
                script_path = os.path.join(sys._MEIPASS, "predict.py")
        cmd = [
            sys.executable,  # 使用当前 Python 解释器（打包后 exe 本身可以执行脚本？实际上 --onefile 后没有 python 环境，需特殊处理）
            script_path,
            "--input_file", self.input_file.get(),
            "--output_file", output_file,
            "--error_file", error_file,
            "--model_dir", model_dir,
            "--min_rt", min_rt,
            "--max_rt", max_rt,
        ]

        # 注意：如果打包为单个 exe，使用 sys.executable 会调用 exe 自身，而不是 python 解释器，无法执行 predict.py。
        # 解决方案：将 predict.py 作为数据文件打包，然后在代码中 import predict 并调用函数，这样无需子进程。
        # 但为了进度捕获，还是采用子进程，但需要打包时包含 python 环境？不行。
        # 因此我们改用直接调用模块函数，并重定向 stdout 到 GUI。

        # 改为直接调用模块，通过线程执行，捕获 print 输出。
        self.run_prediction_thread(model_dir, min_rt, max_rt, output_file, error_file)

    def run_prediction_thread(self, model_dir, min_rt, max_rt, output_file, error_file):
        """在后台线程中执行预测（直接调用 predict.py 中的函数）"""
        import predict
        import io
        from contextlib import redirect_stdout, redirect_stderr

        def task():
            try:
                # 构造 args 对象
                class Args:
                    pass
                args = Args()
                args.input_file = self.input_file.get()
                args.output_file = output_file
                args.error_file = error_file
                args.model_dir = model_dir
                args.smiles_column = "IsomericSMILES"
                args.output_column = "Predicted_RT"
                args.min_rt = float(min_rt)
                args.max_rt = float(max_rt)
                args.batch_size = 10

                # 重定向 stdout/stderr 到我们的日志框
                log_stream = io.StringIO()
                with redirect_stdout(log_stream), redirect_stderr(log_stream):
                    predict.main(args)

                # 将捕获的输出添加到日志
                self.root.after(0, lambda: self.append_log(log_stream.getvalue()))

                self.root.after(0, self.on_prediction_finished, True, output_file)
            except Exception as e:
                import traceback
                err_msg = traceback.format_exc()
                self.root.after(0, lambda: self.log(f"错误:\n{err_msg}"))
                self.root.after(0, self.on_prediction_finished, False, None)

        threading.Thread(target=task, daemon=True).start()

    def on_prediction_finished(self, success, output_file):
        self.progress.stop()
        self.progress.grid_remove()
        self.run_btn.config(state=tk.NORMAL)
        self.cancel_btn.config(state=tk.DISABLED)
        if success:
            self.status_var.set("预测完成")
            self.log(f"结果已保存至: {output_file}")
            messagebox.showinfo("完成", f"预测成功！\n结果文件:\n{output_file}")
        else:
            self.status_var.set("预测失败")
            messagebox.showerror("失败", "预测过程中发生错误，请查看日志。")

    def cancel_prediction(self):
        if self.process and self.process.poll() is None:
            self.process.terminate()
        self.status_var.set("已取消")
        self.log("用户取消了预测。")
        self.on_prediction_finished(False, None)

    def log(self, message):
        self.log_text.config(state=tk.NORMAL)
        self.log_text.insert(tk.END, message + "\n")
        self.log_text.see(tk.END)
        self.log_text.config(state=tk.DISABLED)

    def append_log(self, text):
        self.log_text.config(state=tk.NORMAL)
        self.log_text.insert(tk.END, text)
        self.log_text.see(tk.END)
        self.log_text.config(state=tk.DISABLED)

    def clear_log(self):
        self.log_text.config(state=tk.NORMAL)
        self.log_text.delete(1.0, tk.END)
        self.log_text.config(state=tk.DISABLED)


if __name__ == "__main__":
    root = tk.Tk()
    app = PredictGUI(root)
    root.mainloop()