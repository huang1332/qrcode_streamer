import cv2
import time
import numpy as np
from PIL import ImageGrab, Image
from io import BytesIO
import threading
import copy
import segno
import base64
from multiprocessing import Process
import socket
from Crypto.Cipher import AES
from Crypto.Random import get_random_bytes
from Crypto.Util.Padding import pad, unpad
import io
from queue import Queue
#pip install pycryptodome
def process_pw(two_qr):
    if two_qr!='':
        max_size=1000#开始尝试的最大尺寸
    else:
        max_size=500
    input_size = input("发送图片的最大尺寸(默认双二维码是1000,单二维码是500)：")
    if input_size.isdigit():
        max_size = int(input_size)
    print("发送图片的最大尺寸是"+str(max_size)+"，过大时会自动多次尝试缩小")
    input_str = input("请输入密码(为空则不加密)：")
    if input_str=='':
        return None,max_size
    ascii_string = ''.join(char for char in input_str if ord(char) < 128)# 剔除非ASCII字符
    padded_string = ascii_string[:16].ljust(16)# 补全或截断到16位长度
    byte_string = padded_string.encode('utf-8')
    return byte_string,max_size

def create_qrcode_process(server_address):
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.connect(server_address)
    while True:
        nonce_and_encrypted_data = sock.recv(20480)
        if nonce_and_encrypted_data:
            qr = segno.make(nonce_and_encrypted_data, error='L',micro=False, boost_error=False)
            qr_buffer = io.BytesIO()
            qr.save(qr_buffer, kind='png', scale=5)
            qr_buffer.seek(0)
            sock.sendall(qr_buffer.getvalue())
        else:
            break

def img_encrypt(image,max_size,key):
    image.thumbnail((max_size, max_size), Image.ANTIALIAS)
    buffer = BytesIO()
    image.save(buffer, format='WebP', quality=10)#图像质量 1-100，太小就糊了
    img_str = buffer.getvalue()
    if key is None:
        nonce_base64=b'*'*12#'*'*12 相当于len(nonce_base64)
        encrypted_data_base64 = base64.b64encode(img_str)
    else:
        cipher = AES.new(key, AES.MODE_CTR)
        encrypted_data = cipher.encrypt(img_str)
        nonce_base64 = base64.b64encode(cipher.nonce)
        encrypted_data_base64 = base64.b64encode(encrypted_data)
    print('size of data: ', len(encrypted_data_base64))
    return nonce_base64,encrypted_data_base64

def img_show(video_queue):
    canvas_temp=copy.deepcopy(canvas)
    while True:
        if not video_queue.empty():
            canvas_temp=copy.deepcopy(video_queue.get())
        cv2.imshow('frame', canvas_temp)
        cv2.waitKey(1)

if __name__ == "__main__":
    video_queue= Queue()
    two_qr= input("是否使用两个彩色二维码(输入任意字符即可，不填直接回车则是单个二维码)：")
    if two_qr!='':
        part_num=6
        canvas_orign = np.zeros((960,1920,3), dtype=np.uint8)  # Empty canvas
    else:
        part_num=3
        canvas_orign = np.zeros((960,960,3), dtype=np.uint8)  # Empty canvas
    qr_images = []
    canvas = copy.deepcopy(canvas_orign)
    key ,max_size= process_pw(two_qr)
    threading.Thread(target=img_show, args=(video_queue,)).start()
    processes = []
    connections = []
    for _ in range(6):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.bind(('localhost', 12345 + _))
        s.listen(1)
        p = Process(target=create_qrcode_process, args=(('localhost', 12345 + _),))
        p.start()
        processes.append(p)
        conn, addr = s.accept()
        connections.append(conn)

    while True:
        time1 = time.time()
        image = ImageGrab.grab()
        width, height = image.size
        aspect_ratio_bytes = f"{width:04}{height:04}".encode()
        encrypted_data_base64=None
        for i_size in [1, 0.9, 0.75, 0.5, 0.3, 0.1, 0.01]:
            if encrypted_data_base64 is not None and len(encrypted_data_base64)<2900*part_num:#2800
                break
            size_=max_size*i_size
            nonce_base64,encrypted_data_base64=img_encrypt(image,int(size_),key)
            print('try img size: ',size_, end='   ')

        # Divide the encrypted data into six equal parts
        part_length = len(encrypted_data_base64) // part_num
        data_parts = [encrypted_data_base64[i:i+part_length] for i in range(0, len(encrypted_data_base64), part_length)]
        if len(encrypted_data_base64) % part_num != 0:
            data_parts[part_num-1] += encrypted_data_base64[part_length*part_num:]
        qr_images = []

        for i in range(part_num):
            nonce_and_encrypted_data = bytes(str(i+1).zfill(2), 'utf-8') + nonce_base64 + aspect_ratio_bytes + data_parts[i]
            print(nonce_and_encrypted_data)
            connections[i].sendall(nonce_and_encrypted_data)

        canvas = copy.deepcopy(canvas_orign)

        for i in range(part_num):
            qr_buffer = connections[i].recv(20480)
            qr_img = Image.open(io.BytesIO(qr_buffer))
            qr_images.append(qr_img)
        if two_qr!='':
            for i in range(3):
                qr_np = np.array(qr_images[i*2].convert('RGB'))[:,:,0]  # Red channel
                qr_np_next = np.array(qr_images[i*2+1].convert('RGB'))[:,:,0]  # Red channel
                canvas[0:qr_np.shape[0], 0:qr_np.shape[1], i] = qr_np
                canvas[0:qr_np_next.shape[0], 960:960+qr_np_next.shape[1], i] = qr_np_next
        else:
            for i in range(3):
                qr_np = np.array(qr_images[i].convert('RGB'))[:,:,0]
                canvas[0:qr_np.shape[0], 0:qr_np.shape[1], i] = qr_np
        video_queue.put(canvas)

        print(' time ',time.time() - time1)

    for conn in connections:
        conn.close()
    for p in processes:
        p.join()
    cv2.destroyAllWindows()
