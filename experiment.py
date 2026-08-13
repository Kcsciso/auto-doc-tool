# region 库文件
import ctypes
import inspect
import re
import threading
import time
import cv2
import numpy as np
from yolov5 import *
from PyQt5.QtCore import QRegExp, QObject, pyqtSignal
from PyQt5.QtGui import QStandardItem, QStandardItemModel, QRegExpValidator, QIntValidator, QPixmap, QImage
from UI_modify import Windows_modify
import sys
from PyQt5.QtWidgets import *
from Five_Robot_Control import *
from PyQt5 import QtCore, QtGui, QtWidgets
from calibration import *
from Five_Robot_kinematics import *
from PyQt5.QtGui import QColor

# 语音识别相关库
import queue
import pygame
import sounddevice as sd
import wavio as wv
from rapid_paraformer import RapidParaformer
import os
# endregion

# region 全局变量
global image
global shap_count_circles
shap_count_circles = 0
global shape_count_square
shape_count_square = 0
global result
result = []
global bool_IsSend
bool_IsSend = False
global clip_close_degree  # 夹爪关闭值
clip_close_degree = 73
# endregion

# region 实例化对象
blinx_model_path = 'best.onnx'
robot_control = Blinx_Five_Robot_Control()
calibration = Blinx_Cam_Calibration()
five_robot_kinematics = Blinx_Five_Robot_kinematics()
object_recognition = BLINX_YOLOV5_70(blinx_model_path)
# endregion

# region 语音识别类（无唤醒，支持“分类”命令）
class PipelineSpeechRecognizer(QObject):
    fruit_command = pyqtSignal(str)
    classify_all = pyqtSignal()
    finished = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.config_path = "config.yaml"
        self.paraformer = RapidParaformer(self.config_path)
        self.running = True
        self.sample_rate = 16000
        self.record_duration = 2.5
        self.temp_file = "recording.wav"
        self.audio_queue = queue.Queue(maxsize=3)
        self.result_queue = queue.Queue()
        self.can_record = True
        self.fruit_map = {
            "西瓜": "watermelon",
            "黄瓜": "cucumber",
            "香蕉": "banana",
            "西红柿": "tomato"
        }
        self.exit_close = "退出"
        self.classify_cmd = "分类"
        pygame.mixer.init()

    def audio_producer(self):
        while self.running and self.can_record:
            try:
                audio = sd.rec(
                    int(self.record_duration * self.sample_rate),
                    samplerate=self.sample_rate,
                    channels=1,
                    dtype='int16'
                )
                sd.wait()
                wv.write(self.temp_file, audio, self.sample_rate, sampwidth=2)
                self.audio_queue.put(self.temp_file, timeout=2)
                if self.audio_queue.full():
                    self.can_record = False
            except queue.Full:
                time.sleep(0.5)
            except Exception:
                time.sleep(1)

    def audio_consumer(self):
        while self.running:
            try:
                audio_file = self.audio_queue.get(timeout=1)
                result = self.paraformer(audio_file)
                if result and result[0]:
                    text = result[0]
                    # 退出命令
                    if self.exit_close in text:
                        print("关闭语音识别")
                        self.running = False
                        self.finished.emit()
                        try:
                            if os.path.exists("quit.wav"):
                                pygame.mixer.music.load("quit.wav")
                                pygame.mixer.music.play()
                        except:
                            pass
                    # 分类全部命令（优先级高于单个水果）
                    elif self.classify_cmd in text:
                        print("识别到“分类”命令，即将分拣所有水果")
                        self.classify_all.emit()
                        try:
                            pygame.mixer.music.load("ok.wav")
                            pygame.mixer.music.play()
                        except:
                            pass
                    # 单个水果命令
                    else:
                        for cn_name, en_name in self.fruit_map.items():
                            if cn_name in text:
                                print(f"识别到水果：{cn_name}")
                                self.fruit_command.emit(en_name)
                                try:
                                    pygame.mixer.music.load("ok.wav")
                                    pygame.mixer.music.play()
                                except:
                                    pass
                                break
                try:
                    os.remove(audio_file)
                except:
                    pass
                self.audio_queue.task_done()
                if not self.can_record and self.audio_queue.qsize() < 2:
                    self.can_record = True
            except queue.Empty:
                if not self.running:
                    break
                continue
            except Exception:
                time.sleep(0.1)

    def start(self):
        # 确保每次启动都能正常循环
        self.running = True
        producer = threading.Thread(target=self.audio_producer, daemon=True)
        consumer = threading.Thread(target=self.audio_consumer, daemon=True)
        producer.start()
        time.sleep(0.5)
        consumer.start()
        try:
            while self.running:
                try:
                    if self.result_queue.get(timeout=0.5) == "EXIT":
                        break
                except queue.Empty:
                    pass
                if not producer.is_alive() or not consumer.is_alive():
                    print("语音线程异常退出")
                    break
                time.sleep(0.1)
        except KeyboardInterrupt:
            self.running = False
        finally:
            producer.join(timeout=2)
            consumer.join(timeout=2)
            while not self.audio_queue.empty():
                try:
                    file = self.audio_queue.get_nowait()
                    if os.path.exists(file):
                        os.remove(file)
                except:
                    pass
            pygame.mixer.quit()
            if os.path.exists(self.temp_file):
                try:
                    os.remove(self.temp_file)
                except:
                    pass
# endregion

# region 机械臂主窗口
class Blinx_Five_Robot_Arm(Windows_modify):
    # 定义抓取完成信号
    pick_finished = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.setupUi(self)
        self.setFixedSize(self.width(), self.height())
        self.blinx_btn_ini(False)
        self.blinx_btn_enable_on.setEnabled(False)
        self.blinx_btn_enable_on.setVisible(False)
        self.blinx_btn_enable_off.setEnabled(False)
        self.blinx_btn_enable_off.setVisible(True)
        self.is_button = False
        self.blinx_btn_reduce.clicked.connect(self.showMinimized)
        self.blinx_btn_close_top.clicked.connect(self.close)
        self.blinx_btn_camera.clicked.connect(self.blinx_open_camera)
        self.blinx_lineEdit_step.setValidator(QIntValidator(1, 240))
        self.Speed.setMinimum(1)
        self.Speed.setMaximum(100)
        self.timer_camera = QtCore.QTimer()
        self.thread_send = threading.Thread(target=self.send_data)
        self.thread_send.start()

        # 语音识别器
        self.speech_recognizer = PipelineSpeechRecognizer()
        self.speech_recognizer.fruit_command.connect(self.on_fruit_command)
        self.speech_recognizer.classify_all.connect(self.on_classify_all)
        self.speech_recognizer.finished.connect(self.on_speech_finished)
        self.speech_thread = None
        self.is_busy = False
        self.speech_was_running = False          # 记录抓取前语音是否在运行
        self.speech_disabled_by_user = False     # 用户是否手动关闭了语音

        # 抓取完成信号连接
        self.pick_finished.connect(self.on_pick_finished)
        self.blinx_slot_init()

    # ---------- 暂停与恢复语音识别的辅助方法 ----------
    def _stop_speech_temp(self):
        """临时暂停语音识别（不改变speech_disabled_by_user）"""
        if self.speech_recognizer.running:
            self.speech_recognizer.running = False
        if self.speech_thread and self.speech_thread.is_alive():
            self.speech_thread.join(timeout=2)
        self.speech_thread = None

    def _start_speech_temp(self):
        """恢复语音识别（仅在未被用户手动关闭时启动）"""
        if not self.speech_disabled_by_user:
            self.speech_recognizer.running = True
            self.speech_thread = threading.Thread(
                target=self.speech_recognizer.start, daemon=True
            )
            self.speech_thread.start()

    def _restore_after_early_return(self):
        """提前返回时恢复语音和相机"""
        self.is_busy = False
        if self.speech_was_running:
            self._start_speech_temp()
            self.timer_camera.start(30)

    # ---------- 原有UI方法（未改动的部分保留原样） ----------
    def blinx_slot_init(self):
        self.blinx_btn_reduce.clicked.connect(self.blinx_btn_reduce_click)
        self.blinx_btn_zero.clicked.connect(self.blinx_btn_zero_click)
        self.blinx_btn_start.clicked.connect(self.blinx_btn_start_click)
        self.blinx_btn_j1_add.clicked.connect(self.blinx_btn_j1_add_click)
        self.blinx_btn_j1_subtract.clicked.connect(self.blinx_btn_j1_subtract_click)
        self.blinx_btn_j2_add.clicked.connect(self.blinx_btn_j2_add_click)
        self.blinx_btn_j2_subtract.clicked.connect(self.blinx_btn_j2_subtract_click)
        self.blinx_btn_j3_add.clicked.connect(self.blinx_btn_j3_add_click)
        self.blinx_btn_j3_subtract.clicked.connect(self.blinx_btn_j3_subtract_click)
        self.blinx_btn_j4_add.clicked.connect(self.blinx_btn_j4_add_click)
        self.blinx_btn_j4_subtract.clicked.connect(self.blinx_btn_j4_subtract_click)
        self.blinx_btn_clip_open.clicked.connect(self.blinx_btn_clip_open_click)
        self.blinx_btn_clip_close.clicked.connect(self.blinx_btn_clip_close_click)
        self.blinx_btn_enable_on.clicked.connect(self.blinx_enable_change)
        self.blinx_btn_enable_off.clicked.connect(self.blinx_enable_change)
        self.blinx_btn_open_detection.clicked.connect(self.blinx_btn_open_detection_click)
        self.blinx_btn_close_detection.clicked.connect(self.blinx_btn_close_detection_click)
        self.timer_camera.timeout.connect(self.show_camera)

    def blinx_btn_ini(self, bool):
        self.blinx_btn_zero.setEnabled(bool)
        self.blinx_btn_j1_add.setEnabled(bool)
        self.blinx_btn_j1_subtract.setEnabled(bool)
        self.blinx_btn_j2_add.setEnabled(bool)
        self.blinx_btn_j2_subtract.setEnabled(bool)
        self.blinx_btn_j3_add.setEnabled(bool)
        self.blinx_btn_j3_subtract.setEnabled(bool)
        self.blinx_btn_j4_add.setEnabled(bool)
        self.blinx_btn_j4_subtract.setEnabled(bool)
        self.blinx_lineEdit_step.setEnabled(bool)
        self.blinx_btn_clip_open.setEnabled(bool)
        self.blinx_btn_clip_close.setEnabled(bool)
        self.blinx_btn_open_detection.setEnabled(bool)
        self.blinx_btn_close_detection.setEnabled(bool)
        self.Speed.setEnabled(bool)
        self.blinx_label_j1.setEnabled(bool)
        self.blinx_label_j2.setEnabled(bool)
        self.blinx_label_j3.setEnabled(bool)
        self.blinx_label_j4.setEnabled(bool)

    def blinx_enable_change(self):
        if not self.is_button:
            self.is_button = True
            self.blinx_btn_enable_off.setEnabled(False)
            self.blinx_btn_enable_off.setVisible(False)
            self.blinx_btn_enable_on.setEnabled(True)
            self.blinx_btn_enable_on.setVisible(True)
            self.blinx_btn_ini(True)
            robot_control.bus_servo_niuju_on(0xfe)
            degree = robot_control.bus_servo_get_all()
            if degree[0] <= 260:
                self.blinx_label_j1.setText(str(degree[0]))
                self.blinx_label_j2.setText(str(degree[1]))
                self.blinx_label_j3.setText(str(degree[2]))
                self.blinx_label_j4.setText(str(degree[3]))
        else:
            self.is_button = False
            self.blinx_btn_enable_off.setEnabled(True)
            self.blinx_btn_enable_off.setVisible(True)
            self.blinx_btn_enable_on.setEnabled(False)
            self.blinx_btn_enable_on.setVisible(False)
            self.blinx_btn_ini(False)
            robot_control.bus_servo_niuju_off(0xfe)

    def blinx_btn_reduce_click(self):
        self.is_button = False
        self.blinx_btn_enable_off.setEnabled(False)
        self.blinx_btn_enable_off.setVisible(True)
        self.blinx_btn_enable_on.setEnabled(False)
        self.blinx_btn_enable_on.setVisible(False)
        self.blinx_btn_ini(False)
        robot_control.bus_pwr_off()

    def blinx_btn_zero_click(self):
        wait_point = [30, 45, 182, 219, 0, 2000]
        robot_control.bus_servo_all(wait_point[0], wait_point[1], wait_point[2], wait_point[3],
                                    wait_point[4], wait_point[5])
        self.blinx_label_j1.setText(str(wait_point[0]))
        self.blinx_label_j2.setText(str(wait_point[1]))
        self.blinx_label_j3.setText(str(wait_point[2]))
        self.blinx_label_j4.setText(str(wait_point[3]))

    def blinx_btn_start_click(self):
        robot_control.bus_servo_pwr_on()
        self.blinx_btn_enable_off.setEnabled(True)

    # 关节控制（保留原逻辑不变）
    def blinx_btn_j1_add_click(self):
        degree = int(self.blinx_label_j1.text()) + int(self.blinx_lineEdit_step.text())
        if degree <= 240:
            robot_control.bus_servo(1, degree, int(self.Speed.value()))
            self.blinx_label_j1.setText(str(degree))
    def blinx_btn_j1_subtract_click(self):
        degree = int(self.blinx_label_j1.text()) - int(self.blinx_lineEdit_step.text())
        if degree >= 0:
            robot_control.bus_servo(1, degree, int(self.Speed.value()))
            self.blinx_label_j1.setText(str(degree))
    def blinx_btn_j2_add_click(self):
        degree = int(self.blinx_label_j2.text()) + int(self.blinx_lineEdit_step.text())
        if degree <= 216:
            robot_control.bus_servo(2, degree, int(self.Speed.value()))
            self.blinx_label_j2.setText(str(degree))
    def blinx_btn_j2_subtract_click(self):
        degree = int(self.blinx_label_j2.text()) - int(self.blinx_lineEdit_step.text())
        if degree >= 24:
            robot_control.bus_servo(2, degree, int(self.Speed.value()))
            self.blinx_label_j2.setText(str(degree))
    def blinx_btn_j3_add_click(self):
        degree = int(self.blinx_label_j3.text()) + int(self.blinx_lineEdit_step.text())
        if degree <= 240:
            robot_control.bus_servo(3, degree, int(self.Speed.value()))
            self.blinx_label_j3.setText(str(degree))
    def blinx_btn_j3_subtract_click(self):
        degree = int(self.blinx_label_j3.text()) - int(self.blinx_lineEdit_step.text())
        if degree >= 16:
            robot_control.bus_servo(3, degree, int(self.Speed.value()))
            self.blinx_label_j3.setText(str(degree))
    def blinx_btn_j4_add_click(self):
        degree = int(self.blinx_label_j4.text()) + int(self.blinx_lineEdit_step.text())
        if degree <= 240:
            robot_control.bus_servo(4, degree, int(self.Speed.value()))
            self.blinx_label_j4.setText(str(degree))
    def blinx_btn_j4_subtract_click(self):
        degree = int(self.blinx_label_j4.text()) - int(self.blinx_lineEdit_step.text())
        if degree >= 10:
            robot_control.bus_servo(4, degree, int(self.Speed.value()))
            self.blinx_label_j4.setText(str(degree))
    def blinx_btn_clip_open_click(self):
        robot_control.bus_servo(5, 0, int(self.Speed.value()))
    def blinx_btn_clip_close_click(self):
        robot_control.bus_servo(5, 100, int(self.Speed.value()))

    # 相机相关
    def blinx_open_camera(self):
        if not self.timer_camera.isActive():
            self.camera_idex = int(self.Camera_idex.currentText()[2])
            self.cap = cv2.VideoCapture(self.camera_idex)
            ret, image = self.cap.read()
            flag = self.cap.open(self.camera_idex)
            if not flag:
                QMessageBox.warning(self, u"Warning", u"请检测相机与电脑是否连接正确",
                                    buttons=QMessageBox.Ok, defaultButton=QMessageBox.Ok)
            else:
                self.timer_camera.start(30)
        else:
            self.timer_camera.stop()
            self.camera_idex = int(self.Camera_idex.currentText()[2])
            self.cap = cv2.VideoCapture(self.camera_idex)
            ret, image = self.cap.read()
            flag = self.cap.open(self.camera_idex)
            if not flag:
                QMessageBox.warning(self, u"Warning", u"请检测相机与电脑是否连接正确",
                                    buttons=QMessageBox.Ok, defaultButton=QMessageBox.Ok)
            else:
                self.timer_camera.start(30)

    def show_camera(self):
        global image
        flag, self.image = self.cap.read()
        show = cv2.cvtColor(self.image, cv2.COLOR_BGR2RGB)
        showImage = QImage(show.data, show.shape[1], show.shape[0], QImage.Format_RGB888)
        self.Image_show.setPixmap(QPixmap.fromImage(showImage))
        self.Image_show.setScaledContents(True)

    # ---------- 开启与关闭检测（修改后） ----------
    def blinx_btn_open_detection_click(self):
        if self.timer_camera.isActive():
            self.timer_camera.stop()
        self.blinx_btn_open_detection.setEnabled(False)
        self.blinx_btn_close_detection.setEnabled(True)
        self.speech_disabled_by_user = False          # 标记为主动开启
        if self.speech_thread is None or not self.speech_thread.is_alive():
            self.speech_recognizer.running = True
            self.speech_thread = threading.Thread(
                target=self.speech_recognizer.start, daemon=True
            )
            self.speech_thread.start()
            QMessageBox.information(self, "提示", "语音识别已启动，请说出水果名称（香蕉/西红柿/西瓜/黄瓜）或“分类”。")
        else:
            QMessageBox.warning(self, "提示", "语音识别已在运行中。")

    def blinx_btn_close_detection_click(self):
        self.speech_disabled_by_user = True            # 用户手动关闭
        if self.speech_recognizer.running:
            self.speech_recognizer.running = False
        if self.speech_thread and self.speech_thread.is_alive():
            self.speech_thread.join(timeout=2)
        self.speech_thread = None
        self.blinx_btn_ini(True)
        degree = robot_control.bus_servo_get_all()
        if degree[0] <= 260:
            self.blinx_label_j1.setText(str(degree[0]))
            self.blinx_label_j2.setText(str(degree[1]))
            self.blinx_label_j3.setText(str(degree[2]))
            self.blinx_label_j4.setText(str(degree[3]))
        self.blinx_btn_open_detection.setEnabled(True)
        self.blinx_btn_close_detection.setEnabled(False)
        if not self.timer_camera.isActive():
            self.timer_camera.start(30)

    def send_data(self):
        try:
            while True:
                time.sleep(0.1)
                global bool_IsSend, result
                if bool_IsSend:
                    bool_IsSend = False
                    self.robot_pick(int(result[0]), int(result[1]))
                    self.blinx_btn_close_detection.setEnabled(True)
        except Exception as e:
            print("数据发送线程：", e)

    # ---------- 单个水果抓取（已修改） ----------
    def on_fruit_command(self, fruit):
        if self.is_busy:
            return
        self.is_busy = True
        # 记录语音状态并暂停
        self.speech_was_running = (self.speech_recognizer.running and
                                   not self.speech_disabled_by_user)
        if self.speech_was_running:
            self._stop_speech_temp()
            self.timer_camera.stop()
        try:
            time.sleep(0.2)
            ret, frame = self.cap.read()
            if not ret:
                QMessageBox.warning(self, "错误", "无法获取相机图像")
                self._restore_after_early_return()
                return

            img, detections = object_recognition.detect_result(frame)

            if detections and not isinstance(detections[0], list):
                detections = [detections]

            # 显示检测结果图（确保显示带标注的图像）
            show = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
            show = np.ascontiguousarray(show)
            h, w, ch = show.shape
            qimg = QImage(show.data, w, h, w * ch, QImage.Format_RGB888)
            self.Image_show.setPixmap(QPixmap.fromImage(qimg))
            self.Image_show.setScaledContents(True)

            target = None
            for det in detections:
                if len(det) >= 3 and det[2] == fruit:
                    target = det
                    break
            if target:
                x, y = int(target[0]), int(target[1])
                global result
                result = [x, y, fruit]
                # 后台抓取
                threading.Thread(target=self._execute_pick, args=(x, y), daemon=True).start()
            else:
                QMessageBox.warning(self, "未找到", f"画面中没有找到 {fruit}")
                self._restore_after_early_return()
        except Exception as e:
            print("on_fruit_command 异常:", e)
            QMessageBox.warning(self, "错误", f"抓取失败: {e}")
            self._restore_after_early_return()

    # ---------- 全部分类抓取（已修改） ----------
    def on_classify_all(self):
        if self.is_busy:
            return
        self.is_busy = True
        self.speech_was_running = (self.speech_recognizer.running and
                                   not self.speech_disabled_by_user)
        if self.speech_was_running:
            self._stop_speech_temp()
            self.timer_camera.stop()
        try:
            time.sleep(0.2)
            ret, frame = self.cap.read()
            if not ret:
                QMessageBox.warning(self, "错误", "无法获取相机图像")
                self._restore_after_early_return()
                return

            img, detections = object_recognition.detect_result(frame)
            if detections and not isinstance(detections[0], list):
                detections = [detections]
            if not detections:
                QMessageBox.information(self, "提示", "画面中没有检测到任何水果")
                self._restore_after_early_return()
                return

            # 显示检测结果图
            show = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
            show = np.ascontiguousarray(show)
            h, w, ch = show.shape
            qimg = QImage(show.data, w, h, w * ch, QImage.Format_RGB888)
            self.Image_show.setPixmap(QPixmap.fromImage(qimg))
            self.Image_show.setScaledContents(True)

            # 后台顺序抓取
            threading.Thread(target=self._execute_pick_all, args=(detections,), daemon=True).start()
        except Exception as e:
            print("on_classify_all 异常:", e)
            QMessageBox.warning(self, "错误", f"分类抓取失败: {e}")
            self._restore_after_early_return()

    # ---------- 后台抓取线程 ----------
    def _execute_pick(self, x, y):
        """后台线程：单个抓取"""
        try:
            self.robot_pick(x, y)
        except Exception as e:
            print("抓取线程异常:", e)
        finally:
            self.pick_finished.emit()

    def _execute_pick_all(self, detections):
        """后台线程：按顺序抓取所有目标"""
        order = ['watermelon', 'cucumber', 'banana', 'tomato']
        try:
            for fruit in order:
                for det in detections:
                    if det[2] == fruit:
                        x, y = int(det[0]), int(det[1])
                        global result
                        result = [x, y, fruit]
                        print(f"抓取 {fruit} ({x},{y})")
                        self.robot_pick(x, y)
        except Exception as e:
            print("批量抓取线程异常:", e)
        finally:
            self.pick_finished.emit()

    # ---------- 抓取完成后的处理（已修改） ----------
    def on_pick_finished(self):
        """主线程：抓取完成后恢复状态"""
        self.is_busy = False
        # 如果之前语音在运行且用户未手动关闭，则恢复语音和相机
        if self.speech_was_running and not self.speech_disabled_by_user:
            self._start_speech_temp()
            self.timer_camera.start(30)
        # 重置状态位，避免被重复利用
        self.speech_was_running = False

    def on_speech_finished(self):
        if self.speech_thread and self.speech_thread.is_alive():
            self.speech_thread.join(timeout=2)
        self.speech_thread = None
        self.blinx_btn_ini(True)
        degree = robot_control.bus_servo_get_all()
        if degree[0] <= 260:
            self.blinx_label_j1.setText(str(degree[0]))
            self.blinx_label_j2.setText(str(degree[1]))
            self.blinx_label_j3.setText(str(degree[2]))
            self.blinx_label_j4.setText(str(degree[3]))
        self.blinx_btn_open_detection.setEnabled(True)
        self.blinx_btn_close_detection.setEnabled(False)
        if not self.timer_camera.isActive():
            self.timer_camera.start(30)

    # 机械臂抓取（固定点位，保持不变）
    def robot_pick(self, pixel_x, pixel_y):
        if pixel_x < 1131 and pixel_y < 565:
            angles = [26, 71, 197, 214]    # 1号
            print("抓取点位：1号")
        elif pixel_x > 1131 and pixel_y < 565:
            angles = [66, 91, 177, 224]     # 2号
            print("抓取点位：2号")
        elif pixel_x < 1131 and pixel_y > 565:
            angles = [31, 116, 172, 199]   # 3号
            print("抓取点位：3号")
        elif pixel_x > 1131 and pixel_y > 565:
            angles = [52, 151, 122, 224]   # 4号
            print("抓取点位：4号")
        else:
            angles = [26, 71, 197, 214]
            print("抓取点位：边界，默认1号")

        arr1, arr2, arr3, arr4 = angles[0], angles[1], angles[2], angles[3]

        robot_control.bus_servo_niuju_on(0xfe)
        time.sleep(0.5)
        robot_control.bus_servo_all(30, 58, 170, 217, 20, 1000)
        time.sleep(2)
        robot_control.bus_servo_all(arr1, arr2, arr3, arr4, 20, 1000)
        time.sleep(2)
        robot_control.bus_servo_all(arr1, arr2, arr3, arr4, clip_close_degree, 1000)
        time.sleep(2)
        robot_control.bus_servo_all(30, 74, 172, 198, clip_close_degree, 1000)
        time.sleep(2)
        robot_control.bus_servo_all(200, 74, 172, 198, clip_close_degree, 1000)
        time.sleep(2)
        global result
        self.object_classify(result[2])
        robot_control.bus_servo_all(200, 74, 172, 198, 20, 1000)
        time.sleep(2)
        robot_control.bus_servo_all(30, 58, 170, 217, 20, 1000)

    def object_classify(self, fruit):
        global clip_close_degree
        point1_place = [222, 82, 192, 206, clip_close_degree, 1000]
        point2_place = [200, 88, 190, 206, clip_close_degree, 1000]
        point3_place = [228, 68, 182, 231, clip_close_degree, 1000]
        point4_place = [190, 74, 178, 234, clip_close_degree, 1000]
        if self.blinx_cbx_Ispick_shape.isChecked():
            if fruit == "banana":
                robot_control.bus_servo_all(*point1_place)
                time.sleep(3)
                robot_control.bus_servo_all(point1_place[0], point1_place[1], point1_place[2], point1_place[3],
                                            53, point1_place[5])
                time.sleep(1)
                robot_control.bus_servo_all(point1_place[0], point1_place[1], point1_place[2], 207,
                                            53, point1_place[5])
                time.sleep(1)
            elif fruit == "tomato":
                robot_control.bus_servo_all(*point2_place)
                time.sleep(3)
                robot_control.bus_servo_all(point2_place[0], point2_place[1], point2_place[2], point2_place[3],
                                            53, point2_place[5])
                time.sleep(1)
                robot_control.bus_servo_all(point2_place[0], point2_place[1], point2_place[2], 207,
                                            53, point2_place[5])
                time.sleep(1)
            elif fruit == "watermelon":
                robot_control.bus_servo_all(*point3_place)
                time.sleep(3)
                robot_control.bus_servo_all(point3_place[0], point3_place[1], point3_place[2], point3_place[3],
                                            53, point3_place[5])
                time.sleep(1)
                robot_control.bus_servo_all(point3_place[0], point3_place[1], point3_place[2], 207,
                                            53, point3_place[5])
                time.sleep(1)
            elif fruit == "cucumber":
                robot_control.bus_servo_all(*point4_place)
                time.sleep(3)
                robot_control.bus_servo_all(point4_place[0], point4_place[1], point4_place[2], point4_place[3],
                                            53, point4_place[5])
                time.sleep(1)
                robot_control.bus_servo_all(point4_place[0], point4_place[1], point4_place[2], 207,
                                            53, point4_place[5])
                time.sleep(1)

    def is_number(self, s):
        try:
            int(s)
            return True
        except:
            pass
        try:
            import unicodedata
            unicodedata.numeric(s)
        except:
            pass
        return False

    def closeEvent(self, event):
        if self.speech_recognizer.running:
            self.speech_recognizer.running = False
        if self.speech_thread and self.speech_thread.is_alive():
            self.speech_thread.join(timeout=2)
        if self.timer_camera.isActive():
            if self.cap.isOpened():
                self.cap.release()
            self.timer_camera.stop()
        self.stop_thread(self.thread_send)
        event.accept()

    def _async_raise(self, tid, exctype):
        tid = ctypes.c_long(tid)
        if not inspect.isclass(exctype):
            exctype = type(exctype)
        res = ctypes.pythonapi.PyThreadState_SetAsyncExc(tid, ctypes.py_object(exctype))
        if res == 0:
            raise ValueError("invalid thread id")
        elif res != 1:
            ctypes.pythonapi.PyThreadState_SetAsyncExc(tid, None)
            raise SystemError("PyThreadState_SetAsyncExc failed")

    def stop_thread(self, thread):
        self._async_raise(thread.ident, SystemExit)
# endregion

# region 主程序运行
if __name__ == "__main__":
    app = QApplication(sys.argv)
    five_robot = Blinx_Five_Robot_Arm()
    five_robot.show()
    sys.exit(app.exec_())
# endregion
