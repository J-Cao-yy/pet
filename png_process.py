import os
import sys
import argparse
import numpy as np
import cv2
from PIL import Image

def process_image(input_path, output_path, canny_low=50, canny_high=150, dilate_iter=1, area_thresh=100):
    """
    处理单张图片：
    - 读取 PNG（保留透明度）
    - 边缘检测 + 二值化 + 形态学膨胀
    - 寻找最大轮廓，生成掩膜
    - 将掩膜外的像素 alpha 置 0
    - 保存为 PNG
    """
    # 读取图像，IMREAD_UNCHANGED 会保留 alpha 通道（如果存在）
    img = cv2.imread(input_path, cv2.IMREAD_UNCHANGED)
    if img is None:
        print(f"无法读取图像: {input_path}")
        return

    # 分离颜色和 alpha 通道
    if img.shape[2] == 4:
        bgr = img[:, :, :3]
        alpha = img[:, :, 3].copy()
    else:
        bgr = img
        alpha = np.full(img.shape[:2], 255, dtype=np.uint8)

    # 转为灰度图用于边缘检测
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)

    # 可选：将透明区域置为黑色，避免边缘检测时出现虚假边缘
    # 但直接使用原图也通常没问题
    if alpha is not None:
        # 透明区域（alpha=0）设置为白色，这样边缘检测不会检测到透明边界
        # 也可以设置为黑色，根据内容调整
        gray[alpha == 0] = 255

    # 边缘检测
    edges = cv2.Canny(gray, canny_low, canny_high)

    # 膨胀边缘，连接断开的轮廓
    if dilate_iter > 0:
        kernel = np.ones((3, 3), np.uint8)
        edges = cv2.dilate(edges, kernel, iterations=dilate_iter)

    # 寻找轮廓
    contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    # 如果没有找到任何轮廓，直接保存原图（或全透明？）
    if len(contours) == 0:
        print(f"未检测到轮廓: {input_path}")
        # 可以选择将整张图设为透明，这里保持原样
        cv2.imwrite(output_path, img)
        return

    # 计算每个轮廓的面积（使用轮廓面积，但更准确的是计算填充后的像素数）
    # 这里我们采用轮廓面积近似，也可以使用 cv2.contourArea
    areas = [cv2.contourArea(c) for c in contours]
    max_idx = np.argmax(areas)
    max_contour = contours[max_idx]

    # 创建掩膜，填充最大轮廓
    mask = np.zeros(gray.shape, dtype=np.uint8)
    cv2.drawContours(mask, [max_contour], -1, 255, thickness=cv2.FILLED)

    # 可选：对掩膜进行形态学闭运算，填充内部空洞
    if dilate_iter > 0:
        kernel = np.ones((5,5), np.uint8)
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)

    # 将掩膜外的像素 alpha 设为 0
    new_alpha = alpha.copy()
    new_alpha[mask == 0] = 0

    # 合并 BGRA 图像
    if img.shape[2] == 4:
        result = cv2.merge([bgr[:, :, 0], bgr[:, :, 1], bgr[:, :, 2], new_alpha])
    else:
        # 原图没有 alpha，创建一个
        result = cv2.merge([bgr[:, :, 0], bgr[:, :, 1], bgr[:, :, 2], new_alpha])

    # 保存为 PNG
    cv2.imwrite(output_path, result)
    print(f"已处理: {input_path} -> {output_path}")

def main():
    parser = argparse.ArgumentParser(description="提取 PNG 图片中面积最大的区域，其他区域透明化")
    parser.add_argument("input_dir", help="输入文件夹路径")
    parser.add_argument("output_dir", help="输出文件夹路径")
    parser.add_argument("--canny_low", type=int, default=50, help="Canny 低阈值 (默认 50)")
    parser.add_argument("--canny_high", type=int, default=150, help="Canny 高阈值 (默认 150)")
    parser.add_argument("--dilate_iter", type=int, default=1, help="膨胀迭代次数 (默认 1)")
    parser.add_argument("--area_thresh", type=int, default=100, help="最小面积阈值 (默认 100，暂未使用)")
    args = parser.parse_args()

    input_dir = args.input_dir
    output_dir = args.output_dir

    if not os.path.isdir(input_dir):
        print(f"输入文件夹不存在: {input_dir}")
        sys.exit(1)

    # 创建输出根目录
    os.makedirs(output_dir, exist_ok=True)

    # 递归遍历所有文件夹
    for root, dirs, files in os.walk(input_dir):
        # 计算相对路径，保持目录结构
        rel_path = os.path.relpath(root, input_dir)
        if rel_path == ".":
            rel_path = ""
        target_dir = os.path.join(output_dir, rel_path)
        os.makedirs(target_dir, exist_ok=True)

        for file in files:
            if file.lower().endswith(".png"):
                input_file = os.path.join(root, file)
                output_file = os.path.join(target_dir, file)
                process_image(input_file, output_file,
                              canny_low=args.canny_low,
                              canny_high=args.canny_high,
                              dilate_iter=args.dilate_iter,
                              area_thresh=args.area_thresh)

if __name__ == "__main__":
    main()