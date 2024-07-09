import cv2
import base64
import numpy as np
from flask import Flask, request, render_template, redirect, url_for, flash, session, jsonify, g
from flask_socketio import SocketIO, emit
import pymysql
import time
import requests
from ultralytics import YOLO
import os
from datetime import datetime, timezone

app = Flask(__name__, static_folder='static')
socketio = SocketIO(app, manage_session=True)
# 전역 변수로 선언
data = {}

address_cache={}

app.secret_key = 'team2'

recv_data = None

# 녹화 변수 초기화
rootPath = './recording/'
out = None
recording = False
frameSize = (640, 480)  # 기본 프레임 크기
fps = 2.0
codec = cv2.VideoWriter_fourcc('D', 'I', 'V', 'X')  # 코덱 설정
# 이미지를 저장할 디렉토리 설정
SAVE_DIR = os.path.join(os.path.dirname(__file__), 'img')

tracking_data  = None

# Load YOLOv8 model
best_model_path = 'best2.pt'
model = YOLO(best_model_path)


# 테스트용 이미지파일
def save_frame_as_image(frame):
    timestamp = time.strftime('%Y%m%d%H%M%S')
    filename = f'annotated_frame_{timestamp}.jpg'

    # 이미지 파일 경로 설정
    save_path = os.path.join(SAVE_DIR, filename)

    # 이미지 저장
    cv2.imwrite(save_path, frame)
    # print(f'이미지가 {save_path} 에 저장되었습니다.')


def get_db_connection():
    connection = pymysql.connect(
        # host='192.168.31.75',
        # user='root1',
        host='127.0.0.1',
        user='root',
        password='0000',
        db='team2',
        charset='utf8mb4',
        cursorclass=pymysql.cursors.DictCursor
    )
    return connection

#오픈스트리트맵
def get_address_from_lat_lon_google(lat, lon, api_key, retries=3):
    cache_key = (lat, lon)
    if cache_key in address_cache:
        return address_cache[cache_key]

    url = f'https://maps.googleapis.com/maps/api/geocode/json?latlng={lat},{lon}&key={api_key}&language=ko'
    print(f"Request URL: {url}")  # 요청 URL 출력

    for attempt in range(retries):
        try:
            response = requests.get(url, timeout=10)
            print(f"Response status code: {response.status_code}")  # 응답 상태 코드 출력
            if response.status_code == 200:
                data = response.json()
                print(f"Response data: {data}")  # 응답 데이터 출력
                if data['status'] == 'OK':
                    address = data['results'][0]['formatted_address']
                    address_cache[cache_key] = address
                    return address
                else:
                    print(f"Geocoding API Error: {data['status']} - {data['error_message'] if 'error_message' in data else 'No error message'}")
                    return "No address found"
            else:
                print(f"Attempt {attempt+1}: Error {response.status_code}. Retrying...")
                time.sleep(2 ** attempt)  # 지수 백오프
        except requests.exceptions.RequestException as e:
            print(f"Attempt {attempt+1}: RequestException {e}. Retrying...")
            time.sleep(2 ** attempt)
    return "Failed to get address after retries"

@app.route('/map')
def map():
    # latitude = 36.371691
    # longitude = 127.378964

    latitude = 36.348467
    longitude = 127.382160
    api_key = 'AIzaSyA432B9qNSn19lPPXy83RsRIXe4oSO2pD8'  # Google API 키
    address = get_address_from_lat_lon_google(latitude, longitude, api_key)
    # print(latitude)
    # print(longitude)
    # print(address)
    return jsonify(latitude=latitude, longitude=longitude, address=address)


@app.route('/load_map')
def route_map():
    try:
        data = session.get('row_data')  # 세션에서 데이터 가져오기

        if data is None:
            return jsonify({'error': '세션 데이터가 없습니다.'}), 500

        name = data.get('name')
        update_time = data.get('update_time')  # update_time 가져오기

        if not name or not update_time:
            return jsonify({'error': '세션 데이터에 필수 항목이 없습니다.'}), 500

        connection = get_db_connection()  # 데이터베이스 연결 얻기
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT route_A, latitude_A, longitude_A,
                       route_B, latitude_B, longitude_B,
                       route_C, latitude_C, longitude_C,
                       route_D, latitude_D, longitude_D,
                       route_E, latitude_E, longitude_E
                FROM routes
                WHERE name=%s AND update_time=%s
            """, (name, update_time))
            row = cursor.fetchone()

            if not row:
                return jsonify({'error': '해당하는 경로 데이터가 없습니다.'}), 404

            routes = []
            for i in range(5):
                route_key = f'route_{chr(65 + i)}'
                latitude_key = f'latitude_{chr(65 + i)}'
                longitude_key = f'longitude_{chr(65 + i)}'

                route_name = row.get(route_key)
                latitude = row.get(latitude_key)
                longitude = row.get(longitude_key)

                if route_name and latitude and longitude:
                    routes.append({
                        'name': route_name,
                        'latitude': latitude,
                        'longitude': longitude
                    })

        connection.close()

        current_latitude = 36.348467
        current_longitude = 127.382160

        formatted_data = format_data_for_frontend(current_latitude, current_longitude, routes)
        return jsonify(formatted_data)

    except pymysql.MySQLError as e:
        app.logger.error(f'Database error: {str(e)}')
        return jsonify({'error': f'데이터베이스 오류: {str(e)}'}), 500
    except Exception as e:
        app.logger.error(f'Server error: {str(e)}')
        return jsonify({'error': f'서버 오류: {str(e)}'}), 500


def format_data_for_frontend(current_latitude, current_longitude, routes_data):
    # 프론트엔드에 전달할 데이터를 필요한 형식으로 포맷팅합니다 (예시 구조)
    formatted_data = {
        'current_location': {
            'latitude': current_latitude,
            'longitude': current_longitude,
            # 'address': address,  # 필요시 주소 추가
        },
        'routes': []
    }

    for idx, route in enumerate(routes_data, start=1):
        formatted_data['routes'].append({
            'order': idx,
            'latitude': route['latitude'],
            'longitude': route['longitude'],
        })

    return formatted_data



def create_missing_persons_table():
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            sql = '''
            CREATE TABLE IF NOT EXISTS missing_persons (
                id INT AUTO_INCREMENT PRIMARY KEY,
                name VARCHAR(255) NOT NULL,
                age INT NOT NULL,
                gender VARCHAR(10) NOT NULL,
                height FLOAT NOT NULL,
                place VARCHAR(255) NOT NULL,
                date DATE NOT NULL,
                upper VARCHAR(255) NOT NULL,
                upper_color VARCHAR(50) NOT NULL,
                lower VARCHAR(255) NOT NULL,
                lower_color VARCHAR(50) NOT NULL,
                shoes VARCHAR(255) NOT NULL,
                shoes_color VARCHAR(50) NOT NULL,
                missing_img1_data LONGBLOB NOT NULL,
                missing_img2_data LONGBLOB NOT NULL,
                find TINYINT(1) NOT NULL
            )
            '''
            cursor.execute(sql)
            connection.commit()
    finally:
        connection.close()

@app.route('/')
def home():
    return render_template("login.html")
# OpenWeatherMap API 키
OWM_API_KEY = '0a9ad2bc2f23cd462a5ea9918e5a7bb1'

@app.template_filter('timestamp_to_time')
def timestamp_to_time(timestamp):
    return datetime.fromtimestamp(timestamp).strftime('%H:%M:%S')


def get_weather_data(api_key, city):
    url = f'http://api.openweathermap.org/data/2.5/weather?q={city}&appid={api_key}&units=metric&lang=kr'
    response = requests.get(url)
    data = response.json()
    print("Weather API response:", data)  # 응답 데이터 로그 출력
    return data

@app.route('/login', methods=['POST'])
def login():
    username = request.form['username']
    password = request.form['password']
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            sql = "SELECT * FROM user WHERE user_name=%s AND password=%s"
            cursor.execute(sql, (username, password))
            result = cursor.fetchone()
            if result:
                session['user_id'] = result['user_id']
                sql = "SELECT * FROM missing_persons"
                cursor.execute(sql)
                missing_persons_data = cursor.fetchall()

                # 날씨 데이터 가져오기
                weather_data = get_weather_data(OWM_API_KEY, 'Seoul')  # 도시명을 원하는 도시로 변경

                return render_template('chart.html', data=missing_persons_data, weather_data=weather_data)
            else:
                flash('아이디 또는 비밀번호가 올바르지 않습니다.')
                return redirect(url_for('home'))
    finally:
        connection.close()

@app.route('/chart')
def chart():
    if 'user_id' in session:
        connection = get_db_connection()
        try:
            with connection.cursor() as cursor:
                sql = "SELECT * FROM missing_persons"
                cursor.execute(sql)
                missing_persons_data = cursor.fetchall()

                # 날씨 데이터 가져오기
                weather_data = get_weather_data(OWM_API_KEY, 'Seoul')  # 도시명을 원하는 도시로 변경

                return render_template('chart.html', data=missing_persons_data, weather_data=weather_data)
        finally:
            connection.close()
    else:
        flash('로그인이 필요합니다.')
        return redirect(url_for('login'))


@app.route('/missing_info')
#missing_info : 실종자 정보입력 페이지
def missing_info():
    if 'user_id' in session:
        return render_template('missing_info.html')
    else:
        flash('로그인이 필요합니다.')
        return redirect(url_for('login'))

@app.route('/back_page')
def back():
    return render_template('missing_info.html')

@app.route('/route')
def route():
    return render_template('drone_route.html')


@app.route('/save_info', methods=['POST'])
def save_info():
    if request.method == 'POST':
        # HTML에서 POST로 전송된 데이터를 가져옴
        # print(request.form)

        # print(request.files)
        missing_imgs = request.files.getlist('missing_img')
        print("missing_imgs 뭐야! : ", missing_imgs)
        missing_img1 = missing_imgs[0].read()
        print("missing_img1 바이너리?! : ", missing_img1)

        if missing_imgs and len(missing_imgs) >= 1:

            find = False

            name = request.form['name']
            height = request.form['height']
            gender = request.form['gender']
            age = request.form['age']
            place = request.form['place']
            date = request.form['date']

            upper = request.form['upper']
            upper_color = request.form['upper_color']
            lower = request.form['lower']
            lower_color = request.form['lower_color']
            shoes = request.form['shoes']
            shoes_color = request.form['shoes_color']

            missing_img1_data = missing_img1
            # print("missing_img1_data", missing_img1_data)
            if len(missing_imgs) == 2:
                missing_img2_data = missing_imgs[1].read()
            else:
                missing_img2_data = b''

            # 모든 필드가 채워져 있는지 확인
            if not all([name, height, gender, age, place, date, upper, upper_color, lower, lower_color, shoes,
                        shoes_color, missing_img1_data]):
                flash('모든 칸을 채워주세요!')
                return redirect(url_for('missing_info'))

            # 데이터베이스에 연결
            connection = get_db_connection()
            try:
                with connection.cursor() as cursor:
                    create_missing_persons_table()
                    # INSERT 쿼리 실행해서 데이터 넣기
                    sql = "INSERT INTO missing_persons (name, age, gender, height, place, date, upper, upper_color, lower, lower_color, shoes, shoes_color, missing_img1_data, missing_img2_data,find) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"
                    cursor.execute(sql, (
                        name, age, gender, height, place, date, upper, upper_color, lower, lower_color, shoes,
                        shoes_color, missing_img1_data, missing_img2_data, find))

                    # 마지막으로 삽입된 행의 ID 가져오기
                    last_insert_id = cursor.lastrowid

                    # 방금 삽입한 데이터 가져오기
                    sql = "SELECT id, name, age, gender, height, place, date, upper, upper_color, lower, lower_color, shoes, shoes_color, find FROM missing_persons WHERE id = %s"
                    cursor.execute(sql, (last_insert_id,))
                    result = cursor.fetchone()
                    connection.commit()
                    session['last_info'] = result
                    if 'row_data' in session:
                        del session['row_data']
                    # print("result:", result)
                    print("세션 설정: session['last_info'] =", session['last_info'])
            finally:
                connection.close()
            return render_template('drone_route.html', data=result)

        else:
            flash('모든 칸을 채워주세요!')
            return redirect(url_for('missing_info'))

@app.route('/get_row_data', methods=['POST'])
def get_row_data():
    selected_id = request.form['id']
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            sql = "SELECT id, name, age, gender, height, place, date, upper, upper_color, lower, lower_color, shoes, shoes_color, find FROM missing_persons WHERE id = %s"
            cursor.execute(sql, (selected_id,))
            row_data = cursor.fetchone()
            # print("row_data:",row_data)
            session['row_data']=row_data
            # print("session['row_data']",session['row_data'])
            if 'last_info' in session:
                del session['last_info']

    finally:
        connection.close()

    return render_template('drone_route.html')

def create_routes_table():
    connection = get_db_connection()

    try:
        with connection.cursor() as cursor:
            sql = '''
            CREATE TABLE IF NOT EXISTS routes (
                id INT AUTO_INCREMENT PRIMARY KEY,
                name VARCHAR(10) NOT NULL,
                route_A VARCHAR(255) NOT NULL,
                latitude_A FLOAT NOT NULL,
                longitude_A FLOAT NOT NULL,
                route_B VARCHAR(255) NOT NULL,
                latitude_B FLOAT NOT NULL,
                longitude_B FLOAT NOT NULL,
                route_C VARCHAR(255),
                latitude_C FLOAT,
                longitude_C FLOAT,
                route_D VARCHAR(255),
                latitude_D FLOAT,
                longitude_D FLOAT,
                route_E VARCHAR(255),
                latitude_E FLOAT,
                longitude_E FLOAT,
                update_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
            )
            '''
            cursor.execute(sql)
            connection.commit()
    finally:
        connection.close()



# 데이터베이스에서 색상을 가져오는 함수
def fetch_colors_from_db(class_name):
    try:
        connection = pymysql.connect(
            # host='192.168.31.75',
            # user='root1',
            host='127.0.0.1',
            user='root',
            password='0000',
            db='team2',
            charset='utf8mb4',
            cursorclass=pymysql.cursors.DictCursor
        )
        cursor = connection.cursor()

        query = "SELECT upper_color, lower_color FROM missing_persons WHERE upper = %s OR lower = %s"
        cursor.execute(query, (class_name, class_name))

        row = cursor.fetchone()
        if row:
            upper_color = row['upper_color']
            lower_color = row['lower_color']
            return upper_color, lower_color
        else:
            return None, None

    except pymysql.Error as error:
        print("MySQL에서 데이터를 가져오는 도중 오류 발생", error)
    finally:
        if (connection.is_connected()):
            cursor.close()
            connection.close()


@app.route('/save_route', methods=['POST'])
def save_route():
    global data
    if request.method == 'POST':
        if 'last_info' in session:
            data = session['last_info']
            # print("session['last_info']인가?! :", data)

            data['update_time'] = datetime.now(timezone.utc)

            update_time = data['update_time']

            name = data['name']

            # 세션에 데이터 저장
            session['last_info'] = data
            data = session['last_info']
        else:
            data = session.get('row_data')
            # print("session['row_data']인가?! :", data)

            data['update_time'] = datetime.now(timezone.utc)

            update_time = data['update_time']

            name = data['name']

            # 세션에 데이터 저장
            session['row_data'] = data
            data = session['row_data']
        print(data)
        # 폼 데이터 읽기
        route_A = request.form['route_A_input']
        latitude_A = float(request.form['Latitude_A'])
        longitude_A = float(request.form['longitude_A'])
        route_B = request.form['route_B_input']
        latitude_B = float(request.form['Latitude_B'])
        longitude_B = float(request.form['longitude_B'])

        route_C = request.form.get('route_C_input', None)
        latitude_C = float(request.form['Latitude_C']) if request.form.get('Latitude_C') else None
        longitude_C = float(request.form['longitude_C']) if request.form.get('longitude_C') else None
        route_D = request.form.get('route_D_input', None)
        latitude_D = float(request.form['Latitude_D']) if request.form.get('Latitude_D') else None
        longitude_D = float(request.form['longitude_D']) if request.form.get('longitude_D') else None
        route_E = request.form.get('route_E_input', None)
        latitude_E = float(request.form['Latitude_E']) if request.form.get('Latitude_E') else None
        longitude_E = float(request.form['longitude_E']) if request.form.get('longitude_E') else None

        connection = get_db_connection()
        try:
            with connection.cursor() as cursor:
                create_routes_table()
                sql = '''
                INSERT INTO routes (name,
                                    route_A, latitude_A, longitude_A, 
                                    route_B, latitude_B, longitude_B,
                                    route_C, latitude_C, longitude_C,
                                    route_D, latitude_D, longitude_D,
                                    route_E, latitude_E, longitude_E,
                                    update_time)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                '''
                cursor.execute(sql, (name,
                                     route_A, latitude_A, longitude_A,
                                     route_B, latitude_B, longitude_B,
                                     route_C, latitude_C, longitude_C,
                                     route_D, latitude_D, longitude_D,
                                     route_E, latitude_E, longitude_E,
                                     update_time))
                connection.commit()

        finally:
            connection.close()

    if 'date' in data:
        original_date = data['date']
        formatted_date = datetime.strptime(original_date, '%a, %d %b %Y %H:%M:%S %Z').strftime('%y-%m-%d')
        data['date'] = formatted_date

        selected_id = data['id']
        connection = get_db_connection()
        try:
            with connection.cursor() as cursor:
                sql = "SELECT missing_img1_data, missing_img2_data FROM missing_persons WHERE id = %s"
                cursor.execute(sql, (selected_id,))
                missing_imgs_data = cursor.fetchone()
                # print("missing_img_data:", missing_imgs_data)
                # print("missing_img_data[0]:", missing_imgs_data['missing_img1_data'])

        finally:
            connection.close()

    if missing_imgs_data['missing_img2_data'] == b'':
        img1_base64 = base64.b64encode(missing_imgs_data['missing_img1_data']).decode('utf-8') if \
            missing_imgs_data['missing_img1_data'] else None
        return render_template('tracking.html', data=data, img1=img1_base64)

    else:
        img1_base64 = base64.b64encode(missing_imgs_data['missing_img1_data']).decode('utf-8') if \
            missing_imgs_data['missing_img1_data'] else None
        img2_base64 = base64.b64encode(missing_imgs_data['missing_img2_data']).decode('utf-8') if \
            missing_imgs_data['missing_img2_data'] else None
        return render_template('tracking.html', data=data, img1=img1_base64, img2=img2_base64)

#        return render_template('tracking.html' )#,data= session['row_data'])

@app.route('/update_search_status', methods=['POST'])
def update_search_status():
    if request.method == 'POST':
        search_status = request.form['searchStatus']
        missing_person_id = request.form['id']

        # searchStatus 값에 따라 find 값을 설정합니다.
        find_value = 1 if search_status == 'completed' else 0

        connection = get_db_connection()
        try:
            with connection.cursor() as cursor:
                sql = "UPDATE missing_persons SET find = %s WHERE id = %s"
                cursor.execute(sql, (find_value, missing_person_id))

                sql = "SELECT * FROM missing_persons"
                cursor.execute(sql)
                result = cursor.fetchall()  # 모든 행을 가져옴

                connection.commit()

        finally:
            connection.close()

        return render_template('chart.html', data=result)


@app.route('/go_missing_info', methods=['POST'])
def go_missing_info():
    return render_template('missing_info.html')


@app.route('/tracking')
def tracking():
    global tracking_data  # 글로벌 변수 선언
    print("tracking 들어오는거야?")
    if 'last_info' in session:
        data = session['last_info']
        print("session['last_info']인가?! :",data)
       # session['tracking_data'] = data
       # tracking_data = data  # 글로벌 변수에 데이터 저장
       # print("Tracking data stored in session from last_info:", data)  # 디버깅 메시지 추가
    else:
        data = session.get('row_data')
        print("session['row_data']인가?! :",data)
       # session['tracking_data'] = data
       # tracking_data = data  # 글로벌 변수에 데이터 저장
       # print("Tracking data stored in session from row_data:", data)  # 디버깅 메시지 추가

    if 'date' in data:
        original_date = data['date']
        formatted_date = datetime.strptime(original_date, '%a, %d %b %Y %H:%M:%S %Z').strftime('%y-%m-%d')
        data['date'] = formatted_date

        selected_id = data['id']
        connection = get_db_connection()
        try:
            with connection.cursor() as cursor:
                sql = "SELECT missing_img1_data, missing_img2_data FROM missing_persons WHERE id = %s"
                cursor.execute(sql, (selected_id,))
                missing_imgs_data = cursor.fetchone()
                print("missing_img_data:", missing_imgs_data)
                print("missing_img_data[0]:", missing_imgs_data['missing_img1_data'])

        finally:
            connection.close()

    if missing_imgs_data['missing_img2_data'] == b'':
        img1_base64 = base64.b64encode(missing_imgs_data['missing_img1_data']).decode('utf-8') if \
        missing_imgs_data['missing_img1_data'] else None
        return render_template('tracking.html', data=data,img1=img1_base64)

    else:
        img1_base64 = base64.b64encode(missing_imgs_data['missing_img1_data']).decode('utf-8') if \
        missing_imgs_data['missing_img1_data'] else None
        img2_base64 = base64.b64encode(missing_imgs_data['missing_img2_data']).decode('utf-8') if \
        missing_imgs_data['missing_img2_data'] else None
        return render_template('tracking.html', data=data, img1=img1_base64,img2=img2_base64)


# Hex 코드를 RGB로 변환하는 함수
def hex_to_rgb(hex_code):
    hex_code = hex_code.lstrip('#')
    return tuple(int(hex_code[i:i + 2], 16) for i in (0, 2, 4))


# RGB 값을 BGR로 변환하는 함수
def rgb_to_bgr(rgb):
    return (rgb[2], rgb[1], rgb[0])  # BGR 순서로 변경


# Hex 코드를 BGR로 변환하는 함수
def hex_to_bgr(hex_code):
    rgb = hex_to_rgb(hex_code)
    return rgb_to_bgr(rgb)


# 색상 유사성을 평가하는 함수
def color_similarity_percentage(color1, color2):
    b1, g1, r1 = color1
    b2, g2, r2 = color2

    delta_b = abs(b1 - b2)
    delta_g = abs(g1 - g2)
    delta_r = abs(r1 - r2)

    # 각 색상 채널 값의 범위는 0부터 255이므로 이를 기준으로 비율을 계산
    percent_b = (1 - delta_b / 255) * 100
    percent_g = (1 - delta_g / 255) * 100
    percent_r = (1 - delta_r / 255) * 100

    # 세 개의 비율을 평균하여 전체 색상 유사성을 퍼센트로 계산
    similarity_percentage = (percent_b + percent_g + percent_r) / 3
    print("색상 유사도 퍼센트 : ", similarity_percentage)

    return similarity_percentage


# 가장 빈번하게 나타나는 색상을 찾는 함수
def most_frequent_color(image):
    pixels = np.float32(image.reshape(-1, 3))

    n_colors = 5
    criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 200, .1)
    flags = cv2.KMEANS_RANDOM_CENTERS

    _, labels, centroids = cv2.kmeans(pixels, n_colors, None, criteria, 10, flags)
    palette = np.uint8(centroids)
    dominant_color = palette[np.argmax(np.unique(labels, return_counts=True)[1])]

    print("탐지된 색상 : ", dominant_color)
    return tuple(dominant_color)


# 바운딩 박스에서 색상을 추출하는 함수
def extract_color_from_bbox(frame, bbox):
    xmin = int(bbox[0].item())
    ymin = int(bbox[1].item())
    xmax = int(bbox[2].item())
    ymax = int(bbox[3].item())
    extracted_color = frame[ymin:ymax, xmin:xmax]
    target_color = most_frequent_color(extracted_color)
    return target_color


# 객체 인식 처리 함수
def process_object_detection(result, frame, object_class, target_color_bgr):
    indices = (result.boxes.cls == object_class).nonzero(as_tuple=True)[0]

    if len(indices) == 0:
        return False

    for index in indices:
        bbox_coordinates = result.boxes.xyxy[index]
        extracted_color = frame[int(bbox_coordinates[1]):int(bbox_coordinates[3]),
                          int(bbox_coordinates[0]):int(bbox_coordinates[2])]
        extracted_color_bgr = most_frequent_color(extracted_color)

        # 추출된 색상과 타겟 색상의 유사성 비교
        similarity_percent = color_similarity_percentage(extracted_color_bgr, target_color_bgr)
        print("실종자 색상 : ", target_color_bgr)
        print("탐지된 색상 : ", extracted_color_bgr)

        # 유사성 임계값 설정 (예: 90% 유사성 이상을 유사하다고 판단)
        similarity_threshold = 70
        if similarity_percent >= similarity_threshold:
            print(similarity_percent, similarity_threshold)
            return True

    return False


# 비디오 스트림 처리 함수
@app.route('/stream', methods=['POST'])
def stream():
    global recording, out, data

    # 클라이언트로부터 전송된 비디오 데이터 받기
    video_data = request.data
    nparr = np.frombuffer(video_data, np.uint8)
    frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

    # 현재 시간을 프레임에 표시
    current_time = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(time.time()))
    cv2.putText(frame, current_time, org=(50, 450),
                fontFace=cv2.FONT_HERSHEY_TRIPLEX, fontScale=0.6,
                color=(226, 226, 226), thickness=2)

    object_detected = False
    annotated_frame = frame.copy()

    results = model(frame)

    # 데이터가 있는 경우에만 상체와 하체 인식 수행
    if data is not None:
        try:
            name = data['name']
            upper_color = hex_to_bgr(data['upper_color'])
            lower_color = hex_to_bgr(data['lower_color'])

            # 각 result에서 상체 및 하체 탐지
            for result in results:
                upper_detected = process_object_detection(result, frame, 1.0, upper_color)
                lower_detected = process_object_detection(result, frame, 2.0, lower_color)

            print(name, "실종자 상체 색상 : ", upper_color, "실종자 하체 색상 : ", lower_color)
            print("상체 일치 : ", upper_detected, "하체 일치 : ", lower_detected)

        except KeyError as e:
            # 데이터가 없는 경우에 대한 처리 (예: 로깅)
            print(f"KeyError: {e} - 데이터가 없습니다.")
            name = ""
            upper_color = (0, 0, 0)  # 기본 색상 설정
            lower_color = (0, 0, 0)  # 기본 색상 설정
            upper_detected = False
            lower_detected = False

    # 상체나 하체가 인식된 경우 얼굴 인식 수행
    if upper_detected or lower_detected:
        for result in results:
            if hasattr(result, 'boxes'):
                face_indices = (result.boxes.cls == 3.0).nonzero(as_tuple=True)[0]
                for index in face_indices:
                    bbox_coordinates = result.boxes.xyxy[index]
                    xmin = int(bbox_coordinates[0].item())
                    ymin = int(bbox_coordinates[1].item())
                    xmax = int(bbox_coordinates[2].item())
                    ymax = int(bbox_coordinates[3].item())

                    # 이미지에서 얼굴 부분을 추출하여 cropped_image에 저장
                    cropped_image = frame[ymin:ymax, xmin:xmax]
                    # 추출한 부분 이미지를 JPEG 형식으로 인코딩
                    _, img_encoded = cv2.imencode('.jpg', cropped_image)
                    img_base64 = base64.b64encode(img_encoded).decode('utf-8')
                    # SocketIO를 이용하여 클라이언트에게 얼굴 이미지 전송
                    socketio.emit('face', {'image': img_base64})

    # YOLOv8 객체 인식 수행 및 결과 프레임에 표시
    for result in results:
        if hasattr(result, 'boxes'):
            for box in result.boxes:
                conf = float(box.conf)
                print(f"객체 인식 유사도 : {conf}")  # 객체 인식 확률 확인을 위해 출력
                if conf >= 0.1:
                    # 인식된 객체가 그려진 프레임
                    annotated_frame = result.plot()
                    object_detected = True

    # 객체가 감지되지 않은 경우 원본 frame을 사용
    if not object_detected:
        annotated_frame = frame.copy()

    # JPEG 포맷으로 인코딩된 annotated_frame을 buffer에 저장
    _, buffer = cv2.imencode('.jpg', annotated_frame)
    # buffer를 base64 형식으로 변환하여 클라이언트에게 전송할 준비
    jpg_as_text = base64.b64encode(buffer).decode('utf-8')
    # SocketIO를 이용하여 클라이언트에게 비디오 스트림 전송
    socketio.emit('video_stream', {'video': jpg_as_text})
    # 녹화 중이면 프레임 저장
    if recording and out is not None:
        out.write(frame)

    return {'status': 'success'}


def start_recording():
    global out, rootPath, codec, fps, frameSize
    currentTime = time.strftime('%Y-%m-%d_%H-%M-%S', time.localtime(time.time()))
    videoFileName = rootPath + currentTime + '.avi'
    out = cv2.VideoWriter(videoFileName, codec, fps, frameSize)
    if not out.isOpened():
        print(f'Error: Failed to open {videoFileName} for writing.')
    else:
        print(f'파일({currentTime}.avi) 생성이 완료되었습니다.')

def stop_recording():
    global out
    if out is not None:
        out.release()
        out = None
        print('녹화가 중지되었습니다.')


@socketio.on('start_recording')
def handle_start_recording():
    print("start_recording")
    global recording
    if not recording:
        recording = True
        start_recording()
        socketio.emit('recording_status', {'status': 'recording'})

@socketio.on('stop_recording')
def handle_stop_recording():
    global recording
    if recording:
        recording = False
        stop_recording()
        socketio.emit('recording_status', {'status': 'stopped'})



if __name__ == '__main__':
    socketio.run(app, host="0.0.0.0", port=5000, debug=True, allow_unsafe_werkzeug=True)
