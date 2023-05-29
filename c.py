import cv2
import numpy as np
from io import BytesIO
import base64
import pyzbar.pyzbar as pyzbar
from PIL import ImageGrab, Image
import threading

from Crypto.Cipher import AES
from Crypto.Util.Padding import unpad
def process_pw():
    scale=3
    scale_input = input("请输入一个数字，决定显示窗口是原图的几分之一(比如1、2、3,默认是3): ")
    if scale_input.isdigit():
        scale = int(scale_input)
    print("显示窗口是原图的"+str(scale)+"分之一")

    input_str = input("请输入密码(为空则不加密)：")
    if input_str=='':
        return None,scale
    ascii_string = ''.join(char for char in input_str if ord(char) < 128)
    padded_string = ascii_string[:16].ljust(16)
    byte_string = padded_string.encode('utf-8')
    return byte_string,scale


def decode_qr_image(qr_img, decoded_data_list):
    decoded_objects = pyzbar.decode(qr_img)

    if len(decoded_objects) == 0:
        print("No QR code found")
        return None, None, None, None

    for decoded_object in decoded_objects:
        qr_data = decoded_object.data
        prefix = qr_data[:2]
        if prefix >= b'01' and prefix <= b'06':
            nonce_base64 = qr_data[2:14]
            aspect_ratio_bytes = qr_data[14:22]
            encoded_data = qr_data[22:]
            decoded_data_list.append((prefix, nonce_base64, aspect_ratio_bytes, encoded_data))

def decrypt_image(key_input,nonce_base64, encrypted_data_base64, aspect_ratio_bytes):
    if key_input is None and nonce_base64==b'*'*12:
        decrypted_data = base64.b64decode(encrypted_data_base64)
    else:
        nonce = base64.b64decode(nonce_base64)
        encrypted_data = base64.b64decode(encrypted_data_base64)
        cipher = AES.new(key_input, AES.MODE_CTR, nonce=nonce)
        decrypted_data = cipher.decrypt(encrypted_data)

    original_width = int(int(aspect_ratio_bytes[:4].decode())/imscale)
    original_height = int(int(aspect_ratio_bytes[4:].decode())/imscale)

    img = Image.open(BytesIO(decrypted_data))
    img = img.resize((original_width, original_height), Image.ANTIALIAS)

    return img

key_input,imscale = process_pw()
while True:
    full_img = ImageGrab.grab()
    full_img_np = np.array(full_img.convert('RGB'))
    red_channel = full_img_np[:,:,0]
    green_channel = full_img_np[:,:,1]
    blue_channel = full_img_np[:,:,2]

    channels = [red_channel, green_channel, blue_channel]

    decoded_data_list = []
    threads = []

    for channel in channels:
        channel_img = Image.fromarray(channel)
        t = threading.Thread(target=decode_qr_image, args=(channel_img, decoded_data_list))
        threads.append(t)

    for t in threads:
        t.start()
    for t in threads:
        t.join()
    if len(decoded_data_list)!=6 and len(decoded_data_list)!=3:
        continue
    decoded_data_list.sort(key=lambda x: x[0])  # Sort the list by prefix
    encrypted_data_base64 = b''.join(x[3] for x in decoded_data_list)
    nonce_base64 = decoded_data_list[0][1]
    aspect_ratio_bytes = decoded_data_list[0][2]

    if len(encrypted_data_base64) > 0:
        decoded_img = decrypt_image(key_input,nonce_base64, encrypted_data_base64, aspect_ratio_bytes)
        decoded_np = np.array(decoded_img.convert('RGB'))
        b, g, r = cv2.split(decoded_np)
        decoded_np = cv2.merge((r, g, b))
        cv2.imshow('Decoded Image', decoded_np)

    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

cv2.destroyAllWindows()
