# region 库文件
import cv2
import time
import threading
from Object_Recognition import *  # 导入形状颜色识别模块
from calibration import *  # 导入校准模块
from Five_Robot_kinematics import *  # 导入机械臂运动学模块
from Five_Robot_Control import *  # 导入机械臂控制模块
# endregion
# region 全局变量
global shap_count_circles  # 圆形计数
shap_count_circles = 0
global shape_count_square  # 正方形计数
shape_count_square = 0
global result  # 检测结果
result = []
global bool_IsSend  # 发送数据标志
bool_IsSend = False
global clip_open_degree  # 夹爪每次放置物体时张开夹爪度数，防止夹爪张开过大碰撞到其它
clip_open_degree = 40
global clip_close_degree  # 夹爪关闭时角度
clip_close_degree = 75
# endregion
# region 实例化对象
robot_control = Blinx_Five_Robot_Control()  # 机械臂控制实例
recognitions = Blinx_Object_Recognition() # 物体颜色形状识别实例
calibration = Blinx_Cam_Calibration()  # 摄像头校准实例
five_robot_kinematics = Blinx_Five_Robot_kinematics()  # 机械臂运动学实例
# endregion
# 定义全局变量image，用于存储当前帧图像
global image
# 发送数据线程函数
def blinx_send_data():
    try:
        while True:
            time.sleep(0.1)
            global bool_IsSend
            if bool_IsSend:
                bool_IsSend = False
                global result
                if result:
                    # 调用机械臂抓取函数
                    blinx_robot_pick(int(result[0][0]), int(result[0][1]))
                    print("数据已发送到机械臂")
                    result = []
                else:
                    print('图像识别错误')
    except Exception as e:
        print("数据发送线程异常：", e)
# 机械臂抓取函数
def blinx_robot_pick(pixel_x, pixel_y):
    # 通过校准将像素坐标转换为世界坐标
    point_x, point_y = calibration.blinx_calibration(pixel_x, pixel_y)
    print("世界坐标:", point_x, point_y)
    # 计算关节角度
    arr1, arr2, arr3, arr4 = five_robot_kinematics.arr(point_x, point_y, 0)
    print("关节角度:", arr1, arr2, arr3, arr4)
    # 开启机械臂
    robot_control.blinx_bus_servo_niuju_on(0xfe)
    time.sleep(0.5)
    # 控制机械臂运动
    robot_control.blinx_bus_servo_all(30, 58, 170, 217, 0, 1000)
    time.sleep(2)
    robot_control.blinx_bus_servo_all(arr1, arr2, arr3, arr4, 0, 1000)
    time.sleep(2)
    robot_control.blinx_bus_servo_all(arr1, arr2, arr3, arr4, clip_close_degree, 1000)
    time.sleep(2)
    robot_control.blinx_bus_servo_all(30, 74, 172, 198, clip_close_degree, 1000)
    time.sleep(2)
    robot_control.blinx_bus_servo_all(200, 74, 172, 198, clip_close_degree, 1000)
    time.sleep(2)
    global result
    # 调用物体分类函数
    blinx_object_classify(result[1], result[2])
    print("物体分类:", result[1], result[2])
    robot_control.blinx_bus_servo_all(200, 74, 172, 198, 0, 1000)
    time.sleep(2)
    robot_control.blinx_bus_servo_all(30, 58, 170, 217, 0, 1000)
# 物体分类函数
def blinx_object_classify(color, shape):
    global clip_open_degree
    global clip_close_degree
    # 定义四个放置点的坐标和角度
    point1_place = [213, 96, 193, 204, clip_close_degree, 1000]
    point2_place = [192, 96, 193, 204, clip_close_degree, 1000]
    point3_place = [220, 47, 210, 227, clip_close_degree, 1000]
    point4_place = [185, 47, 210, 227, clip_close_degree, 1000]
    classification_color = True
    if classification_color:
        # 根据颜色分类
        if color == "red":
            # 控制机械臂将物体放置在第一个位置
            robot_control.blinx_bus_servo_all(point1_place[0], point1_place[1], point1_place[2], point1_place[3],
                                        point1_place[4], point1_place[5])
            time.sleep(1)
            robot_control.blinx_bus_servo_all(point1_place[0], point1_place[1], point1_place[2], point1_place[3],
                                        clip_close_degree - clip_open_degree, point1_place[5])
            time.sleep(1)
            robot_control.blinx_bus_servo_all(point1_place[0], point1_place[1], point1_place[2], 207,
                                        clip_close_degree - clip_open_degree, point1_place[5])
            time.sleep(1)
        elif color in ["blue", "cyan"]:
            # 控制机械臂将物体放置在第二个位置
            robot_control.blinx_bus_servo_all(point2_place[0], point2_place[1], point2_place[2], point2_place[3],
                                        point2_place[4], point2_place[5])
            time.sleep(1)
            robot_control.blinx_bus_servo_all(point2_place[0], point2_place[1], point2_place[2], point2_place[3],
                                        clip_close_degree - clip_open_degree, point2_place[5])
            time.sleep(1)
            robot_control.blinx_bus_servo_all(point2_place[0], point2_place[1], point2_place[2], 207,
                                        clip_close_degree - clip_open_degree, point2_place[5])
            time.sleep(1)
        elif color == "yellow":
            # 控制机械臂将物体放置在第三个位置
            robot_control.blinx_bus_servo_all(point3_place[0], point3_place[1], point3_place[2], point3_place[3],
                                        point3_place[4], point3_place[5])
            time.sleep(1)
            robot_control.blinx_bus_servo_all(point3_place[0], point3_place[1], point3_place[2], point3_place[3],
                                        clip_close_degree - clip_open_degree, point3_place[5])
            time.sleep(1)
            robot_control.blinx_bus_servo_all(point3_place[0], point3_place[1], point3_place[2], 207,
                                        clip_close_degree - clip_open_degree, point3_place[5])
            time.sleep(1)
        elif color == "green":
            # 控制机械臂将物体放置在第四个位置
            robot_control.blinx_bus_servo_all(point4_place[0], point4_place[1], point4_place[2], point4_place[3],
                                        point4_place[4], point4_place[5])
            time.sleep(1)
            robot_control.blinx_bus_servo_all(point4_place[0], point4_place[1], point4_place[2], point4_place[3],
                                        clip_close_degree - clip_open_degree, point4_place[5])
            time.sleep(1)
            robot_control.blinx_bus_servo_all(point4_place[0], point4_place[1], point4_place[2], 207,
                                        clip_close_degree - clip_open_degree, point4_place[5])
            time.sleep(1)
        else:
            print("未知的颜色")
    else:
        # 根据形状分类
        if shape == "square":
            global shape_count_square
            shape_count_square += 1
            if shape_count_square == 1:
                # 控制机械臂将物体放置在第一个位置
                robot_control.blinx_bus_servo_all(point1_place[0], point1_place[1], point1_place[2], point1_place[3],
                                            point1_place[4], point1_place[5])
                time.sleep(1)
                robot_control.blinx_bus_servo_all(point1_place[0], point1_place[1], point1_place[2], point1_place[3],
                                            clip_close_degree - clip_open_degree, point1_place[5])
                time.sleep(1)
                robot_control.blinx_bus_servo_all(point1_place[0], point1_place[1], point1_place[2], 207,
                                            clip_close_degree - clip_open_degree, point1_place[5])
                time.sleep(1)
            elif shape_count_square == 2:
                # 控制机械臂将物体放置在第二个位置
                robot_control.blinx_bus_servo_all(point2_place[0], point2_place[1], point2_place[2], point2_place[3],
                                            point2_place[4], point2_place[5])
                time.sleep(1)
                robot_control.blinx_bus_servo_all(point2_place[0], point2_place[1], point2_place[2], point2_place[3],
                                            clip_close_degree - clip_open_degree, point2_place[5])
                time.sleep(1)
                robot_control.blinx_bus_servo_all(point2_place[0], point2_place[1], point2_place[2], 207,
                                            clip_close_degree - clip_open_degree, point2_place[5])
                time.sleep(1)
        elif shape == "circle":
            global shap_count_circles
            shap_count_circles += 1
            if shap_count_circles == 1:
                # 控制机械臂将物体放置在第三个位置
                robot_control.blinx_bus_servo_all(point3_place[0], point3_place[1], point3_place[2], point3_place[3],
                                            point3_place[4], point3_place[5])
                time.sleep(1)
                robot_control.blinx_bus_servo_all(point3_place[0], point3_place[1], point3_place[2], point3_place[3],
                                            clip_close_degree - clip_open_degree, point3_place[5])
                time.sleep(1)
                robot_control.blinx_bus_servo_all(point3_place[0], point3_place[1], point3_place[2], 207,
                                            clip_close_degree - clip_open_degree, point3_place[5])
                time.sleep(1)
            elif shap_count_circles == 2:
                # 控制机械臂将物体放置在第四个位置
                robot_control.blinx_bus_servo_all(point4_place[0], point4_place[1], point4_place[2], point4_place[3],
                                            point4_place[4], point4_place[5])
                time.sleep(1)
                robot_control.blinx_bus_servo_all(point4_place[0], point4_place[1], point4_place[2], point4_place[3],
                                            clip_close_degree - clip_open_degree, point4_place[5])
                time.sleep(1)
                robot_control.blinx_bus_servo_all(point4_place[0], point4_place[1], point4_place[2], 207,
                                            clip_close_degree - clip_open_degree, point4_place[5])
                time.sleep(1)
        else:
            print("未知的形状")
# 打开摄像头函数
def blinx_open_camera(cam_num):
    cap = cv2.VideoCapture(cam_num)  # 打开摄像头
    if not cap.isOpened():  # 检查摄像头是否成功打开
        print('相机打开失败，请更改相机序号cam_num后重试（修改范围0，1，2，3）')
    return cap  # 返回摄像头对象
# 开始进行物体形状颜色识别，并显示识别后的图像
def blinx_start_detection(image):
    try:
        # 调用物体形状颜色识别函数
        img, identify_result = recognitions.blinx_recognition(image)
        cv2.imshow("Camera", img)  # 显示识别后的图像
        global bool_IsSend, result
        # 是否打开机械臂抓取
        bool_IsSend = True
        result = identify_result
        cv2.waitKey(0)
    except Exception as e:
        print("数据获取失败：", e)
# 主函数
def main():
    global image  # 声明全局变量image
    cam_num = 0  # 设置摄像头编号
    cap = blinx_open_camera(cam_num)  # 打开摄像头
    print("按下'd'键，执行检测；按下'q'键，退出运行")
    try:
        while True:
            ret, frame = cap.read()  # 读取摄像头的一帧图像
            if not ret:  # 如果未成功读取帧
                print("获取帧失败")
                break
            cv2.imshow("Camera", frame)  # 显示图像
            image = frame  # 保存当前帧以便进行检测
            key = cv2.waitKey(30) & 0xFF  # 等待按键输入，每隔30ms检查一次
            if key == ord('d'):  # 如果按下'd'键
                blinx_start_detection(image)  # 开始进行物体形状颜色识别
            elif key == ord('q'):  # 如果按下'q'键
                break  # 退出循环
    finally:
        cap.release()  # 释放摄像头
        cv2.destroyAllWindows()  # 关闭所有OpenCV窗口
# 程序入口
if __name__ == "__main__":
    # 启动发送数据线程
    thread_send = threading.Thread(target=blinx_send_data)
    thread_send.start()
    main()  # 运行主程序
